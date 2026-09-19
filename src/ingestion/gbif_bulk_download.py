"""
src/ingestion/gbif_bulk_download.py

GBIF's asynchronous *occurrence download* endpoint -- the correct path
when a bounding box/polygon query exceeds the 100,000-record cap that
`src/ingestion/gbif.py`'s synchronous search-based connector hits (see
that module's `run_gbif_ingestion`, `MAX_OFFSET_CAP`).

WHY THIS IS A SEPARATE MODULE, NOT JUST A BIGGER LIMIT:
The download endpoint is fundamentally asynchronous -- GBIF queues the
request, prepares a file server-side (this can take anywhere from under a
minute to a couple of hours depending on load and result size), and you
poll for completion before downloading a zip file. This is a different
programming model from the synchronous, page-at-a-time search endpoint,
not just "the same thing with a higher limit". Keeping it separate also
means the fast, simple, no-credentials-needed path in `gbif.py` keeps
working unmodified for the common case (fewer than 100k records), which
is expected to be true for a single metropolitan region.

CREDENTIALS REQUIRED (confirmed from pygbif's own docs):
  - GBIF_USER, GBIF_PWD, GBIF_EMAIL environment variables, matching a real,
    free GBIF account (register at https://www.gbif.org/user/profile).
Without these, `request_bulk_download()` correctly returns an UNTESTED
ProvenanceRecord -- the same UNTESTED-without-credentials pattern used elsewhere in this codebase --
rather than fabricating a result.

THIS MODULE ONLY REQUESTS AND POLLS FOR THE DOWNLOAD. It does not
automatically merge the result into the standard schema -- a GBIF
Darwin Core Archive download has a different, richer file layout than the
search API's JSON records, and mapping it into `src/processing/cleaning.py`
is a distinct, not-yet-implemented follow-up step. This is intentionally
scoped, not silently incomplete: see `NOT_IMPLEMENTED` note in
`parse_and_normalise_bulk_download()` below.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from src.config import CONFIG, RAW_DIR, BoundingBox
from src.utils.provenance import ProvenanceRecord, write_provenance, now_utc_iso, untested_connector_record

try:
    from pygbif import occurrences
    PYGBIF_AVAILABLE = True
except ImportError:
    PYGBIF_AVAILABLE = False

GBIF_DOWNLOAD_ENDPOINT = "https://api.gbif.org/v1/occurrence/download"
CREDENTIAL_ENV_VARS = ("GBIF_USER", "GBIF_PWD", "GBIF_EMAIL")


def _build_geometry_predicate(bbox: BoundingBox) -> str:
    if bbox.polygon_wkt:
        return f"geometry = {bbox.polygon_wkt}"
    # GBIF's download predicate language does not accept a decimalLatitude/
    # decimalLongitude RANGE the way the search endpoint's params do -- a
    # bounding rectangle must be expressed as a WKT polygon here instead.
    wkt = (
        f"POLYGON(({bbox.min_lon} {bbox.min_lat}, {bbox.max_lon} {bbox.min_lat}, "
        f"{bbox.max_lon} {bbox.max_lat}, {bbox.min_lon} {bbox.max_lat}, "
        f"{bbox.min_lon} {bbox.min_lat}))"
    )
    return f"geometry = {wkt}"


def request_bulk_download(bbox: Optional[BoundingBox] = None,
                           country: Optional[str] = None,
                           poll: bool = True,
                           poll_interval_seconds: int = 30,
                           poll_timeout_seconds: int = 3600) -> ProvenanceRecord:
    """
    Submit a GBIF asynchronous occurrence-download request for the
    configured bounding box/polygon, and (if poll=True) wait for it to
    finish and download the resulting zip to data/raw/.

    Returns UNTESTED if credentials are missing (never attempted), FAILED
    on any real submission/polling/download error, SUCCESS once the file
    is actually downloaded. If poll=False, returns SUCCESS with the
    download key recorded so you can check on it later with
    check_download_status() -- useful since a real download can take a
    long time and you may not want this function to block.
    """
    bbox = bbox or CONFIG.bbox
    country = country if country is not None else CONFIG.country_filter
    access_time = now_utc_iso()
    predicate = _build_geometry_predicate(bbox)
    queries = [predicate]
    if country:
        queries.append(f"country = {country}")

    geo_filter = {"bbox": {"min_lat": bbox.min_lat, "max_lat": bbox.max_lat,
                            "min_lon": bbox.min_lon, "max_lon": bbox.max_lon},
                  "is_official_polygon": bbox.is_official_polygon,
                  "polygon_wkt_configured": bool(bbox.polygon_wkt)}
    query_params = {"predicate_queries": queries, "format": "SIMPLE_CSV"}

    missing = [v for v in CREDENTIAL_ENV_VARS if not os.environ.get(v)]
    if missing:
        record = untested_connector_record(
            source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
            query_parameters=query_params, geographic_filter=geo_filter,
            reason=(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                f"Register a free account at https://www.gbif.org/user/profile and set "
                f"GBIF_USER, GBIF_PWD, GBIF_EMAIL before requesting a bulk download. "
                f"This was never attempted -- not a network failure."
            ),
        )
        write_provenance(record, "gbif_bulk_download_provenance.json")
        return record

    if not PYGBIF_AVAILABLE:
        record = ProvenanceRecord(
            source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail="pygbif is not installed.",
        )
        write_provenance(record, "gbif_bulk_download_provenance.json")
        return record

    try:
        result = occurrences.download(queries, format="SIMPLE_CSV", pred_type="and")
        # pygbif's download() returns a list like [download_key, ...]; be defensive.
        download_key = result[0] if isinstance(result, (list, tuple)) else result
    except Exception as exc:  # noqa: BLE001
        record = ProvenanceRecord(
            source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail=f"{type(exc).__name__}: {exc}",
            extra_notes="Failed while submitting the download request itself. No fallback data generated.",
        )
        write_provenance(record, "gbif_bulk_download_provenance.json")
        return record

    if not poll:
        record = ProvenanceRecord(
            source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="SUCCESS",
            extra_notes=(
                f"Download request SUBMITTED (key={download_key}) but NOT polled to completion "
                f"(poll=False). Call check_download_status({download_key!r}) later, or re-run "
                f"with poll=True. A real GBIF bulk download can take from under a minute to "
                f"several hours depending on GBIF's queue and result size."
            ),
        )
        write_provenance(record, "gbif_bulk_download_provenance.json")
        return record

    return _poll_and_download(download_key, access_time, query_params, geo_filter,
                               poll_interval_seconds, poll_timeout_seconds)


def _poll_and_download(download_key: str, access_time: str, query_params: dict,
                        geo_filter: dict, poll_interval_seconds: int,
                        poll_timeout_seconds: int) -> ProvenanceRecord:
    waited = 0
    try:
        while waited < poll_timeout_seconds:
            meta = occurrences.download_meta(key=download_key)
            status = meta.get("status")
            if status == "SUCCEEDED":
                break
            if status in ("KILLED", "FAILED", "CANCELLED"):
                record = ProvenanceRecord(
                    source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
                    access_datetime_utc=access_time, query_parameters=query_params,
                    geographic_filter=geo_filter, taxonomic_filter=None,
                    records_retrieved=0, records_retained=0, cleaning_operations=[],
                    excluded_records=[], licensing_info=None, status="FAILED",
                    error_detail=f"GBIF reported download status={status} for key={download_key}.",
                )
                write_provenance(record, "gbif_bulk_download_provenance.json")
                return record
            time.sleep(poll_interval_seconds)
            waited += poll_interval_seconds

        if waited >= poll_timeout_seconds:
            record = ProvenanceRecord(
                source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
                access_datetime_utc=access_time, query_parameters=query_params,
                geographic_filter=geo_filter, taxonomic_filter=None,
                records_retrieved=0, records_retained=0, cleaning_operations=[],
                excluded_records=[], licensing_info=None, status="FAILED",
                error_detail=(
                    f"Timed out after {poll_timeout_seconds}s waiting for download "
                    f"key={download_key} to complete. It may still finish later -- check "
                    f"manually with check_download_status({download_key!r})."
                ),
            )
            write_provenance(record, "gbif_bulk_download_provenance.json")
            return record

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        occurrences.download_get(key=download_key, path=str(RAW_DIR))
    except Exception as exc:  # noqa: BLE001
        record = ProvenanceRecord(
            source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
            access_datetime_utc=access_time, query_parameters=query_params,
            geographic_filter=geo_filter, taxonomic_filter=None,
            records_retrieved=0, records_retained=0, cleaning_operations=[],
            excluded_records=[], licensing_info=None, status="FAILED",
            error_detail=f"{type(exc).__name__}: {exc}",
            extra_notes=f"Failed while polling/downloading key={download_key}.",
        )
        write_provenance(record, "gbif_bulk_download_provenance.json")
        return record

    zip_path = RAW_DIR / f"{download_key}.zip"
    record = ProvenanceRecord(
        source="GBIF (bulk download)", source_url_or_api=GBIF_DOWNLOAD_ENDPOINT,
        access_datetime_utc=access_time, query_parameters=query_params,
        geographic_filter=geo_filter, taxonomic_filter=None,
        records_retrieved=None, records_retained=None,  # unknown until the archive is parsed -- see module docstring
        cleaning_operations=[],
        excluded_records=[],
        licensing_info="Per-record licenses included inside the downloaded Darwin Core Archive; not yet parsed.",
        status="SUCCESS",
        extra_notes=(
            f"Download key={download_key} downloaded to {zip_path}. Record count is unknown "
            f"until the archive is parsed -- parsing/normalising this format is NOT_IMPLEMENTED "
            f"yet (see module docstring). Use occurrences.download_meta(key={download_key!r}) "
            f"for GBIF's own reported record count in the meantime."
        ),
    )
    write_provenance(record, "gbif_bulk_download_provenance.json")
    return record


def check_download_status(download_key: str) -> dict:
    """Thin wrapper for checking on a previously-submitted download without
    re-submitting it. Raises if pygbif isn't installed or the API call fails
    -- callers should handle that, this is a diagnostic helper, not part of
    the main ingestion contract."""
    if not PYGBIF_AVAILABLE:
        raise ImportError("pygbif is not installed.")
    return occurrences.download_meta(key=download_key)


def parse_and_normalise_bulk_download(zip_path: Path):
    """NOT_IMPLEMENTED. A GBIF Darwin Core Archive download has a
    different file layout (multiple TSV/CSV files plus an EML metadata
    file inside the zip) than the search API's JSON records that
    src/processing/cleaning.py::normalise_gbif() expects. Mapping it into
    the standard schema is a distinct piece of work, deliberately not
    guessed at here."""
    raise NotImplementedError(
        "Parsing a GBIF bulk-download archive into the standard schema is not yet "
        "implemented. See this function's docstring for why, and "
        "src/processing/cleaning.py::normalise_gbif for the target schema it would "
        "need to map into."
    )


if __name__ == "__main__":
    import json
    result = request_bulk_download(poll=False)
    print(json.dumps(result.to_dict(), indent=2, default=str))
