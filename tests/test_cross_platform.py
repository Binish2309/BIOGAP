from src.analysis.cross_platform import (
    taxonomic_composition_by_source, temporal_range_by_source, spatial_extent_by_source,
    cross_platform_summary, PLATFORM_STRUCTURE_CAVEATS,
)


def test_taxonomic_composition_by_source_has_all_sources(mock_standard_df):
    comp = taxonomic_composition_by_source(mock_standard_df)
    assert set(comp["source"]) == {"GBIF", "iNaturalist"}


def test_temporal_range_by_source(mock_standard_df):
    ranges = temporal_range_by_source(mock_standard_df)
    gbif_row = ranges[ranges["source"] == "GBIF"].iloc[0]
    assert gbif_row["earliest_year"] == 2022
    assert gbif_row["latest_year"] == 2022
    inat_row = ranges[ranges["source"] == "iNaturalist"].iloc[0]
    assert inat_row["earliest_year"] == 2020
    assert inat_row["latest_year"] == 2024


def test_spatial_extent_by_source(mock_standard_df):
    extents = spatial_extent_by_source(mock_standard_df, grid_size_deg=0.05)
    assert (extents["n_records_with_coordinates"] > 0).all()


def test_cross_platform_summary_includes_caveats(mock_standard_df):
    summary = cross_platform_summary(mock_standard_df, grid_size_deg=0.05)
    for source in summary["sources_present"]:
        assert source in PLATFORM_STRUCTURE_CAVEATS
        assert len(summary["platform_structure_caveats"][source]) > 0
