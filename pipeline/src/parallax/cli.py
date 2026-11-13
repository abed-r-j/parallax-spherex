"""Command line for ParallaX.

    parallax targets                     list the built-in fields
    parallax fetch barnard               download SPHEREx cutouts for a built-in field
    parallax fetch --ra 10.68 --dec 41.27 --key m31 --name "M31"   ... or for any position
    parallax publish                     rebuild every data pack for the web app
    parallax serve                       run the web app + live engine on this computer

Updating to a new SPHEREx data release is ``parallax fetch <field>`` (only new images are
downloaded) followed by ``parallax publish <field>``.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from .publish import all_targets, publish, repo_root
from .targets import Target

app = typer.Typer(add_completion=False, help="ParallaX: the SPHEREx sky in motion.")


def _data() -> Path:
    return repo_root() / "data"


@app.command()
def targets() -> None:
    """List the fields this installation knows about."""
    for t in all_targets(_data()).values():
        ra, dec = t.centre
        n = len(list((_data() / "raw" / t.key).glob("*.fits")))
        typer.echo(f"{t.key:10s} {t.kind:9s} {ra:10.5f} {dec:+10.5f}  {n:5d} cutouts  {t.name}")


@app.command()
def fetch(
    key: str = typer.Argument(None, help="Built-in field key, or a new key with --ra/--dec."),
    ra: float = typer.Option(None, help="Right ascension, degrees (ICRS)."),
    dec: float = typer.Option(None, help="Declination, degrees (ICRS)."),
    name: str = typer.Option(None, help="Display name for a new field."),
    size_arcmin: float = typer.Option(6.25, help="Field of view for a new field."),
    max_images: int = typer.Option(None, help="Cap on images (evenly spaced in time)."),
    mirror: str = typer.Option("irsa", help="'irsa' or 's3' (the public AWS mirror)."),
    threads: int = typer.Option(6, help="Parallel downloads."),
) -> None:
    """Download every SPHEREx Level-2 cutout covering a field (resumable, incremental)."""
    from .irsa import fetch_field
    from .server import size_to_pixels

    known = all_targets(_data())
    if key in known and ra is None:
        t = known[key]
    elif key and ra is not None and dec is not None:
        t = Target(key, name or key, "custom", ra, dec, 2026.0,
                   size_pix=size_to_pixels(size_arcmin), max_images=max_images)
        extra = _data() / "extra_targets.json"
        rows = json.loads(extra.read_text()) if extra.exists() else []
        rows = [r for r in rows if r["key"] != key] + [asdict(t)]
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text(json.dumps(rows, indent=1))
    else:
        raise typer.BadParameter("give a known field key, or a new key with --ra and --dec")
    c_ra, c_dec = t.centre
    typer.echo(f"{t.name}: centre {c_ra:.5f} {c_dec:+.5f}, {t.size_pix} px, mirror {mirror}")
    res = fetch_field(c_ra, c_dec, t.size_pix, _data() / "raw" / t.key, threads=threads,
                      max_images=max_images or t.max_images, mirror=mirror, progress=typer.echo)
    typer.echo(f"done: {res['n_requested']} of {res['n_available']} images, "
               f"{res['n_failed']} failed, {res['bytes'] / 1e6:.1f} MB, {res['seconds']:.0f} s")


@app.command(name="publish")
def publish_cmd(
    keys: list[str] = typer.Argument(None, help="Fields to publish (default: all with data)."),
    injection: bool = typer.Option(False, help="Re-run the injection-recovery tests (slow)."),
    offline: bool = typer.Option(False, help="Skip catalogue and solar-system lookups."),
    rebuild: bool = typer.Option(False, help="Rebuild aligned cubes even if cached."),
) -> None:
    """Run the pipeline and write the data packs the web app reads."""
    entries = publish(keys or None, with_injection=injection, online=not offline,
                      rebuild=rebuild, log=typer.echo)
    typer.echo(f"{len(entries)} fields in the index")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Serve the web app and the live engine: open http://127.0.0.1:8000 ."""
    import uvicorn

    from .server import create_app

    typer.echo(f"ParallaX is running at http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
