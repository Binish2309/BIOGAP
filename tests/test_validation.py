import pandas as pd
import pytest

from src.processing.validation import (
    flag_invalid_coordinates, flag_duplicate_records, parse_year_safe,
    validate_year_range, assert_no_test_data_in_research_path, ResearchIntegrityError,
    check_schema,
)


def test_flag_invalid_coordinates_catches_out_of_range_and_null_island():
    df = pd.DataFrame({
        "latitude": [19.0, 0.0, 91.0, None],
        "longitude": [72.8, 0.0, 72.8, 72.8],
    })
    flags = flag_invalid_coordinates(df)
    assert list(flags) == [False, True, True, True]


def test_flag_duplicate_records_same_source_only():
    df = pd.DataFrame({
        "source": ["GBIF", "GBIF", "iNaturalist"],
        "record_id": ["1", "1", "1"],
    })
    flags = flag_duplicate_records(df)
    assert list(flags) == [False, True, False]  # cross-source id=1 is NOT flagged


def test_parse_year_safe_coerces_bad_values_to_na():
    s = pd.Series(["2020", "not-a-year", None, "1998"])
    out = parse_year_safe(s)
    assert out.tolist()[0] == 2020
    assert pd.isna(out.tolist()[1])
    assert pd.isna(out.tolist()[2])
    assert out.tolist()[3] == 1998


def test_validate_year_range_flags_implausible_years():
    s = pd.Series([2020, 9999, 0, None, 1850])
    flags = validate_year_range(s)
    assert list(flags) == [False, True, True, False, False]


def test_check_schema_reports_missing_columns():
    df = pd.DataFrame({"source": ["GBIF"]})
    result = check_schema(df)
    assert result["ok"] is False
    assert "latitude" in result["missing_columns"]


def test_research_integrity_guard_blocks_test_data(mock_flagged_test_df):
    with pytest.raises(ResearchIntegrityError):
        assert_no_test_data_in_research_path(mock_flagged_test_df, caller="test")


def test_research_integrity_guard_allows_real_data(mock_standard_df):
    # Should not raise
    assert_no_test_data_in_research_path(mock_standard_df, caller="test")
