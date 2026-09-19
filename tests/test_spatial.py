import pandas as pd

from src.analysis.spatial import assign_grid_cell, observation_density_by_cell, coverage_summary, nearest_neighbor_index


def test_assign_grid_cell_groups_nearby_points_together(mock_standard_df):
    cells = assign_grid_cell(mock_standard_df, grid_size_deg=0.5)
    # g1 (19.07, 72.87) and i3 (19.05, 72.85) should fall in the same 0.5deg cell
    g1_cell = cells[mock_standard_df["record_id"] == "g1"].iloc[0]
    i3_cell = cells[mock_standard_df["record_id"] == "i3"].iloc[0]
    assert g1_cell == i3_cell


def test_observation_density_by_cell_excludes_missing_coords():
    df = pd.DataFrame({
        "latitude": [19.0, None], "longitude": [72.8, None],
        "record_id": ["a", "b"], "scientific_name": ["X", "Y"], "source": ["GBIF", "GBIF"],
    })
    density = observation_density_by_cell(df, grid_size_deg=0.1)
    assert density["record_count"].sum() == 1


def test_coverage_summary_reports_extent(mock_standard_df):
    summary = coverage_summary(mock_standard_df, grid_size_deg=0.05)
    assert summary["n_records_with_coordinates"] == len(mock_standard_df)
    assert summary["lat_extent"][0] <= summary["lat_extent"][1]


def test_nearest_neighbor_index_returns_none_below_3_points():
    df = pd.DataFrame({"latitude": [19.0, 19.01], "longitude": [72.8, 72.81]})
    assert nearest_neighbor_index(df) is None


def test_nearest_neighbor_index_computes_for_enough_points(mock_standard_df):
    result = nearest_neighbor_index(mock_standard_df)
    assert result is not None
    assert result["n_points"] == len(mock_standard_df)
    assert "nni" in result
