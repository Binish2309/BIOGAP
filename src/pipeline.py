"""
src/pipeline.py

Orchestrates the real pipeline: run a source's ingestion connector ->
normalise into the standard schema -> concatenate with every other
source's most recently retained real data -> clean -> write
data/processed/combined_standard.csv (+ per-source normalised files) ->
write a combined run-summary JSON to data/metadata/.

STAGED DESIGN (see RESEARCH_METHOD.md / SETUP.md for the rationale):
Running all three sources' connectors back-to-back inside one blocking
call could take many minutes (GBIF's search API alone can require
dozens of sequential paginated requests, and iNaturalist's pagination
had no enforced upper bound), which is unreliable on Streamlit Cloud --
the UI has nothing to show while it's blocked, and a long silent block
can look like the browser losing its connection to the app.

run_source_pipeline() is the primary entry point now: it runs exactly
ONE source, reports progress as it goes (via on_progress), and then
recombines that source's fresh data with the OTHER source's most
recently and successfully retrieved result (tracked in latest_source_state.json,
independent from the full historical provenance log in data/metadata/,
which is never overwritten -- see src/utils/provenance.py). This means:
  - The first-ever run only needs GBIF to succeed to produce a usable
    combined_standard.csv and unlock every analysis page.
  - Running iNaturalist later ADDS to the combined dataset
    rather than replacing it, and a later source failing never erases
    an earlier source's successfully retained data.

run_full_pipeline() (both sources back-to-back) is kept for CLI /
non-interactive use (`python -m src.pipeline`), and shares the exact
same recombination logic, so the UI and CLI cannot silently drift apart.

No step here fabricates data. Any source that fails or is untested
contributes zero rows to the combined dataset and its status is
preserved in the run summary and surfaced by the UI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from src.config import CONFIG, PROCESSED_DIR, METADATA_DIR, RAW_DIR
from src.ingestion.gbif import run_gbif_ingestion
from src.ingestion.inaturalist import run_inaturalist_ingestion
from src.processing.cleaning import normalise_gbif, normalise_inaturalist, clean_standard_frame
from src.processing.schema import empty_standard_frame, STANDARD_COLUMNS
from src.utils.provenance import ProvenanceRecord

COMBINED_PROCESSED_PATH = PROCESSED_DIR / "combined_standard.csv"
RUN_SUMMARY_PATH = METADATA_DIR / "pipeline_run_summary.json"
# Distinct from the historical, never-overwritten provenance JSONs written
# by src/utils/provenance.py::write_provenance -- this file intentionally
# IS overwritten every run. It exists purely so a single-source ingestion
# knows what the OTHER sources' most recent successful result was, without
# re-running them. Full audit history still lives in the numbered
# gbif_provenance*.json / inaturalist_provenance*.json files, untouched by this file.
LATEST_SOURCE_STATE_PATH = METADATA_DIR / "latest_source_state.json"

# eBird was deliberately removed from this pipeline -- see RESEARCH_METHOD.md
# ("Why eBird was removed") for the reasoning: its public API only offers
# recent (<=30 day), radius-based observations (not the historical,
# bounding-box data GBIF/iNaturalist provide), and needs a separately-
# requested API key, for comparatively little research value over the two
# remaining multi-taxon sources.
SOURCE_KEYS = ("gbif", "inaturalist")
DISPLAY_NAMES = {"gbif": "GBIF", "inaturalist": "iNaturalist"}
RAW_FILENAMES = {"gbif": "gbif_raw.csv", "inaturalist": "inaturalist_raw.csv"}
INGESTION_FUNCS = {"gbif": run_gbif_ingestion, "inaturalist": run_inaturalist_ingestion}
NORMALISERS = {"gbif": normalise_gbif, "inaturalist": normalise_inaturalist}


def load_latest_source_state() -> dict:
    """dict of source_key -> last-known ProvenanceRecord dict (or absent if never attempted)."""
    if not LATEST_SOURCE_STATE_PATH.exists():
        return {}
    try:
        return json.loads(LATEST_SOURCE_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_latest_source_state(state: dict) -> None:
    LATEST_SOURCE_STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _recombine(state: dict) -> tuple[pd.DataFrame, dict, str]:
    """
    Build the combined, cleaned standard-schema DataFrame from every
    source's most recent SUCCESSFUL, non-empty raw file recorded in
    `state` (a dict as returned by load_latest_source_state()). A source
    missing from `state`, or recorded as FAILED/UNTESTED/zero-retained,
    simply contributes nothing -- it never blocks the other sources'
    data from being combined. Returns (cleaned_df, cleaning_report,
    data_status).
    """
    normalised_frames = []
    for key in SOURCE_KEYS:
        prov = state.get(key)
        if not prov:
            continue
        if prov.get("status") != "SUCCESS" or prov.get("records_retained", 0) <= 0:
            continue
        raw_csv = RAW_DIR / RAW_FILENAMES[key]
        if not raw_csv.exists():
            continue
        normalised_frames.append(NORMALISERS[key](pd.read_csv(raw_csv)))

    if normalised_frames:
        aligned = [f.reindex(columns=list(set(STANDARD_COLUMNS) | set(f.columns))) for f in normalised_frames]
        combined_raw_normalised = pd.concat(aligned, ignore_index=True, sort=False)
        cleaned, cleaning_report = clean_standard_frame(combined_raw_normalised)
        cleaned.to_csv(COMBINED_PROCESSED_PATH, index=False)
        data_status = "REAL_DATA_AVAILABLE"
    else:
        cleaned = empty_standard_frame()
        cleaned.to_csv(COMBINED_PROCESSED_PATH, index=False)
        cleaning_report = {"note": "No source has any retained records yet; nothing to clean."}
        data_status = "NO_REAL_DATA_YET"

    return cleaned, cleaning_report, data_status


def _write_summary(run_started: str, sources_this_run: list[str], state: dict,
                    cleaned: pd.DataFrame, cleaning_report: dict, data_status: str) -> dict:
    provenance_by_source = {DISPLAY_NAMES[k]: state[k] for k in SOURCE_KEYS if k in state}
    summary = {
        "pipeline_run_started_utc": run_started,
        "pipeline_run_finished_utc": datetime.now(timezone.utc).isoformat(),
        "sources_attempted_this_run": sources_this_run,
        "sources_in_combined_dataset": [
            DISPLAY_NAMES[k] for k in SOURCE_KEYS
            if state.get(k, {}).get("status") == "SUCCESS" and state.get(k, {}).get("records_retained", 0) > 0
        ],
        "provenance_by_source": provenance_by_source,
        "cleaning_report": cleaning_report,
        "combined_row_count": int(len(cleaned)),
        "data_status": data_status,
        "combined_processed_path": str(COMBINED_PROCESSED_PATH),
    }
    RUN_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def run_source_pipeline(source: str, on_progress: Optional[Callable[[str], None]] = None,
                         **ingestion_kwargs) -> dict:
    """
    Run ingestion for exactly ONE source (source in SOURCE_KEYS), then
    recombine the processed dataset using this source's fresh result
    together with every other source's last known successful result (if
    any). This is the function the Streamlit "Fetch GBIF observations" /
    "Add iNaturalist observations" buttons call.

    on_progress: optional callback forwarded to the connector, invoked
    with short human-readable status strings (e.g. "Fetching page
    3...") so the UI can show live progress instead of one long block.

    ingestion_kwargs: forwarded to the source's run_<source>_ingestion()
    function (e.g. max_records=... to override the interactive default).

    Returns the same run-summary shape as run_full_pipeline().
    """
    if source not in SOURCE_KEYS:
        raise ValueError(f"Unknown source {source!r}; expected one of {SOURCE_KEYS}")

    run_started = datetime.now(timezone.utc).isoformat()
    state = load_latest_source_state()

    prov: ProvenanceRecord = INGESTION_FUNCS[source](on_progress=on_progress, **ingestion_kwargs)
    state[source] = prov.to_dict()
    _save_latest_source_state(state)

    cleaned, cleaning_report, data_status = _recombine(state)
    return _write_summary(run_started, [source], state, cleaned, cleaning_report, data_status)


def run_full_pipeline(sources: list[str] | None = None,
                       on_progress: Optional[Callable[[str, str], None]] = None) -> dict:
    """
    Run every source in `sources` (default: both) back-to-back, in
    one call. Intended for CLI / non-interactive use
    (`python -m src.pipeline`); the Streamlit UI uses the staged
    run_source_pipeline() instead so a single source's result is visible
    without waiting for the others.

    on_progress, if given, is called as on_progress(source_key, message)
    so a caller can distinguish which source a progress message is about.

    Shares _recombine()/_write_summary() with run_source_pipeline(), so
    the two code paths cannot silently produce different combined
    datasets from the same underlying per-source state.
    """
    sources = sources or list(SOURCE_KEYS)
    run_started = datetime.now(timezone.utc).isoformat()
    state = load_latest_source_state()

    for key in sources:
        if key not in SOURCE_KEYS:
            raise ValueError(f"Unknown source {key!r}; expected one of {SOURCE_KEYS}")
        cb = (lambda msg, _k=key: on_progress(_k, msg)) if on_progress is not None else None
        prov: ProvenanceRecord = INGESTION_FUNCS[key](on_progress=cb)
        state[key] = prov.to_dict()
        _save_latest_source_state(state)

    cleaned, cleaning_report, data_status = _recombine(state)
    return _write_summary(run_started, sources, state, cleaned, cleaning_report, data_status)


if __name__ == "__main__":
    def _print_progress(source_key: str, message: str) -> None:
        print(f"  [{DISPLAY_NAMES[source_key]}] {message}")

    result = run_full_pipeline(on_progress=_print_progress)
    print(json.dumps({k: v for k, v in result.items() if k != "provenance_by_source"}, indent=2, default=str))
    print(f"\nData status: {result['data_status']}")
    for source, prov in result["provenance_by_source"].items():
        print(f"  {source}: status={prov['status']}, retained={prov['records_retained']}")
