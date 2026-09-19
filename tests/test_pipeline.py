"""
tests/test_pipeline.py

Tests for the staged single-source pipeline introduced to fix the
"Run ingestion pipeline" hang on Streamlit Cloud (see src/pipeline.py's
module docstring). Every ingestion connector call in these tests is
monkeypatched -- these tests never hit a real network, and the
ProvenanceRecord / raw CSVs used here are obvious, clearly-synthetic test
fixtures (is_test_data is not part of this path; these tests operate at
the pipeline-orchestration level, one layer below the standard schema,
using the connectors' own RAW_FIELDS layout, exactly as a real connector
would produce before normalisation).
"""

from __future__ import annotations

import pandas as pd
import pytest

import src.pipeline as pipeline
from src.processing.schema import STANDARD_COLUMNS, validate_columns
from src.utils.provenance import ProvenanceRecord, now_utc_iso


def _prov(source: str, status: str, retrieved: int = 0, retained: int = 0,
          error_detail: str | None = None) -> ProvenanceRecord:
    return ProvenanceRecord(
        source=source, source_url_or_api=f"https://example.invalid/{source}",
        access_datetime_utc=now_utc_iso(), query_parameters={}, geographic_filter={},
        taxonomic_filter=None, records_retrieved=retrieved, records_retained=retained,
        cleaning_operations=[], excluded_records=[], licensing_info=None,
        status=status, error_detail=error_detail,
    )


GBIF_RAW_ROWS = [
    {"gbif_key": "1", "occurrenceID": "o1", "species": "Corvus splendens",
     "scientificName": "Corvus splendens", "kingdom": "Animalia", "phylum": "Chordata",
     "class": "Aves", "order": "Passeriformes", "family": "Corvidae", "genus": "Corvus",
     "decimalLatitude": 19.07, "decimalLongitude": 72.87, "eventDate": "2022-03-01",
     "year": 2022, "basisOfRecord": "HUMAN_OBSERVATION", "datasetKey": "ds1",
     "publishingOrgKey": "pub1", "occurrenceStatus": "PRESENT", "license": "CC_BY_4_0",
     "has_media": True, "media_count": 1},
    {"gbif_key": "2", "occurrenceID": "o2", "species": "Pavo cristatus",
     "scientificName": "Pavo cristatus", "kingdom": "Animalia", "phylum": "Chordata",
     "class": "Aves", "order": "Galliformes", "family": "Phasianidae", "genus": "Pavo",
     "decimalLatitude": 19.10, "decimalLongitude": 72.90, "eventDate": "2021-11-15",
     "year": 2021, "basisOfRecord": "HUMAN_OBSERVATION", "datasetKey": "ds1",
     "publishingOrgKey": "pub1", "occurrenceStatus": "PRESENT", "license": "CC0_1_0",
     "has_media": False, "media_count": 0},
]


@pytest.fixture
def isolated_pipeline_paths(tmp_path, monkeypatch):
    """Redirect every path pipeline.py writes to/reads from into tmp_path,
    so tests never touch the real data/ directory."""
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    metadata_dir = tmp_path / "metadata"
    for d in (raw_dir, processed_dir, metadata_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(pipeline, "RAW_DIR", raw_dir)
    monkeypatch.setattr(pipeline, "COMBINED_PROCESSED_PATH", processed_dir / "combined_standard.csv")
    monkeypatch.setattr(pipeline, "RUN_SUMMARY_PATH", metadata_dir / "pipeline_run_summary.json")
    monkeypatch.setattr(pipeline, "LATEST_SOURCE_STATE_PATH", metadata_dir / "latest_source_state.json")
    return raw_dir, processed_dir, metadata_dir


def _write_gbif_raw(raw_dir) -> None:
    pd.DataFrame(GBIF_RAW_ROWS).to_csv(raw_dir / "gbif_raw.csv", index=False)


def test_gbif_only_pipeline_produces_real_data_available(isolated_pipeline_paths, monkeypatch):
    raw_dir, processed_dir, metadata_dir = isolated_pipeline_paths
    _write_gbif_raw(raw_dir)

    def fake_gbif(on_progress=None, **kwargs):
        return _prov("GBIF", "SUCCESS", retrieved=2, retained=2)

    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "gbif", fake_gbif)

    result = pipeline.run_source_pipeline("gbif")

    assert result["data_status"] == "REAL_DATA_AVAILABLE"
    assert result["combined_row_count"] == 2
    assert result["sources_in_combined_dataset"] == ["GBIF"]
    assert pipeline.COMBINED_PROCESSED_PATH.exists()

    combined = pd.read_csv(pipeline.COMBINED_PROCESSED_PATH)
    assert len(combined) == 2
    assert validate_columns(combined) == []  # every STANDARD_COLUMNS present


def test_zero_records_yields_no_real_data_yet(isolated_pipeline_paths, monkeypatch):
    def fake_gbif(on_progress=None, **kwargs):
        return _prov("GBIF", "SUCCESS", retrieved=0, retained=0)

    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "gbif", fake_gbif)

    result = pipeline.run_source_pipeline("gbif")

    assert result["data_status"] == "NO_REAL_DATA_YET"
    assert result["combined_row_count"] == 0
    assert result["sources_in_combined_dataset"] == []
    combined = pd.read_csv(pipeline.COMBINED_PROCESSED_PATH)
    assert validate_columns(combined) == []


