"""
src/analysis/taxonomic.py

Taxonomic representation analysis. Reports what SHARE of recorded
observations/species belong to each major group -- explicitly a measure of
RECORDING representation, not of true relative abundance or richness. No
"expected" baseline (e.g. a regional species checklist) is assumed unless
one is explicitly supplied, because we do not have a verified one for MMR
yet (see BIOGAP Stage 1 report, Section 5 on research gaps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.processing.taxonomy import assign_major_group
from src.processing.validation import assert_no_test_data_in_research_path


def group_representation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Record count, unique-species count, and share-of-total-records per
    major taxonomic group. This is the taxonomic analogue of Section 4.2's
    Konkan-division breakdown in the Stage 1 report -- computed here on
    THIS dataset, not assumed from that gray-literature figure.
    """
    assert_no_test_data_in_research_path(df, caller="taxonomic.group_representation")
    working = df.copy()
    working["major_group"] = assign_major_group(working["kingdom"], working["taxon_class"])

    total = len(working)
    grouped = working.groupby("major_group").agg(
        record_count=("record_id", "count"),
        unique_species=("scientific_name", lambda s: s.dropna().nunique()),
    ).reset_index()
    grouped["share_of_records"] = grouped["record_count"] / total if total else np.nan
    return grouped.sort_values("record_count", ascending=False).reset_index(drop=True)


def pielou_evenness(group_counts: pd.Series) -> float | None:
    """
    Pielou's evenness index (J') applied to record counts across major
    taxonomic groups (or, if you pass species-level counts instead,
    across species) -- as used in the Sardinia GBIF bias study cited in
    the Stage 1 report. J' = H' / ln(S), where H' is Shannon diversity and
    S is the number of categories. J' close to 1 means recording effort is
    spread evenly across categories; J' close to 0 means it is dominated
    by very few categories.

    Returns None if fewer than 2 non-zero categories are present.
    """
    counts = group_counts[group_counts > 0]
    s = len(counts)
    if s < 2:
        return None
    proportions = counts / counts.sum()
    shannon_h = float(-(proportions * np.log(proportions)).sum())
    return shannon_h / np.log(s)


def species_representation(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    Record count per distinct scientific_name, sorted descending. Useful
    for spotting whether the dataset is dominated by a small number of
    easily-identified/charismatic species -- a documented citizen-science
    bias pattern (Stage 1 report, Section 2.3) -- WITHOUT asserting that
    the dominant species are actually the most abundant in the field.
    """
    assert_no_test_data_in_research_path(df, caller="taxonomic.species_representation")
    counts = df["scientific_name"].dropna().value_counts().head(top_n)
    out = counts.reset_index()
    out.columns = ["scientific_name", "record_count"]
    out["share_of_identified_records"] = out["record_count"] / df["scientific_name"].notna().sum()
    return out
