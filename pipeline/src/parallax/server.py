"""ParallaX local engine: serves the web app and builds fields for any coordinates.

Start it with ``parallax serve`` and open http://127.0.0.1:8000 . The engine

* serves the built web app (``web/dist``) and every published data pack, so the whole
  tool runs from one laptop, without internet, for the fields already built;
* accepts ``POST /api/field {ra, dec, size_arcmin}``, downloads the SPHEREx Level-2
  cutouts for that position from NASA/IPAC IRSA, runs the full pipeline and publishes a
  new pack, reporting progress through ``GET /api/job/<id>``.

The public static site talks to this same interface when its coordinates fall outside
the precomputed fields.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import re
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import __version__
from .frames import PIXEL_ARCSEC
from .irsa import fetch_field
from .publish import publish_field, repo_root
from .targets import Target

MAX_SIZE_ARCMIN = 12.0
DEFAULT_MAX_IMAGES = 160


class FieldRequest(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    size_arcmin: float = Field(default=6.0, gt=0.5, le=MAX_SIZE_ARCMIN)
    max_images: int = Field(default=DEFAULT_MAX_IMAGES, ge=8, le=1200)
    name: str | None = Field(default=None, max_length=60)


@dataclass
class Job:
    id: str
    key: str
    state: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    message: str = "Waiting to start"
    started: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {"id": self.id, "state": self.state, "progress": round(self.progress, 3),
                "message": self.message, "key": self.key if self.state == "done" else None,
                "seconds": round(time.time() - self.started, 1)}


def field_key(ra: float, dec: float, n: int) -> str:
    sign = "p" if dec >= 0 else "m"
    return f"live_{ra:08.4f}_{sign}{abs(dec):07.4f}_{n}".replace(".", "d")


def size_to_pixels(size_arcmin: float) -> int:
    n = int(round(size_arcmin * 60.0 / PIXEL_ARCSEC))
    return max(15, n | 1)  # odd, so the target sits on a pixel centre


def create_app(data_dir: Path | None = None, site_dir: Path | None = None) -> FastAPI:
    root = repo_root()
    data_dir = Path(data_dir or root / "data")
    site_dir = Path(site_dir or root / "web" / "dist")
    packs = [data_dir / "live", root / "web" / "public" / "data", site_dir / "data"]
    (data_dir / "live").mkdir(parents=True, exist_ok=True)
    jobs: dict[str, Job] = {}
    lock = threading.Lock()  # one field at a time: be gentle with the archive

    app = FastAPI(title="ParallaX engine", version=__version__)

    @app.middleware("http")
    async def cors(request: Request, call_next):
        if request.method == "OPTIONS":
            resp: Response = Response(status_code=204)
        else:
            resp = await call_next(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "content-type"
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
        return resp

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "engine": "parallax", "version": __version__,
                "maxSizeArcmin": MAX_SIZE_ARCMIN}

    def run(job: Job, req: FieldRequest, n: int) -> None:
        with lock:
            try:
                job.state, job.message = "running", "Asking the archive which images cover this spot"
                raw = data_dir / "raw" / job.key

                def progress(msg: str) -> None:
                    m = re.search(r"(\d+)/(\d+)", msg)
                    if m and int(m.group(2)) > 0:
                        done, total = int(m.group(1)), int(m.group(2))
                        job.progress = 0.05 + 0.75 * done / total
                        job.message = f"Downloading SPHEREx images: {done} of {total}"
                    else:
                        job.message = msg.strip()

                res = fetch_field(req.ra, req.dec, n, raw, threads=6,
                                  max_images=req.max_images, progress=progress)
                if res["n_requested"] == 0:
                    raise RuntimeError("SPHEREx has not released images of this position yet")
                job.progress, job.message = 0.82, "Aligning images and building the chromatic template"
                name = req.name or f"RA {req.ra:.4f}  Dec {req.dec:+.4f}"
                target = Target(job.key, name, "custom", req.ra, req.dec, 2026.0, size_pix=n,
                                blurb=f"Built on request from {res['n_requested']} of "
                                      f"{res['n_available']} available SPHEREx images.")
                entry = publish_field(job.key, target, data_dir, data_dir / "live",
                                      with_injection=False, online=True,
                                      log=lambda m: setattr(job, "message", m.strip()[:160]))
                if entry is None:
                    raise RuntimeError("no usable images at this position")
                job.state, job.progress, job.message = "done", 1.0, "Ready"
            except Exception as e:
                traceback.print_exc()
                job.state, job.message = "error", f"{type(e).__name__}: {str(e)[:200]}"

    @app.post("/api/field")
    def start(req: FieldRequest) -> dict:
        n = size_to_pixels(req.size_arcmin)
        key = field_key(req.ra, req.dec, n)
        for j in jobs.values():  # same request already running or finished: reuse it
            if j.key == key and j.state in ("queued", "running", "done"):
                return j.public()
        job = Job(uuid.uuid4().hex[:12], key)
        if (data_dir / "live" / key / "meta.json").exists():
            job.state, job.progress, job.message = "done", 1.0, "Ready (already built)"
        else:
            threading.Thread(target=run, args=(job, req, n), daemon=True).start()
        jobs[job.id] = job
        return job.public()

    @app.get("/api/job/{job_id}")
    def status(job_id: str) -> dict:
        if job_id not in jobs:
            raise HTTPException(404, "unknown job")
        return jobs[job_id].public()

    @app.get("/data/{key}/{name}")
    def pack_file(key: str, name: str):
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", key) or name not in ("meta.json", "cube.bin", "thumb.png"):
            raise HTTPException(404)
        for base in packs:
            p = base / key / name
            if p.is_file():
                return FileResponse(p)
        raise HTTPException(404)

    @app.get("/data/index.json")
    def index():
        import json

        fields: dict[str, dict] = {}
        for base in reversed(packs):
            p = base / "index.json"
            if p.is_file():
                for e in json.loads(p.read_text())["fields"]:
                    fields[e["key"]] = e
        live = data_dir / "live"
        for meta in live.glob("*/meta.json"):
            m = json.loads(meta.read_text())
            fields.setdefault(m["key"], {
                "key": m["key"], "name": m["name"], "kind": m["kind"], "ra": m["ra0"],
                "dec": m["dec0"], "n": m["n"], "scale": m["scale"],
                "nFrames": len(m["frames"]["mjd"]), "nCampaigns": len(m["campaigns"]),
                "blurb": m.get("blurb", ""), "thumb": f"{m['key']}/thumb.png"})
        return JSONResponse({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             "pipeline": __version__, "fields": list(fields.values())})

    @app.get("/{path:path}")
    def site(path: str):
        target = (site_dir / path).resolve()
        if site_dir.resolve() in target.parents and target.is_file():
            return FileResponse(target)
        home = site_dir / "index.html"
        if home.is_file():
            return FileResponse(home)
        return JSONResponse({"detail": "web app not built: run 'npm run build' in web/"}, 404)

    return app