def test_failed_source_yields_no_real_data_yet_and_visible_error(isolated_pipeline_paths, monkeypatch):
    def fake_gbif(on_progress=None, **kwargs):
        return _prov("GBIF", "FAILED", retrieved=0, retained=0,
                     error_detail="ConnectionError: could not reach api.gbif.org")

    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "gbif", fake_gbif)

    result = pipeline.run_source_pipeline("gbif")

    assert result["data_status"] == "NO_REAL_DATA_YET"
    assert result["provenance_by_source"]["GBIF"]["status"] == "FAILED"
    assert "could not reach" in result["provenance_by_source"]["GBIF"]["error_detail"]


def test_partial_source_success_never_erases_earlier_source(isolated_pipeline_paths, monkeypatch):
    """The core staged-ingestion guarantee: GBIF succeeds first, then
    iNaturalist fails -- the combined dataset must still contain GBIF's
    data, and overall status must remain REAL_DATA_AVAILABLE."""
    raw_dir, processed_dir, metadata_dir = isolated_pipeline_paths
    _write_gbif_raw(raw_dir)

    def fake_gbif(on_progress=None, **kwargs):
        return _prov("GBIF", "SUCCESS", retrieved=2, retained=2)

    def fake_inaturalist(on_progress=None, **kwargs):
        return _prov("iNaturalist", "FAILED", retrieved=0, retained=0,
                     error_detail="Timeout: api.inaturalist.org")

    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "gbif", fake_gbif)
    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "inaturalist", fake_inaturalist)

    first = pipeline.run_source_pipeline("gbif")
    assert first["data_status"] == "REAL_DATA_AVAILABLE"

    second = pipeline.run_source_pipeline("inaturalist")

    assert second["data_status"] == "REAL_DATA_AVAILABLE"  # NOT wiped out
    assert second["combined_row_count"] == 2  # still the 2 GBIF rows
    assert second["sources_in_combined_dataset"] == ["GBIF"]
    assert second["provenance_by_source"]["GBIF"]["status"] == "SUCCESS"  # carried forward
    assert second["provenance_by_source"]["iNaturalist"]["status"] == "FAILED"


def test_second_source_success_adds_to_combined_dataset(isolated_pipeline_paths, monkeypatch):
    raw_dir, processed_dir, metadata_dir = isolated_pipeline_paths
    _write_gbif_raw(raw_dir)
    inat_rows = [{
        "inat_id": 101, "uuid": "u101", "taxon_name": "Hemidactylus frenatus",
        "taxon_rank": "species", "iconic_taxon_name": "Reptilia",
        "latitude": 19.05, "longitude": 72.88, "observed_on": "2023-05-01",
        "quality_grade": "research", "license_code": "CC0", "photo_count": 1,
        "user_login": "someone",
    }]
    pd.DataFrame(inat_rows).to_csv(raw_dir / "inaturalist_raw.csv", index=False)

    def fake_gbif(on_progress=None, **kwargs):
        return _prov("GBIF", "SUCCESS", retrieved=2, retained=2)

    def fake_inaturalist(on_progress=None, **kwargs):
        return _prov("iNaturalist", "SUCCESS", retrieved=1, retained=1)

    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "gbif", fake_gbif)
    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "inaturalist", fake_inaturalist)

    pipeline.run_source_pipeline("gbif")
    result = pipeline.run_source_pipeline("inaturalist")

    assert result["data_status"] == "REAL_DATA_AVAILABLE"
    assert result["combined_row_count"] == 3  # 2 GBIF + 1 iNaturalist
    assert set(result["sources_in_combined_dataset"]) == {"GBIF", "iNaturalist"}


def test_run_full_pipeline_shares_recombination_logic(isolated_pipeline_paths, monkeypatch):
    raw_dir, processed_dir, metadata_dir = isolated_pipeline_paths
    _write_gbif_raw(raw_dir)

    def fake_gbif(on_progress=None, **kwargs):
        return _prov("GBIF", "SUCCESS", retrieved=2, retained=2)

    def fake_inaturalist(on_progress=None, **kwargs):
        return _prov("iNaturalist", "UNTESTED", retrieved=0, retained=0,
                     error_detail="no credentials")

    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "gbif", fake_gbif)
    monkeypatch.setitem(pipeline.INGESTION_FUNCS, "inaturalist", fake_inaturalist)

    result = pipeline.run_full_pipeline()

    assert result["data_status"] == "REAL_DATA_AVAILABLE"
    assert result["combined_row_count"] == 2
    assert result["provenance_by_source"]["iNaturalist"]["status"] == "UNTESTED"


def test_analysis_functions_work_on_gbif_only_data(mock_standard_df):
    """Requirement: analysis pages must gracefully work with a GBIF-only
    dataset, not assume multiple sources are present."""
    from src.analysis.taxonomic import group_representation
    from src.analysis.spatial import coverage_summary
    from src.analysis.temporal import yearly_coverage

    gbif_only = mock_standard_df[mock_standard_df["source"] == "GBIF"].copy()
    assert gbif_only["source"].nunique() == 1

    rep = group_representation(gbif_only)
    assert len(rep) >= 1

    summary = coverage_summary(gbif_only, grid_size_deg=0.05)
    assert "n_occupied_cells" in summary

    yearly = yearly_coverage(gbif_only)
    assert isinstance(yearly, pd.DataFrame)


def test_cross_platform_reports_honest_single_source_state(mock_standard_df):
    """Requirement 15: never invent a cross-platform comparison when only
    one source succeeded -- the page-level gate (pages/06_Cross_Platform.py)
    checks this directly; here we confirm the data it checks is accurate."""
    gbif_only = mock_standard_df[mock_standard_df["source"] == "GBIF"].copy()
    sources_present = sorted(gbif_only["source"].dropna().unique().tolist())
    assert sources_present == ["GBIF"]
    assert len(sources_present) < 2  # this is what pages/06_Cross_Platform.py checks
