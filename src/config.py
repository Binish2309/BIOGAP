"""
src/config.py

Central, configurable settings for BIOGAP. Nothing else in the codebase
should hard-code the study-area geometry, file paths, or API endpoints --
they should all be read from here (or from environment variables /
config.json, which override the defaults below).

RESEARCH INTEGRITY NOTE:
The DEFAULT_BBOX below is a hand-built rectangular APPROXIMATION of the
Mumbai Metropolitan Region, not an official MMRDA administrative polygon.
It is a placeholder for feasibility testing. See DATA_PROVENANCE.md and
RESEARCH_METHOD.md for the full discussion. The geometry is intentionally
configurable (via config.json or environment variables) so it can be
replaced with an authoritative polygon later without touching any other
module.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
METADATA_DIR = DATA_DIR / "metadata"

for _d in (RAW_DIR, PROCESSED_DIR, METADATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = PROJECT_ROOT / "config.json"


@dataclass
class BoundingBox:
    """A simple rectangular study-area definition, OR (if polygon_wkt is
    set) a real polygon with this rectangle kept only as its bounding
    envelope for sources whose API can't accept an arbitrary polygon.
    See module docstring."""
    min_lat: float = 18.75
    max_lat: float = 19.50
    min_lon: float = 72.75
    max_lon: float = 73.35
    label: str = "MMR feasibility bounding box (hand-built approximation, NOT official MMRDA boundary)"
    is_official_polygon: bool = False
    polygon_wkt: Optional[str] = None  # e.g. "POLYGON((lon lat, lon lat, ...))" -- counter-clockwise, per GBIF's requirement

    def as_gbif_params(self) -> dict:
        if self.polygon_wkt:
            return {"geometry": self.polygon_wkt}
        return {
            "decimalLatitude": f"{self.min_lat},{self.max_lat}",
            "decimalLongitude": f"{self.min_lon},{self.max_lon}",
        }

    def as_inaturalist_params(self) -> dict:
        # iNaturalist's public API has no arbitrary-polygon filter -- only a
        # rectangular bbox (swlat/swlng/nelat/nelng). When polygon_wkt is
        # set, the connector queries this rectangle (the polygon's envelope,
        # a strict superset) and then filters retained points against the
        # real polygon locally -- see src/ingestion/inaturalist.py.
        return {
            "swlat": self.min_lat, "swlng": self.min_lon,
            "nelat": self.max_lat, "nelng": self.max_lon,
        }

    def center(self) -> tuple[float, float]:
        return ((self.min_lat + self.max_lat) / 2, (self.min_lon + self.max_lon) / 2)

    def contains_point(self, lat: float, lon: float) -> bool:
        """
        True if (lat, lon) is inside the real geometry: the polygon if
        polygon_wkt is set, else the rectangle. Used to post-filter sources
        (like iNaturalist) that can only be queried by rectangle even when
        a real polygon is configured.
        """
        if self.polygon_wkt:
            from shapely import wkt as shapely_wkt
            from shapely.geometry import Point
            poly = shapely_wkt.loads(self.polygon_wkt)
            return bool(poly.contains(Point(lon, lat)))
        return (self.min_lat <= lat <= self.max_lat) and (self.min_lon <= lon <= self.max_lon)


@dataclass
class AppConfig:
    bbox: BoundingBox = field(default_factory=BoundingBox)
    country_filter: Optional[str] = "IN"
    gbif_page_size: int = 300
    # gbif_max_offset is the ABSOLUTE ceiling GBIF's synchronous search API
    # allows (offset+limit <= 100,000) -- it is a hard API limit, not a
    # tuning knob. It stays high so a deliberate CLI/full run can still
    # reach it. Interactive (Streamlit) runs use the separate, much smaller
    # gbif_interactive_record_limit below so a single button click stays
    # fast and reliable on Streamlit Cloud. See RESEARCH_METHOD.md.
    gbif_max_offset: int = 100_000
    # Conservative default for a single interactive "Fetch GBIF observations"
    # click: at gbif_page_size=300 this is ~27 sequential requests, which
    # comfortably finishes within a Streamlit Cloud session instead of the
    # ~334 requests a full 100k-offset run would need. If GBIF reports more
    # matching records than this, the UI says so honestly rather than
    # claiming completeness -- see src/ingestion/gbif.py.
    gbif_interactive_record_limit: int = 8_000
    inaturalist_per_page: int = 200
    # Absolute ceiling for the page/per_page pagination strategy before the
    # id_above workaround kicks in (see src/ingestion/inaturalist.py).
    inaturalist_max_results: int = 10_000
    # Interactive (optional, second-stage) ingestion default -- smaller than
    # inaturalist_max_results so the optional "Add iNaturalist observations"
    # step also finishes quickly.
    inaturalist_interactive_record_limit: int = 3_000
    request_delay_seconds: float = 0.5
    spatial_default_grid_size_deg: float = 0.05  # ~5.5 km at this latitude; user-configurable in UI


def load_config() -> AppConfig:
    """
    Build the app configuration, applying overrides in this priority order:
    built-in defaults  <  config.json (if present)  <  environment variables.
    Nothing here invents study-area geometry -- it only changes WHICH
    already-specified geometry/settings are active.
    """
    cfg = AppConfig()

    if CONFIG_FILE.exists():
        try:
            overrides = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"config.json is not valid JSON: {exc}") from exc

        bbox_overrides = overrides.get("bbox", {})
        for k, v in bbox_overrides.items():
            if hasattr(cfg.bbox, k):
                setattr(cfg.bbox, k, v)

        for k, v in overrides.items():
            if k != "bbox" and hasattr(cfg, k):
                setattr(cfg, k, v)

    # Environment variable overrides (useful for CI / different laptops)
    env_map = {
        "BIOGAP_MIN_LAT": ("bbox", "min_lat", float),
        "BIOGAP_MAX_LAT": ("bbox", "max_lat", float),
        "BIOGAP_MIN_LON": ("bbox", "min_lon", float),
        "BIOGAP_MAX_LON": ("bbox", "max_lon", float),
        "BIOGAP_COUNTRY_FILTER": (None, "country_filter", str),
    }
    for env_var, (sub, attr, caster) in env_map.items():
        if env_var in os.environ:
            value = caster(os.environ[env_var])
            target = getattr(cfg, sub) if sub else cfg
            setattr(target, attr, value)

    return cfg


def config_as_dict(cfg: AppConfig) -> dict:
    return asdict(cfg)


# A module-level singleton most code can just import directly.
CONFIG = load_config()
