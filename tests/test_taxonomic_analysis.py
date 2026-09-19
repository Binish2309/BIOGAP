from src.analysis.taxonomic import group_representation, pielou_evenness, species_representation
import pandas as pd


def test_group_representation_shares_sum_to_one(mock_standard_df):
    rep = group_representation(mock_standard_df)
    assert abs(rep["share_of_records"].sum() - 1.0) < 1e-9


def test_pielou_evenness_perfect_evenness_is_one():
    counts = pd.Series([10, 10, 10, 10])
    j = pielou_evenness(counts)
    assert abs(j - 1.0) < 1e-9


def test_pielou_evenness_single_category_returns_none():
    counts = pd.Series([10])
    assert pielou_evenness(counts) is None


def test_species_representation_counts_corvus_twice(mock_standard_df):
    rep = species_representation(mock_standard_df, top_n=5)
    corvus_row = rep[rep["scientific_name"] == "Corvus splendens"]
    assert corvus_row["record_count"].iloc[0] == 3  # g1, i2, e1
