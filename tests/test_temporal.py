import pandas as pd

from src.processing.temporal import parse_observation_date, extract_year_month, year_coverage_summary
from src.analysis.temporal import yearly_coverage, coefficient_of_variation, low_coverage_years


def test_parse_observation_date_handles_bad_values():
    s = pd.Series(["2022-03-01", "not-a-date", None])
    parsed = parse_observation_date(s)
    assert parsed.iloc[0].year == 2022
    assert pd.isna(parsed.iloc[1])
    assert pd.isna(parsed.iloc[2])


def test_extract_year_month():
    parsed = parse_observation_date(pd.Series(["2022-03-15"]))
    out = extract_year_month(parsed)
    assert out.loc[0, "derived_year"] == 2022
    assert out.loc[0, "derived_month"] == 3


def test_year_coverage_summary(mock_standard_df):
    summary = year_coverage_summary(mock_standard_df)
    assert summary["n_records_missing_year"] == 1  # g2 has no year
    assert summary["earliest_year"] == 2020
    assert summary["latest_year"] == 2024


def test_yearly_coverage_and_cv(mock_standard_df):
    yearly = yearly_coverage(mock_standard_df)
    assert set(yearly["year"]) == {2020, 2021, 2022, 2024}
    cv = coefficient_of_variation(yearly["record_count"])
    assert cv is not None and cv >= 0


def test_low_coverage_years_flags_relative_to_dataset():
    yearly = pd.DataFrame({"year": [2019, 2020, 2021], "record_count": [1, 1, 100]})
    low = low_coverage_years(yearly, quantile_threshold=0.5)
    assert set(low["year"]) == {2019, 2020}
