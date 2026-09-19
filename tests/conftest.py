"""
tests/conftest.py

Shared fixtures. All data here is obviously synthetic (fictional
coordinates/species used only to exercise code paths); it never touches
data/raw/ or data/processed/.

Two fixtures, two different purposes:
  - mock_standard_df: is_test_data=False. Used to unit-test the actual
    analysis LOGIC (spatial/taxonomic/temporal/cross-platform functions)
    end-to-end. These rows are fictional but are not meant to trip the
    is_test_data guard -- that guard exists to stop a real mock/fixture
    FILE from ever being loaded by the deployed app's pipeline as if it
    were real ingested data, not to block legitimate unit testing of the
    analysis functions themselves.
  - mock_flagged_test_df: is_test_data=True. Used ONLY in
    test_validation.py to confirm the guard itself actually raises.
"""

import pandas as pd
import pytest

from src.processing.schema import STANDARD_COLUMNS


def _rows(is_test_data_value: bool):
    return [
        dict(source="GBIF", record_id="g1", scientific_name="Corvus splendens",
             taxonomic_rank="species", kingdom="Animalia", phylum="Chordata",
             taxon_class="Aves", order="Passeriformes", family="Corvidae", genus="Corvus",
             latitude=19.07, longitude=72.87, observation_date="2022-03-01", year=2022,
             basis_of_record="HUMAN_OBSERVATION", dataset="ds1", publisher="pub1",
             license="CC_BY_4_0", has_media=True, effort_distance_km=pd.NA,
             effort_duration_min=pd.NA, effort_complete_checklist=pd.NA, is_test_data=is_test_data_value),
        dict(source="GBIF", record_id="g2", scientific_name=None,
             taxonomic_rank=None, kingdom="Plantae", phylum="Tracheophyta",
             taxon_class="Magnoliopsida", order="Rosales", family=None, genus="Ficus",
             latitude=19.10, longitude=72.90, observation_date=None, year=None,
             basis_of_record="HUMAN_OBSERVATION", dataset="ds1", publisher="pub1",
             license="CC0_1_0", has_media="UNKNOWN", effort_distance_km=pd.NA,
             effort_duration_min=pd.NA, effort_complete_checklist=pd.NA, is_test_data=is_test_data_value),
        dict(source="iNaturalist", record_id="i1", scientific_name="Pavo cristatus",
             taxonomic_rank="species", kingdom="Animalia", phylum="Chordata",
             taxon_class="Aves", order="Galliformes", family="Phasianidae", genus="Pavo",
             latitude=18.99, longitude=73.12, observation_date="2021-11-15", year=2021,
             basis_of_record="HUMAN_OBSERVATION", dataset="iNaturalist", publisher="iNaturalist",
             license="CC_BY_NC_4_0", has_media=False, effort_distance_km=pd.NA,
             effort_duration_min=pd.NA, effort_complete_checklist=pd.NA, is_test_data=is_test_data_value),
        dict(source="iNaturalist", record_id="i2", scientific_name="Corvus splendens",
             taxonomic_rank="species", kingdom="Animalia", phylum="Chordata",
             taxon_class="Aves", order="Passeriformes", family="Corvidae", genus="Corvus",
             latitude=19.08, longitude=72.88, observation_date="2020-05-20", year=2020,
             basis_of_record="HUMAN_OBSERVATION", dataset="iNaturalist", publisher="iNaturalist",
             license="CC_BY_4_0", has_media=True, effort_distance_km=pd.NA,
             effort_duration_min=pd.NA, effort_complete_checklist=pd.NA, is_test_data=is_test_data_value),
        dict(source="iNaturalist", record_id="i3", scientific_name="Corvus splendens",
             taxonomic_rank="species", kingdom="Animalia", phylum="Chordata",
             taxon_class="Aves", order=None, family=None, genus=None,
             latitude=19.05, longitude=72.85, observation_date="2024-01-10", year=2024,
             basis_of_record="HUMAN_OBSERVATION", dataset="iNaturalist", publisher="iNaturalist",
             license="CC0_1_0", has_media="UNKNOWN", effort_distance_km=pd.NA,
             effort_duration_min=pd.NA, effort_complete_checklist=pd.NA, is_test_data=is_test_data_value),
    ]


@pytest.fixture
def mock_standard_df() -> pd.DataFrame:
    df = pd.DataFrame(_rows(False))
    return df[STANDARD_COLUMNS]


@pytest.fixture
def mock_flagged_test_df() -> pd.DataFrame:
    df = pd.DataFrame(_rows(True))
    return df[STANDARD_COLUMNS]

