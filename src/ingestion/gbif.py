"""
src/ingestion/gbif.py

Real GBIF occurrence ingestion connector. Uses the official GBIF REST API
v1 via the `pygbif` client. This is the connector previously developed and
mock-tested as `fetch_gbif_mmr.py`; the logic is unchanged, just refactored
to fit the BIOGAP package structure and to use src.config / src.utils.provenance.

This module DOES attempt a real network call when run. In an environment
without access to api.gbif.org, it will fail honestly (status="FAILED",
with the real exception recorded) rather than falling back to fabricated
data.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from src.config import CONFIG, RAW_DIR, BoundingBox
from src.utils.provenance import ProvenanceRecord, write_provenance, now_utc_iso

try:
    from pygbif import occurrences, registry
    PYGBIF_AVAILABLE = True
except ImportError:
    PYGBIF_AVAILABLE = False

GBIF_ENDPOINT = "https://api.gbif.org/v1/occurrence/search"

RAW_FIELDS = [
    "gbif_key", "occurrenceID", "species", "scientificName", "kingdom",
    "phylum", "class", "order", "family", "genus", "decimalLatitude",
    "decimalLongitude", "eventDate", "year", "basisOfRecord", "datasetKey",
    "publishingOrgKey", "occurrenceStatus", "license", "has_media", "media_count",
]


def build_query_params(bbox: BoundingBox, country: Optional[str]) -> dict:
    params = bbox.as_gbif_params()
    if country:
        params["country"] = country
    return params


def _fetch_all_records(query_params: dict, page_size: int, max_offset: int,
                        delay: float, max_records: Optional[int] = None,
                        on_progress: Optional[Callable[[str], None]] = None,
                        ) -> tuple[list[dict], dict]:
    """
    Returns (records, run_info). Raises on unrecoverable API failure.

    max_records: if set, stops fetching once at least this many records
    have been retrieved (after finishing the page in progress -- never a
    partial page). This is the INTERACTIVE bound; it is independent of
    max_offset, which remains GBIF's absolute API ceiling. Hitting this
    bound is recorded honestly in run_info["hit_interactive_limit"] and is
    never treated as if it means "this is all the matching data".

    on_progress: optional callback invoked with short human-readable
    status strings as fetching proceeds, so a caller (e.g. the Streamlit
    UI) can render live progress instead of one long silent block.
    """

    def _report(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    all_results: list[dict] = []
    offset = 0
    total_count = None
    run_info = {"pages_fetched": 0, "hit_offset_cap": False, "hit_interactive_limit": False}

    _report("Connecting to GBIF...")

    while True:
        if offset > max_offset:
            run_info["hit_offset_cap"] = True
            break
        if max_records is not None and len(all_results) >= max_records:
            run_info["hit_interactive_limit"] = True
            break

        attempt = 0
        while True:
            attempt += 1
            try:
                page = occurrences.search(offset=offset, **query_params, limit=page_size)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt >= 3:
                    raise
                _report(f"GBIF request failed (attempt {attempt}/3), retrying...")
                time.sleep(2 ** attempt)

        if total_count is None:
            total_count = page.get("count")
            _report(f"GBIF connection successful. GBIF reports {total_count:,} matching records."
                    if total_count is not None else "GBIF connection successful.")
        results = page.get("results", [])
        all_results.extend(results)
        run_info["pages_fetched"] += 1
        _report(f"Fetched {len(all_results):,} records so far "
                f"(page {run_info['pages_fetched']})...")

        if page.get("endOfRecords", True) or not results:
            break
        offset += page_size
        time.sleep(delay)

    run_info["total_count_reported_by_gbif"] = total_count
    return all_results, run_info


def _extract_fields(raw_records: list[dict]) -> pd.DataFrame:
    rows = []
    for rec in raw_records:
        media = rec.get("media")
        if media is None:
            has_media, media_count = "UNKNOWN", pd.NA
        else:
            has_media, media_count = bool(len(media) > 0), len(media)
        rows.append({
            "gbif_key": rec.get("key", pd.NA),
            "occurrenceID": rec.get("occurrenceID", pd.NA),
            "species": rec.get("species", pd.NA),
            "scientificName": rec.get("scientificName", pd.NA),
            "kingdom": rec.get("kingdom", pd.NA),
            "phylum": rec.get("phylum", pd.NA),
            "class": rec.get("class", pd.NA),
            "order": rec.get("order", pd.NA),
            "family": rec.get("family", pd.NA),
            "genus": rec.get("genus", pd.NA),
            "decimalLatitude": rec.get("decimalLatitude", pd.NA),
            "decimalLongitude": rec.get("decimalLongitude", pd.NA),
            "eventDate": rec.get("eventDate", pd.NA),
            "year": rec.get("year", pd.NA),
            "basisOfRecord": rec.get("basisOfRecord", pd.NA),
            "datasetKey": rec.get("datasetKey", pd.NA),
            "publishingOrgKey": rec.get("publishingOrgKey", pd.NA),
            "occurrenceStatus": rec.get("occurrenceStatus", pd.NA),
            "license": rec.get("license", pd.NA),
            "has_media": has_media,
            "media_count": media_count,
        })
    return pd.DataFrame(rows, columns=RAW_FIELDS)


def run_gbif_ingestion(bbox: Optional[BoundingBox] = None,
                        country: Optional[str] = None,
                        page_size: Optional[int] = None,
                        max_offset: Optional[int] = None,
                        delay: Optional[float] = None,
                        max_records: Optional[int] = None,
                        on_progress: Optional[Callable[[str], None]] = None,
                        raw_output_name: str = "gbif_raw.csv") -> ProvenanceRecord:
    """
    Run a real GBIF ingestion against the configured bounding box.
    Writes the raw CSV to data/raw/<raw_output_name> (never modified after
    writing) and a provenance JSON to data/metadata/.

    max_records defaults to CONFIG.gbif_interactive_record_limit (a
    conservative bound sized for a single interactive Streamlit run, NOT
    all matching records). Pass max_records=None explicitly together with
    a raised max_offset for a full/bulk run (e.g. from the CLI); see
    src/ingestion/gbif_bulk_download.py for the asynchronous path needed
    once results exceed GBIF's 100,000-record search-API ceiling.

    Returns the ProvenanceRecord (also written to disk). Never raises past
    this function for a network/API failure -- the failure is captured in
    the returned record's status/error_detail instead, so callers (e.g. the
    Streamlit app) can display it honestly rather than crashing.
    """
    bbox = bbox or CONFIG.bbox
    country = country if country is not None else CONFIG.country_filter
    page_size = page_size or CONFIG.gbif_page_size
    max_offset = max_offset or CONFIG.gbif_max_offset
    delay = delay if delay is not None else CONFIG.request_delay_seconds
    if max_records is None:
        max_records = CONFIG.gbif_interactive_record_limit

    def _report(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    query_params = build_query_params(bbox, country)
    access_time = now_utc_iso()
    geo_filter = {"bbox": {"min_lat": bbox.min_lat, "max_lat": bbox.max_lat,
                            "min_lon": bbox.min_lon, "max_lon": bbox.max_lon},
                  "is_official_polygon": bbox.is_official_polygon}

    if not PYGBIF_AVAILABLE:
        _report("pygbif is not installed -- cannot connect to GBIF.")
        record = ProvenanceRecord(
            source="GBIF", source_url_or_api=GBIF_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail="pygbif is not installed. Run: pip install -r requirements.txt",
        )
        write_provenance(record, "gbif_provenance.json")
        return record

    try:
        raw_records, run_info = _fetch_all_records(
            query_params, page_size, max_offset, delay,
            max_records=max_records, on_progress=_report,
        )
    except Exception as exc:  # noqa: BLE001
        _report(f"GBIF ingestion failed: {type(exc).__name__}: {exc}")
        record = ProvenanceRecord(
            source="GBIF", source_url_or_api=GBIF_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail=f"{type(exc).__name__}: {exc}",
            extra_notes="No fallback/synthetic data was generated. See SETUP.md troubleshooting section.",
        )
        write_provenance(record, "gbif_provenance.json")
        return record

    if not raw_records:
        _report("GBIF query succeeded but returned zero records for this bounding box.")
        record = ProvenanceRecord(
            source="GBIF", source_url_or_api=GBIF_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="SUCCESS",
            extra_notes="Query succeeded but returned zero records for this bounding box.",
        )
        write_provenance(record, "gbif_provenance.json")
        return record

    _report("Cleaning observations...")
    df = _extract_fields(raw_records)
    _report("Saving verified dataset...")
    raw_path = RAW_DIR / raw_output_name
    df.to_csv(raw_path, index=False)

    license_counts = df["license"].fillna("MISSING").value_counts().to_dict()

    total_reported = run_info.get("total_count_reported_by_gbif")
    honesty_note = ""
    if run_info.get("hit_interactive_limit") and total_reported is not None and total_reported > len(df):
        honesty_note = (
            f" GBIF reports {total_reported:,} matching observations in total; this "
            f"interactive run retrieved {len(df):,} of them (bounded by the configured "
            f"interactive fetch limit so the request finishes reliably). This is NOT the "
            f"complete set of matching GBIF records."
        )
    elif run_info.get("hit_offset_cap"):
        honesty_note = (
            " Hit GBIF's 100,000-record search-API offset cap before finishing -- to "
            "retrieve the remainder, use src/ingestion/gbif_bulk_download.py::"
            "request_bulk_download() (GBIF's asynchronous download endpoint, requires a "
            "free GBIF account)."
        )

    _report("GBIF ingestion complete.")

    record = ProvenanceRecord(
        source="GBIF", source_url_or_api=GBIF_ENDPOINT,
        access_datetime_utc=access_time, query_parameters=query_params,
        geographic_filter=geo_filter, taxonomic_filter=None,
        records_retrieved=len(raw_records), records_retained=len(df),
        cleaning_operations=["none -- this is the raw ingestion stage; see src/processing/cleaning.py for the separate cleaning stage"],
        excluded_records=[], licensing_info={str(k): int(v) for k, v in license_counts.items()},
        status="SUCCESS",
        extra_notes=f"Pages fetched: {run_info['pages_fetched']}. "
                    f"GBIF-reported total matching records: {total_reported}. "
                    f"Hit 100k offset cap: {run_info['hit_offset_cap']}. "
                    f"Hit interactive fetch limit: {run_info.get('hit_interactive_limit', False)}."
                    + honesty_note,
    )
    write_provenance(record, "gbif_provenance.json")
    return record


if __name__ == "__main__":
    import json
    result = run_gbif_ingestion()
    print(json.dumps(result.to_dict(), indent=2, default=str))
