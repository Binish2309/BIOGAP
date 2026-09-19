"""
src/ingestion/osm_context.py

Real ingestion connector for OpenStreetMap road/path network data via the
public Overpass API -- the CONTEXTUAL layer needed to distinguish a
genuine biodiversity gap from a recording gap.

WHY THIS EXISTS
----------------
The bias literature reviewed in this project's Stage 1 report is
consistent: accessibility (road/path density, proximity to trails) is the
single strongest predictor of WHERE citizen-science observation effort
concentrates -- stronger than population density in several studies (Tiago
et al. 2017, Scientific Reports, found path/trail density the strongest
predictor in 7 of 8 taxonomic groups studied). This module fetches real
road/path geometry for the study area so BIOGAP can test that relationship
directly: a grid cell with HIGH accessibility but LOW observation density
is much stronger evidence of a recording gap than a cell that is simply
remote and hard to reach.

WHAT THIS MODULE DOES NOT DO
------------------------------
- It does not compute true road LENGTH per grid cell (that requires
  line-in-polygon geometric intersection, out of scope for now). Instead
  it counts OSM way VERTICES (the coordinate points that make up each
  road/path's geometry) falling in each cell, as a documented, honest
  density PROXY -- denser digitised road geometry in a cell produces more
  vertex hits. This is stated explicitly wherever the resulting numbers
  are shown, not silently presented as a precise length measurement.
- It does not fetch population data (e.g. WorldPop). That requires raster
  processing (rasterio) and multi-hundred-MB downloads that would
  reintroduce exactly the memory/timeout problems the staged biodiversity
  ingestion redesign just fixed. It remains a documented, NOT_IMPLEMENTED
  future enhancement -- see RESEARCH_METHOD.md.

REAL, PUBLIC, KEY-FREE API
----------------------------
POST https://overpass-api.de/api/interpreter, body: an Overpass QL query
string. No API key, but please be a good citizen of a free public service:
this connector queries a REDUCED set of highway tags (the ones with
documented relevance to recording accessibility -- primary/secondary/
tertiary/residential roads plus paths/footways/tracks), not everything
OSM has, and is meant to be run ONCE per study area, not repeatedly -- the
result is cached to data/raw/osm_roads_raw.csv and reused.
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from src.config import CONFIG, RAW_DIR, BoundingBox
from src.utils.provenance import ProvenanceRecord, write_provenance, now_utc_iso

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

# Highway tags with documented relevance to recording accessibility.
# Deliberately excludes service roads, parking aisles, motorway link ramps,
# etc., which would inflate vertex counts without reflecting genuine
# human-accessible routes a recorder would plausibly walk/drive/cycle.
HIGHWAY_TAGS = [
    "primary", "secondary", "tertiary", "residential",
    "path", "footway", "track", "trunk", "unclassified",
]

RAW_FIELDS = ["way_id", "highway_type", "vertex_index", "latitude", "longitude"]


def _build_query(bbox: BoundingBox, timeout_s: int) -> str:
    tag_regex = "^(" + "|".join(HIGHWAY_TAGS) + ")$"
    if bbox.polygon_wkt:
        # Overpass QL doesn't take arbitrary WKT directly; fall back to the
        # polygon's rectangular envelope for the query, matching the same
        # documented approach used in src/ingestion/inaturalist.py -- exact
        # polygon filtering happens client-side afterwards if needed.
        south, west, north, east = bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon
    else:
        south, west, north, east = bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon
    return (
        f'[out:json][timeout:{timeout_s}];\n'
        f'(\n'
        f'  way["highway"~"{tag_regex}"]({south},{west},{north},{east});\n'
        f');\n'
        f'out geom;'
    )


def run_osm_context_ingestion(bbox: Optional[BoundingBox] = None,
                               timeout_s: int = 90,
                               raw_output_name: str = "osm_roads_raw.csv") -> ProvenanceRecord:
    """
    Fetch real OSM road/path geometry for the study area. This is a single,
    heavier request (not paginated like the biodiversity connectors) --
    expect it to take anywhere from a few seconds to a couple of minutes
    for an area the size of MMR. Meant to be run once and cached, not
    re-run on every page load.

    Returns a ProvenanceRecord with the same SUCCESS/FAILED/UNTESTED
    contract as every other connector in this project. Never fabricates
    data on failure.
    """
    bbox = bbox or CONFIG.bbox
    access_time = now_utc_iso()
    query = _build_query(bbox, timeout_s)
    geo_filter = {"bbox": {"min_lat": bbox.min_lat, "max_lat": bbox.max_lat,
                            "min_lon": bbox.min_lon, "max_lon": bbox.max_lon},
                  "is_official_polygon": bbox.is_official_polygon,
                  "note": "Overpass QL queries a rectangular bbox natively; polygon_wkt, "
                          "if set, is not yet applied to this connector (documented gap)."}
    query_params = {"highway_tags": HIGHWAY_TAGS, "timeout_s": timeout_s}

    if not REQUESTS_AVAILABLE:
        record = ProvenanceRecord(
            source="OSM (Overpass)", source_url_or_api=OVERPASS_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail="'requests' package is not installed.",
        )
        write_provenance(record, "osm_context_provenance.json")
        return record

    try:
        resp = requests.post(OVERPASS_ENDPOINT, data={"data": query}, timeout=timeout_s + 15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        record = ProvenanceRecord(
            source="OSM (Overpass)", source_url_or_api=OVERPASS_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail=f"{type(exc).__name__}: {exc}",
            extra_notes=(
                "Overpass is a shared free public service and occasionally rate-limits or "
                "times out under load -- if this keeps failing, wait a few minutes and retry, "
                "or reduce the bounding box size. No fallback/synthetic data was generated."
            ),
        )
        write_provenance(record, "osm_context_provenance.json")
        return record

    elements = payload.get("elements", [])
    rows = []
    for way in elements:
        way_id = way.get("id")
        highway_type = (way.get("tags") or {}).get("highway", "unknown")
        for i, node in enumerate(way.get("geometry") or []):
            rows.append({
                "way_id": way_id, "highway_type": highway_type, "vertex_index": i,
                "latitude": node.get("lat"), "longitude": node.get("lon"),
            })

    if not rows:
        record = ProvenanceRecord(
            source="OSM (Overpass)", source_url_or_api=OVERPASS_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="SUCCESS",
            extra_notes="Query succeeded but returned zero road/path features for this bounding box.",
        )
        write_provenance(record, "osm_context_provenance.json")
        return record

    df = pd.DataFrame(rows, columns=RAW_FIELDS)
    raw_path = RAW_DIR / raw_output_name
    df.to_csv(raw_path, index=False)

    highway_counts = df.drop_duplicates("way_id")["highway_type"].value_counts().to_dict()

    record = ProvenanceRecord(
        source="OSM (Overpass)", source_url_or_api=OVERPASS_ENDPOINT,
        access_datetime_utc=access_time, query_parameters=query_params,
        geographic_filter=geo_filter, taxonomic_filter=None,
        records_retrieved=int(df["way_id"].nunique()), records_retained=int(df["way_id"].nunique()),
        cleaning_operations=["none -- raw ingestion stage only; vertex-to-grid-cell aggregation "
                              "happens in src/analysis/blind_spot_evidence.py, not here"],
        excluded_records=[],
        licensing_info="OpenStreetMap contributors, Open Database License (ODbL) -- share-alike, attribution required.",
        status="SUCCESS",
        extra_notes=(
            f"{df['way_id'].nunique():,} distinct road/path ways, {len(df):,} total geometry "
            f"vertices. Ways by highway type: {highway_counts}. This is VERTEX-COUNT data, a "
            "density proxy, not a true road-length calculation -- see module docstring."
        ),
    )
    write_provenance(record, "osm_context_provenance.json")
    return record


if __name__ == "__main__":
    import json
    result = run_osm_context_ingestion()
    print(json.dumps(result.to_dict(), indent=2, default=str))
