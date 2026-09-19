import pytest

from src.analysis.gap_metrics import list_components, run_component, REGISTRY


def test_list_components_includes_all_registered():
    df = list_components()
    assert set(df["name"]) == set(REGISTRY.keys())


def test_implemented_components_run_without_error(mock_standard_df):
    result = run_component("taxonomic_evenness", mock_standard_df)
    assert "pielou_evenness" in result

    result2 = run_component("temporal_evenness", mock_standard_df)
    assert "coefficient_of_variation" in result2

    result3 = run_component("spatial_density", mock_standard_df, grid_size_deg=0.5)
    assert not result3.empty


def test_not_implemented_components_raise_not_implemented_error(mock_standard_df):
    with pytest.raises(NotImplementedError):
        run_component("composite_bogs", mock_standard_df)


def test_completeness_component_excludes_low_record_cells(mock_standard_df):
    # The 5-row fixture has too few records per cell to meet the default
    # min_records_per_cell=10 -- confirm it's honestly excluded, not guessed.
    result = run_component("completeness_index_knowbr_style", mock_standard_df, grid_size_deg=0.5)
    assert result["n_cells_analysed"] == 0
    assert result["n_cells_excluded_too_few_records"] > 0
    assert result["mean_completeness_estimate"] is None


def test_completeness_component_computes_real_slope_with_enough_records():
    import pandas as pd
    from src.analysis.gap_metrics import run_component
    from src.processing.schema import STANDARD_COLUMNS

    # A perfectly flat curve: the same 3 species repeated 12 times in one
    # cell -- completeness should be very high (slope near 0, estimate near 1)
    # since no new species appear at all in the final segment.
    rows = []
    species = ["Corvus splendens", "Pavo cristatus", "Ficus religiosa"]
    for i in range(12):
        rows.append(dict(
            source="GBIF", record_id=f"r{i}", scientific_name=species[i % 3],
            taxonomic_rank="species", kingdom="Animalia", phylum="Chordata",
            taxon_class="Aves", order=None, family=None, genus=None,
            latitude=19.0, longitude=72.8, observation_date=f"2022-01-{i+1:02d}", year=2022,
            basis_of_record="HUMAN_OBSERVATION", dataset="d", publisher="p", license="CC0",
            has_media="UNKNOWN", effort_distance_km=pd.NA, effort_duration_min=pd.NA,
            effort_complete_checklist=pd.NA, is_test_data=False,
        ))
    df = pd.DataFrame(rows)[STANDARD_COLUMNS]
    result = run_component("completeness_index_knowbr_style", df, grid_size_deg=0.5, min_records_per_cell=10)
    assert result["n_cells_analysed"] == 1
    row = result["per_cell_completeness"].iloc[0]
    assert row["n_species"] == 3
    assert row["completeness_estimate"] > 0.9  # curve is flat -- highly complete


def test_unknown_component_raises_key_error(mock_standard_df):
    with pytest.raises(KeyError):
        run_component("not_a_real_metric", mock_standard_df)
