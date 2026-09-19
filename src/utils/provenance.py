"""
src/utils/provenance.py

Every ingestion run, from every source, must record a provenance record
with this same structure, so DATA_PROVENANCE.md's claims are enforced in
code rather than just documented in prose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.config import METADATA_DIR


@dataclass
class ProvenanceRecord:
    source: str                          # "GBIF" | "iNaturalist" (or a future added source)
    source_url_or_api: str
    access_datetime_utc: str
    query_parameters: dict
    geographic_filter: dict
    taxonomic_filter: Optional[dict]
    records_retrieved: int
    records_retained: int
    cleaning_operations: list
    excluded_records: list              # list of {"reason": ..., "count": ...}
    licensing_info: Any
    status: str                          # "SUCCESS" | "FAILED" | "UNTESTED"
    error_detail: Optional[str] = None
    extra_notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_provenance(record: ProvenanceRecord, filename: str) -> Path:
    """
    Write a provenance record to data/metadata/<filename>.json.
    Never overwrites silently -- if the file exists, a numeric suffix is
    added, so historical provenance records are never lost.
    """
    path = METADATA_DIR / filename
    if path.exists():
        stem, suffix = path.stem, path.suffix
        n = 1
        while (METADATA_DIR / f"{stem}_{n}{suffix}").exists():
            n += 1
        path = METADATA_DIR / f"{stem}_{n}{suffix}"
    path.write_text(json.dumps(record.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


def untested_connector_record(source: str, source_url_or_api: str,
                               query_parameters: dict, geographic_filter: dict,
                               reason: str) -> ProvenanceRecord:
    """
    Standard way for a connector to honestly report that it could not be
    run against the live API in the current environment. Per project
    rules: never pretend a connector worked when it didn't.
    """
    return ProvenanceRecord(
        source=source,
        source_url_or_api=source_url_or_api,
        access_datetime_utc=now_utc_iso(),
        query_parameters=query_parameters,
        geographic_filter=geographic_filter,
        taxonomic_filter=None,
        records_retrieved=0,
        records_retained=0,
        cleaning_operations=[],
        excluded_records=[],
        licensing_info=None,
        status="UNTESTED",
        error_detail=reason,
        extra_notes=(
            "This connector was built and code-reviewed against the source's "
            "official API documentation but has NOT been executed against the "
            "live API in this environment. No data was fabricated. Run it "
            "yourself in an environment with network access to verify it."
        ),
    )
