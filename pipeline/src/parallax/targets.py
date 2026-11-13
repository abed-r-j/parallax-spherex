"""Built-in fields: the five targets named in the challenge statement, plus extras.

Coordinates are ICRS degrees. For fast-moving stars the catalogue position (epoch J2000
unless stated) is moved to epoch 2026.0 with the catalogue proper motion, so that the star
sits near the middle of the cutout during the SPHEREx survey.

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    kind: str  # "motion" | "variable" | "mover" | "static"
    ra: float  # catalogue position, degrees
    dec: float
    epoch: float  # epoch of that position, Julian year
    pm_ra: float = 0.0  # mas/yr, includes cos(dec)
    pm_dec: float = 0.0  # mas/yr
    size_pix: int = 61
    max_images: int | None = None
    blurb: str = ""
    source: str = ""

    def at(self, year: float) -> tuple[float, float]:
        dt = year - self.epoch
        dec = self.dec + self.pm_dec * dt / 3.6e6
        ra = self.ra + self.pm_ra * dt / 3.6e6 / cos(radians(self.dec))
        return ra, dec

    @property
    def centre(self) -> tuple[float, float]:
        return self.at(2026.0)


TARGETS: dict[str, Target] = {
    t.key: t
    for t in [
        Target(
            "barnard", "Barnard's Star", "motion", 269.452075, 4.693391, 2000.0,
            -798.58, 10328.12,
            blurb="The fastest-moving star in the sky: 10.4 arcsec per year, about 1.7 SPHEREx pixels.",
            source="Gaia DR3 4472832130942575872 (position propagated to J2000)",
        ),
        Target(
            "epsindi", "Epsilon Indi B", "motion", 331.043833, -56.782694, 2000.0,
            3960.9, -2539.2, size_pix=61,
            blurb="A pair of brown dwarfs 12 light-years away, moving 4.7 arcsec per year.",
            source="Scholz et al. 2003; King et al. 2010",
        ),
        Target(
            "wise0855", "WISE 0855-0714", "motion", 133.795129, -7.245147, 2014.3,
            -8118.0, 680.0, size_pix=81,
            blurb="The coldest known brown dwarf (about 250 K), moving 8.1 arcsec per year. "
                  "The challenge coordinates are its 2014 position.",
            source="Luhman 2014; Luhman & Esplin 2016",
        ),
        Target(
            "rwaur", "RW Aurigae", "variable", 76.956417, 30.401417, 2000.0,
            blurb="A young T Tauri binary with deep, irregular dimming events.",
            source="SIMBAD",
        ),
        Target(
            "rdra", "R Draconis", "variable", 248.167500, 66.755000, 2000.0,
            max_images=600,
            blurb="A Mira variable with a 246-day period, close to the north ecliptic pole "
                  "where SPHEREx returns very often.",
            source="SIMBAD; AAVSO VSX",
        ),
    ]
}
