import pandas as pd

from src.processing.taxonomy import normalise_text_field, assign_major_group, taxonomic_completeness_flags


def test_normalise_text_field_trims_and_collapses_spaces():
    s = pd.Series(["  Ficus   religiosa ", None, "Corvus splendens"])
    out = normalise_text_field(s)
    assert out.iloc[0] == "Ficus religiosa"
    assert pd.isna(out.iloc[1])


def test_assign_major_group_maps_known_classes():
    kingdom = pd.Series(["Animalia", "Plantae", "Animalia", None])
    taxon_class = pd.Series(["Aves", None, None, None])
    groups = assign_major_group(kingdom, taxon_class)
    assert groups.iloc[0] == "Birds"
    assert groups.iloc[1] == "Plants (other)"
    assert groups.iloc[2] == "Other animals"
    assert groups.iloc[3] == "Unclassified (missing kingdom & class)"


def test_taxonomic_completeness_flags(mock_standard_df):
    flags = taxonomic_completeness_flags(mock_standard_df)
    # g2 has no scientific_name and no taxonomic_rank "species" -> not identified_to_species
    g2_idx = mock_standard_df.index[mock_standard_df["record_id"] == "g2"][0]
    assert flags.loc[g2_idx, "identified_to_species"] == False  # noqa: E712
