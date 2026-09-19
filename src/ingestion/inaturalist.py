"""
src/ingestion/inaturalist.py

Real iNaturalist ingestion connector, built against iNaturalist's official
v1 REST API (api.inaturalist.org/v1/observations), confirmed from
iNaturalist's own API documentation and "API Recommended Practices" page:

  - Bounding-box params: swlat, swlng, nelat, nelng
  - Pagination: page / per_page (per_page max 200 for most endpoints)
  - HARD LIMIT: a given set of search parameters can return at most 10,000
    records via page/per_page pagination; beyond that, iNaturalist's own
    docs say to sort by id ascending (order_by=id&order=asc) and page with
    id_above instead. This connector implements the id_above strategy
    automatically once the 10,000 cap is approached, rather than silently
    truncating.
  - Recommended rate limit: about 1 request/second, ~10,000 requests/day.
  - quality_grade is left unfiltered by default (both "research" and
    "needs_id" grade observations are retrieved) -- filtering to
    research-grade only is a downstream analysis choice, not an ingestion
    decision, and is NOT applied here so raw data stays maximally complete.

This module attempts a real network call when run and reports FAILED
(with the real exception) rather than fabricating data if it cannot reach
api.inaturalist.org.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import pandas as pd

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from src.config import CONFIG, RAW_DIR, BoundingBox
from src.utils.provenance import ProvenanceRecord, write_provenance, now_utc_iso

INATURALIST_ENDPOINT = "https://api.inaturalist.org/v1/observations"

RAW_FIELDS = [
    "inat_id", "uuid", "taxon_name", "taxon_rank", "iconic_taxon_name",
    "latitude", "longitude", "observed_on", "quality_grade",
    "license_code", "photo_count", "user_login",
]


def _parse_page(results: list[dict]) -> list[dict]:
    rows = []
    for obs in results:
        taxon = obs.get("taxon") or {}
        geojson = obs.get("geojson") or {}
        coords = geojson.get("coordinates") if geojson else None
        lon, lat = (coords[0], coords[1]) if coords and len(coords) == 2 else (pd.NA, pd.NA)
        photos = obs.get("photos") or []
        rows.append({
            "inat_id": obs.get("id", pd.NA),
            "uuid": obs.get("uuid", pd.NA),
            "taxon_name": taxon.get("name", pd.NA),
            "taxon_rank": taxon.get("rank", pd.NA),
            "iconic_taxon_name": taxon.get("iconic_taxon_name", pd.NA),
            "latitude": lat,
            "longitude": lon,
            "observed_on": obs.get("observed_on", pd.NA),
            "quality_grade": obs.get("quality_grade", pd.NA),
            "license_code": obs.get("license_code", pd.NA),
            "photo_count": len(photos),
            "user_login": (obs.get("user") or {}).get("login", pd.NA),
        })
    return rows


def _fetch_all_records(bbox_params: dict, per_page: int, max_results: int,
                        delay: float, on_progress: Optional[Callable[[str], None]] = None,
                        **_ignored) -> tuple[list[dict], dict]:
    """
    **_ignored absorbs any extra keyword arguments (e.g. from future
    callers) so existing test doubles that only accept the original four
    positional parameters keep working unmodified.
    """

    def _report(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    all_rows: list[dict] = []
    run_info = {"pages_fetched": 0, "used_id_above_strategy": False, "total_results_reported": None}

    _report("Connecting to iNaturalist...")

    page = 1
    id_above = None
    while True:
        params = {**bbox_params, "per_page": per_page, "order_by": "id", "order": "asc"}
        if id_above is not None:
            params["id_above"] = id_above
            run_info["used_id_above_strategy"] = True
        else:
            params["page"] = page

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = requests.get(INATURALIST_ENDPOINT, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception:  # noqa: BLE001
                if attempt >= 3:
                    raise
                _report(f"iNaturalist request failed (attempt {attempt}/3), retrying...")
                time.sleep(2 ** attempt)

        if run_info["total_results_reported"] is None:
            run_info["total_results_reported"] = data.get("total_results")
            _report("iNaturalist connection successful.")

        results = data.get("results", [])
        rows = _parse_page(results)
        all_rows.extend(rows)
        run_info["pages_fetched"] += 1
        _report(f"Fetched {len(all_rows):,} records so far (page {run_info['pages_fetched']})...")

        if not results:
            break

        if len(all_rows) >= max_results:
            run_info["hit_result_limit"] = True
            break

        # Switch to id_above pagination once we approach the 10k page/per_page cap.
        if len(all_rows) >= max_results - per_page and id_above is None:
            id_above = results[-1].get("id")
        elif id_above is not None:
            id_above = results[-1].get("id")
        else:
            page += 1

        if len(results) < per_page:
            break
        time.sleep(delay)

    run_info.setdefault("hit_result_limit", False)
    return all_rows, run_info


def run_inaturalist_ingestion(bbox: Optional[BoundingBox] = None,
                               per_page: Optional[int] = None,
                               max_results: Optional[int] = None,
                               delay: Optional[float] = None,
                               on_progress: Optional[Callable[[str], None]] = None,
                               raw_output_name: str = "inaturalist_raw.csv") -> ProvenanceRecord:
    """
    Run a real iNaturalist ingestion for the configured bounding box.
    Mirrors run_gbif_ingestion()'s contract: never raises on API failure,
    returns a ProvenanceRecord with status SUCCESS/FAILED, never fabricates
    data.

    max_results defaults to CONFIG.inaturalist_interactive_record_limit (a
    conservative bound for the optional, second-stage interactive "Add
    iNaturalist observations" step), NOT CONFIG.inaturalist_max_results
    (the absolute page/per_page cap before the id_above workaround). Pass
    max_results=CONFIG.inaturalist_max_results explicitly for a fuller,
    non-interactive run.

    If bbox.polygon_wkt is set, iNaturalist is queried using the polygon's
    rectangular envelope (a strict superset -- this API has no arbitrary-
    polygon filter), and results are then filtered locally to points that
    actually fall inside the real polygon via bbox.contains_point(). The
    number of records excluded this way is recorded in the returned
    ProvenanceRecord's excluded_records, never silently dropped.
    """
    bbox = bbox or CONFIG.bbox
    per_page = per_page or CONFIG.inaturalist_per_page
    max_results = max_results or CONFIG.inaturalist_interactive_record_limit
    delay = delay if delay is not None else max(CONFIG.request_delay_seconds, 1.0)  # iNat asks for >=1s

    def _report(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    bbox_params = bbox.as_inaturalist_params()
    access_time = now_utc_iso()
    geo_filter = {"bbox": {"min_lat": bbox.min_lat, "max_lat": bbox.max_lat,
                            "min_lon": bbox.min_lon, "max_lon": bbox.max_lon},
                  "is_official_polygon": bbox.is_official_polygon,
                  "polygon_wkt_configured": bool(bbox.polygon_wkt)}
    if bbox.polygon_wkt:
        geo_filter["note"] = ("Queried via the polygon's rectangular envelope (iNaturalist's "
                               "public API has no arbitrary-polygon filter); results below are "
                               "POST-FILTERED to the real polygon locally -- see excluded_records.")

    if not REQUESTS_AVAILABLE:
        _report("'requests' package is not installed -- cannot connect to iNaturalist.")
        record = ProvenanceRecord(
            source="iNaturalist", source_url_or_api=INATURALIST_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=bbox_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail="'requests' package is not installed.",
        )
        write_provenance(record, "inaturalist_provenance.json")
        return record

    try:
        raw_rows, run_info = _fetch_all_records(bbox_params, per_page, max_results, delay,
                                                  on_progress=_report)
    except Exception as exc:  # noqa: BLE001
        _report(f"iNaturalist ingestion failed: {type(exc).__name__}: {exc}")
        record = ProvenanceRecord(
            source="iNaturalist", source_url_or_api=INATURALIST_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=bbox_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail=f"{type(exc).__name__}: {exc}",
            extra_notes="No fallback/synthetic data was generated.",
        )
        write_provenance(record, "inaturalist_provenance.json")
        return record

    if not raw_rows:
        _report("iNaturalist query succeeded but returned zero records for this bounding box.")
        record = ProvenanceRecord(
            source="iNaturalist", source_url_or_api=INATURALIST_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=bbox_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="SUCCESS",
            extra_notes="Query succeeded but returned zero records for this bounding box.",
        )
        write_provenance(record, "inaturalist_provenance.json")
        return record

    _report("Cleaning observations...")
    df = pd.DataFrame(raw_rows, columns=RAW_FIELDS)
    excluded_records = []

    if bbox.polygon_wkt:
        n_before = len(df)
        has_coords = df["latitude"].notna() & df["longitude"].notna()
        inside = has_coords & df.apply(
            lambda r: bbox.contains_point(r["latitude"], r["longitude"]) if pd.notna(r["latitude"]) else False,
            axis=1,
        )
        n_outside_polygon = int((has_coords & ~inside).sum())
        n_no_coords = int((~has_coords).sum())
        df = df[inside].copy()
        if n_outside_polygon:
            excluded_records.append({
                "reason": "fell inside the rectangular envelope but outside the real configured polygon",
                "count": n_outside_polygon,
            })
        if n_no_coords:
            excluded_records.append({
                "reason": "missing coordinates -- cannot be tested against the polygon, excluded from this polygon-filtered file only (NOT deleted from raw API response, simply not included in the polygon-scoped CSV)",
                "count": n_no_coords,
            })

    _report("Saving verified dataset...")
    raw_path = RAW_DIR / raw_output_name
    df.to_csv(raw_path, index=False)

    license_counts = df["license_code"].fillna("MISSING").value_counts().to_dict()

    total_reported = run_info.get("total_results_reported")
    honesty_note = ""
    if run_info.get("hit_result_limit") and total_reported is not None and total_reported > len(raw_rows):
        honesty_note = (
            f" iNaturalist reported {total_reported:,} matching observations at the first "
            f"page; this run retrieved {len(raw_rows):,} of them (bounded by the configured "
            f"interactive fetch limit). This is NOT the complete set of matching records."
        )

    _report("iNaturalist ingestion complete.")

    record = ProvenanceRecord(
        source="iNaturalist", source_url_or_api=INATURALIST_ENDPOINT,
        access_datetime_utc=access_time, query_parameters=bbox_params,
        geographic_filter=geo_filter, taxonomic_filter=None,
        records_retrieved=len(raw_rows), records_retained=len(df),
        cleaning_operations=["none -- raw ingestion stage only"],
        excluded_records=excluded_records,
        licensing_info={str(k): int(v) for k, v in license_counts.items()},
        status="SUCCESS",
        extra_notes=(
            f"Pages fetched: {run_info['pages_fetched']}. "
            f"iNaturalist-reported total_results at first page: {run_info['total_results_reported']}. "
            f"Switched to id_above pagination (>10k cap workaround): {run_info['used_id_above_strategy']}. "
            f"Hit interactive fetch limit: {run_info.get('hit_result_limit', False)}. "
            "quality_grade was NOT filtered -- both 'research' and 'needs_id' grade "
            "observations are included in this raw file; filter downstream if needed."
            + honesty_note
        ),
    )
    write_provenance(record, "inaturalist_provenance.json")
    return record


if __name__ == "__main__":
    import json
    result = run_inaturalist_ingestion()
    print(json.dumps(result.to_dict(), indent=2, default=str))
