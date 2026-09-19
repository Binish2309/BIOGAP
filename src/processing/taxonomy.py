"""
src/processing/taxonomy.py

Taxonomic normalisation helpers. These standardise FORMATTING (casing,
whitespace) and provide a documented, literature-grounded grouping of
kingdom/class into coarse "major taxonomic group" labels for the taxonomic-
gap analysis. They never invent or correct a taxonomic identification --
if a source says a record is identified only to genus, it stays identified
only to genus.
"""

from __future__ import annotations

import pandas as pd

# Coarse taxonomic groups used in charts/analysis. This mapping is a
# PRESENTATION/GROUPING choice for readability, documented here so it is
# auditable -- it is not a taxonomic claim beyond what the source recorded.
# Unmapped kingdom/class combinations fall through to "Other/Unclassified"
# rather than being forced into a group they don't belong in.
_CLASS_TO_GROUP = {
    "Aves": "Birds",
    "Mammalia": "Mammals",
    "Reptilia": "Reptiles",
    "Amphibia": "Amphibians",
    "Insecta": "Insects",
    "Arachnida": "Arachnids",
    "Actinopterygii": "Ray-finned fishes",
    "Chondrichthyes": "Cartilaginous fishes",
    "Magnoliopsida": "Flowering plants (dicots)",
    "Liliopsida": "Flowering plants (monocots)",
}
_KINGDOM_TO_GROUP = {
    "Plantae": "Plants (other)",
    "Fungi": "Fungi",
    "Bacteria": "Bacteria",
    "Protozoa": "Protozoa",
    "Chromista": "Chromista",
}


def normalise_text_field(series: pd.Series) -> pd.Series:
    """Trim whitespace and collapse internal multi-spaces. Case is left
    exactly as the source provided it -- we do not guess correct
    capitalisation of scientific names."""
    return series.apply(
        lambda v: " ".join(v.split()) if isinstance(v, str) else v
    )


def assign_major_group(kingdom: pd.Series, taxon_class: pd.Series) -> pd.Series:
    """
    Assign each record a coarse, human-readable major taxonomic group for
    charting. Falls through kingdom -> class -> "Other/Unclassified".
    Documented mapping above; extend it there, not ad hoc in analysis code.
    """
    def _one(k, c):
        if isinstance(c, str) and c in _CLASS_TO_GROUP:
            return _CLASS_TO_GROUP[c]
        if isinstance(k, str) and k in _KINGDOM_TO_GROUP:
            return _KINGDOM_TO_GROUP[k]
        if isinstance(k, str) and k == "Animalia":
            return "Other animals"
        if pd.isna(k) and pd.isna(c):
            return "Unclassified (missing kingdom & class)"
        return "Other/Unclassified"

    return pd.Series(
        [_one(k, c) for k, c in zip(kingdom, taxon_class)],
        index=kingdom.index,
    )


def taxonomic_completeness_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return boolean columns describing how far down the taxonomic hierarchy
    each record was identified, based on which fields are populated (not
    on any external checklist). Purely descriptive of THIS dataset.
    """
    return pd.DataFrame({
        "identified_to_species": df["scientific_name"].notna() & (df["taxonomic_rank"].fillna("") == "species"),
        "identified_to_genus_only": df["genus"].notna() & df["scientific_name"].isna(),
        "missing_all_taxonomy": df[["kingdom", "phylum", "taxon_class", "order", "family", "genus"]].isna().all(axis=1),
    })
