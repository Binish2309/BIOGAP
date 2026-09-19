import pandas as pd
import pytest

from src.analysis.research_export import build_report_data, render_markdown_report
from src.processing.validation import ResearchIntegrityError


def test_build_report_data_raises_on_empty_dataset():
    with pytest.raises(ValueError):
        build_report_data(pd.DataFrame(), None)


def test_build_report_data_refuses_test_flagged_data(mock_flagged_test_df):
    with pytest.raises(ResearchIntegrityError):
        build_report_data(mock_flagged_test_df, None)


def test_build_report_data_computes_real_numbers(mock_standard_df):
    data = build_report_data(mock_standard_df, run_summary=None, grid_size_deg=0.5)
    assert data["overview"]["n_records"] == len(mock_standard_df)
    assert data["spatial"]["n_records_with_coordinates"] == len(mock_standard_df)
    assert data["cross_platform"] is not None  # 3 sources present in the fixture


def test_render_markdown_report_includes_real_record_count(mock_standard_df):
    data = build_report_data(mock_standard_df, run_summary=None, grid_size_deg=0.5)
    report = render_markdown_report(data)
    assert f"{data['overview']['n_records']:,}" in report
    assert "Biodiversity Observation Gap Score (BOGS)" in report  # honest "not included" section present
    assert "# BIOGAP -- Data Summary Report" in report


def test_render_markdown_report_handles_missing_species_count_gracefully():
    # A minimal frame with no scientific_name column values at all.
    df = pd.DataFrame({
        "source": ["GBIF"], "record_id": ["1"], "scientific_name": [None],
        "taxonomic_rank": [None], "kingdom": [None], "phylum": [None], "taxon_class": [None],
        "order": [None], "family": [None], "genus": [None],
        "latitude": [19.0], "longitude": [72.8], "observation_date": [None], "year": [None],
        "basis_of_record": [None], "dataset": [None], "publisher": [None], "license": [None],
        "has_media": ["UNKNOWN"], "effort_distance_km": [pd.NA], "effort_duration_min": [pd.NA],
        "effort_complete_checklist": [pd.NA], "is_test_data": [False],
    })
    data = build_report_data(df, run_summary=None, grid_size_deg=0.5)
    report = render_markdown_report(data)
    # scientific_name is present but all-null -> a real computed 0, not "n/a"
    assert "Named species: **0**" in report
    # crucially, the bounding-box and records lines must NOT have been swallowed
    assert "Bounding box" in report
    assert "Total records" in report


def test_build_report_data_omits_blind_spot_section_without_osm_data(mock_standard_df):
    data = build_report_data(mock_standard_df, run_summary=None, grid_size_deg=0.5, osm_df=None)
    assert data["blind_spot"] is None
    report = render_markdown_report(data)
    assert "Not included in this report" in report


def test_build_report_data_includes_blind_spot_section_with_osm_data(mock_standard_df):
    from src.config import BoundingBox
    # A small bbox matching the fixture's actual coordinate range (18.99-19.10,
    # 72.75-73.35), with a fine enough grid to produce >=8 cells.
    bbox = BoundingBox(min_lat=18.90, max_lat=19.20, min_lon=72.70, max_lon=73.20)
    osm_df = pd.DataFrame([
        {"way_id": i, "highway_type": "residential", "vertex_index": 0,
         "latitude": 18.95 + (i % 6) * 0.05, "longitude": 72.80 + (i % 6) * 0.05}
        for i in range(60)
    ])
    data = build_report_data(mock_standard_df, run_summary=None, grid_size_deg=0.05,
                              bbox=bbox, osm_df=osm_df)
    assert data["blind_spot"] is not None
    assert data["blind_spot"]["status"] == "OK"
    report = render_markdown_report(data)
    assert "Blind-spot evidence" in report
    assert "LIKELY_RECORDING_GAP" not in report  # should be human-formatted, not raw enum
    assert "Likely Recording Gap" in report


def test_build_report_data_always_includes_completeness_section(mock_standard_df):
    data = build_report_data(mock_standard_df, run_summary=None, grid_size_deg=0.5)
    assert data["completeness"] is not None
    report = render_markdown_report(data)
    assert "Survey completeness" in report
