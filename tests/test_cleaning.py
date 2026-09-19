import pandas as pd

from src.processing.cleaning import normalise_gbif, normalise_inaturalist, clean_standard_frame
from src.processing.schema import STANDARD_COLUMNS


def test_normalise_gbif_maps_fields_correctly():
    raw = pd.DataFrame([{
        "gbif_key": 1001, "occurrenceID": "urn:x", "species": "Corvus splendens",
        "scientificName": "Corvus splendens Vieillot, 1817", "kingdom": "Animalia",
        "phylum": "Chordata", "class": "Aves", "order": "Passeriformes",
        "family": "Corvidae", "genus": "Corvus", "decimalLatitude": 19.07,
        "decimalLongitude": 72.87, "eventDate": "2022-03-01", "year": 2022,
        "basisOfRecord": "HUMAN_OBSERVATION", "datasetKey": "ds1",
        "publishingOrgKey": "org1", "occurrenceStatus": "PRESENT",
        "license": "CC_BY_4_0", "has_media": True, "media_count": 1,
    }])
    out = normalise_gbif(raw)
    assert out.loc[0, "source"] == "GBIF"
    assert out.loc[0, "taxon_class"] == "Aves"
    assert out.loc[0, "latitude"] == 19.07
    assert out.loc[0, "is_test_data"] == False  # noqa: E712
    for col in STANDARD_COLUMNS:
        assert col in out.columns


def test_normalise_inaturalist_derives_year_from_date():
    raw = pd.DataFrame([{
        "inat_id": 1, "uuid": "u1", "taxon_name": "Pavo cristatus", "taxon_rank": "species",
        "iconic_taxon_name": "Aves", "latitude": 18.99, "longitude": 73.12,
        "observed_on": "2021-11-15", "quality_grade": "research", "license_code": "CC0",
        "photo_count": 2, "user_login": "someone",
    }])
    out = normalise_inaturalist(raw)
    assert out.loc[0, "year"] == 2021
    assert out.loc[0, "has_media"] == True  # noqa: E712


def test_clean_standard_frame_dedups_and_never_drops_missing_fields(mock_standard_df):
    # Introduce an exact same-source duplicate
    dup_row = mock_standard_df.iloc[[0]].copy()
    df = pd.concat([mock_standard_df, dup_row], ignore_index=True)
    rows_before = len(df)

    cleaned, report = clean_standard_frame(df)

    assert report["rows_before"] == rows_before
    assert report["rows_removed_total"] == 1  # only the exact duplicate
    assert len(cleaned) == rows_before - 1
    # The row with missing scientific_name (g2) must still be present, not dropped
    assert (cleaned["record_id"] == "g2").any()
    assert bool(cleaned.loc[cleaned["record_id"] == "g2", "missing_scientific_name"].iloc[0]) is True


def test_clean_standard_frame_flags_but_does_not_remove_invalid_coordinates(mock_standard_df):
    df = mock_standard_df.copy()
    df.loc[0, "latitude"] = 999.0  # invalid
    cleaned, _ = clean_standard_frame(df)
    assert len(cleaned) == len(df)  # nothing removed
    assert bool(cleaned.loc[0, "invalid_coordinates_flag"]) is True
