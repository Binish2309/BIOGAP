import pandas as pd
import pytest

from src.config import BoundingBox
from src.analysis.blind_spot_evidence import (
    build_full_grid, road_density_by_cell, observation_vs_accessibility,
    cross_platform_disagreement_by_cell, CATEGORY_LIKELY_GAP,
)
from src.processing.validation import ResearchIntegrityError


def _small_bbox():
    return BoundingBox(min_lat=19.0, max_lat=19.2, min_lon=72.8, max_lon=73.0)


def test_build_full_grid_includes_empty_cells():
    grid = build_full_grid(_small_bbox(), grid_size_deg=0.1)
    assert len(grid) == 4  # 2x2 grid of 0.1deg cells across a 0.2x0.2deg bbox
    assert "grid_cell" in grid.columns


def test_build_full_grid_handles_float_boundary_cleanly():
    # A regression check for the np.arange float-boundary bug this module
    # used to have: a bbox spanning an exact multiple of grid_size_deg
    # must give an exact, predictable cell count every time.
    bbox = BoundingBox(min_lat=18.75, max_lat=19.50, min_lon=72.75, max_lon=73.35)
    grid = build_full_grid(bbox, grid_size_deg=0.05)
    expected_lat_steps = round((19.50 - 18.75) / 0.05)
    expected_lon_steps = round((73.35 - 72.75) / 0.05)
    assert len(grid) == expected_lat_steps * expected_lon_steps


def test_road_density_by_cell_counts_vertices():
    osm_df = pd.DataFrame([
        {"way_id": 1, "highway_type": "residential", "vertex_index": 0, "latitude": 19.05, "longitude": 72.85},
        {"way_id": 1, "highway_type": "residential", "vertex_index": 1, "latitude": 19.06, "longitude": 72.86},
        {"way_id": 2, "highway_type": "path", "vertex_index": 0, "latitude": 19.05, "longitude": 72.85},
    ])
    density = road_density_by_cell(osm_df, grid_size_deg=0.1)
    assert density["road_vertex_count"].sum() == 3


def test_road_density_by_cell_empty_input():
    density = road_density_by_cell(pd.DataFrame(), grid_size_deg=0.1)
    assert density.empty


def test_observation_vs_accessibility_insufficient_when_no_osm_data(mock_standard_df):
    result = observation_vs_accessibility(mock_standard_df, pd.DataFrame(), _small_bbox(), grid_size_deg=0.1)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "road" in result["reason"].lower()


def test_observation_vs_accessibility_insufficient_when_no_bio_data():
    osm_df = pd.DataFrame([{"way_id": 1, "highway_type": "path", "vertex_index": 0,
                             "latitude": 19.05, "longitude": 72.85}])
    result = observation_vs_accessibility(pd.DataFrame(), osm_df, _small_bbox(), grid_size_deg=0.1)
    assert result["status"] == "INSUFFICIENT_DATA"


def test_observation_vs_accessibility_refuses_test_data(mock_flagged_test_df):
    osm_df = pd.DataFrame([{"way_id": 1, "highway_type": "path", "vertex_index": 0,
                             "latitude": 19.05, "longitude": 72.85}])
    with pytest.raises(ResearchIntegrityError):
        observation_vs_accessibility(mock_flagged_test_df, osm_df, _small_bbox(), grid_size_deg=0.1)


def test_observation_vs_accessibility_classifies_a_likely_recording_gap():
    import numpy as np
    from src.processing.schema import STANDARD_COLUMNS

    bbox = BoundingBox(min_lat=19.0, max_lat=19.4, min_lon=72.8, max_lon=73.2)
    grid_size = 0.1  # 4x4 = 16 cells

    # Roads present in every cell, with genuine variance in density (not
    # uniform -- a correlation needs actual variance in both variables).
    rng = np.random.default_rng(42)
    road_rows = []
    way_id = 0
    for lat in [19.0, 19.1, 19.2, 19.3]:
        for lon in [72.8, 72.9, 73.0, 73.1]:
            n_vertices = int(rng.integers(15, 30))
            for _ in range(n_vertices):
                road_rows.append({"way_id": way_id, "highway_type": "residential",
                                   "vertex_index": 0, "latitude": lat + 0.01, "longitude": lon + 0.01})
                way_id += 1
    osm_df = pd.DataFrame(road_rows)

    # Biodiversity records concentrated in only ONE cell -- every other
    # cell (all with substantial road density) has zero records despite
    # comparable accessibility.
    bio_rows = []
    for i in range(15):
        bio_rows.append(dict(
            source="GBIF", record_id=f"r{i}", scientific_name=f"Species {i}",
            taxonomic_rank="species", kingdom="Animalia", phylum="Chordata", taxon_class="Aves",
            order=None, family=None, genus=None, latitude=19.05, longitude=72.85,
            observation_date="2022-01-01", year=2022, basis_of_record="HUMAN_OBSERVATION",
            dataset="d", publisher="p", license="CC0", has_media="UNKNOWN",
            effort_distance_km=pd.NA, effort_duration_min=pd.NA, effort_complete_checklist=pd.NA,
            is_test_data=False,
        ))
    df = pd.DataFrame(bio_rows)[STANDARD_COLUMNS]

    result = observation_vs_accessibility(df, osm_df, bbox, grid_size_deg=grid_size)
    assert result["status"] == "OK"
    assert result["correlation"] is not None
    # At least one cell should be flagged as a likely recording gap: high
    # road density but zero/low records.
    assert result["category_counts"].get(CATEGORY_LIKELY_GAP, 0) > 0


def test_cross_platform_disagreement_by_cell(mock_standard_df):
    disagreement = cross_platform_disagreement_by_cell(mock_standard_df, grid_size_deg=0.01)
    assert "is_single_platform_only" in disagreement.columns
    assert disagreement["n_sources"].min() >= 1
