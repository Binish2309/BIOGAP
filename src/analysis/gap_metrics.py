"""
src/analysis/gap_metrics.py

Modular framework for candidate "Biodiversity Observation Gap Score"
(BOGS) components. Per project rules, NO final composite formula is
implemented or claimed here. What this module DOES do:

  1. Define a registry of candidate metric COMPONENTS, each tagged with
     its validation status and the literature it comes from (per the
     BIOGAP Stage 1 report, Section 3).
  2. Actually IMPLEMENT the components that are simple, standard,
     descriptive statistics with no free parameters to validate (spatial
     density, taxonomic evenness, temporal evenness) -- these are
     genuinely computed, not placeholders.
  3. Leave components that require methodological validation (a
     completeness estimator like KnowBR's accumulation-curve-slope method,
     any WEIGHTED composite of components, any claim of "this cell is a
     gap") as explicitly NOT_IMPLEMENTED, raising NotImplementedError with
     a message pointing to what would need to happen first -- rather than
     shipping a guessed formula.

WHY NO COMPOSITE SCORE YET:
Composing spatial + taxonomic + temporal components into a single number
requires choosing a normalisation and a weighting scheme, and the Stage 1
report (Section 13) found no literature consensus on whether compositing
is even the right approach vs. reporting the three dimensions separately.
Choosing weights now, before real data and a validation plan exist, would
be exactly the "manufactured novelty" and "unvalidated metric" the project
rules prohibit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from src.analysis.spatial import observation_density_by_cell, coverage_summary
from src.analysis.taxonomic import group_representation, pielou_evenness
from src.analysis.temporal import yearly_coverage, coefficient_of_variation
from src.processing.validation import assert_no_test_data_in_research_path

VALIDATION_STATUSES = ("IMPLEMENTED_DESCRIPTIVE", "PROPOSED", "NOT_YET_VALIDATED", "NOT_IMPLEMENTED")


@dataclass
class MetricComponent:
    name: str
    description: str
    status: str  # one of VALIDATION_STATUSES
    literature_basis: str
    function: Optional[Callable] = None

    def run(self, *args, **kwargs):
        if self.status == "NOT_IMPLEMENTED":
            raise NotImplementedError(
                f"'{self.name}' is intentionally not implemented yet (status={self.status}). "
                f"Literature basis: {self.literature_basis}. "
                f"See RESEARCH_METHOD.md for what validation work is required before this "
                f"can be implemented honestly."
            )
        if self.function is None:
            raise NotImplementedError(f"'{self.name}' has no attached function.")
        return self.function(*args, **kwargs)


def _spatial_density_component(df: pd.DataFrame, grid_size_deg: float) -> pd.DataFrame:
    assert_no_test_data_in_research_path(df, caller="gap_metrics.spatial_density_component")
    return observation_density_by_cell(df, grid_size_deg)


def _taxonomic_evenness_component(df: pd.DataFrame) -> dict:
    assert_no_test_data_in_research_path(df, caller="gap_metrics.taxonomic_evenness_component")
    rep = group_representation(df)
    evenness = pielou_evenness(rep.set_index("major_group")["record_count"])
    return {"pielou_evenness": evenness, "group_representation": rep.to_dict(orient="records")}


def _temporal_evenness_component(df: pd.DataFrame) -> dict:
    assert_no_test_data_in_research_path(df, caller="gap_metrics.temporal_evenness_component")
    yearly = yearly_coverage(df)
    cv = coefficient_of_variation(yearly["record_count"]) if not yearly.empty else None
    return {"coefficient_of_variation": cv, "yearly_coverage": yearly.to_dict(orient="records")}


def _completeness_component(df: pd.DataFrame, grid_size_deg: float,
                             min_records_per_cell: int = 10) -> dict:
    """
    Per-cell survey completeness via the slope of the species-accumulation
    curve, following the standard method behind KnowBR (Hortal et al.):
    add records to a cell one at a time (in the order given below), track
    cumulative distinct species found, and look at how much the curve is
    STILL RISING over its final segment. A curve that has flattened (low
    final-segment slope) suggests the cell is close to fully surveyed for
    however many records exist; a curve still climbing steeply suggests
    real undersampling, independent of the raw record count.

    ORDERING CAVEAT (stated honestly, not hidden): records are ordered by
    parsed observation_date where available, falling back to record_id
    order for records with no usable date. This is a reasonable, standard
    choice (accumulation curves are conventionally built in
    chronological/collection order) but is NOT the same as a randomised or
    resampled accumulation curve (as some completeness estimators use to
    reduce order-dependence) -- that refinement is not implemented here.

    A cell needs at least `min_records_per_cell` records to be included at
    all -- below that, a slope estimate is too noisy to be meaningful, and
    the cell is reported as excluded, not silently given a value.
    """
    assert_no_test_data_in_research_path(df, caller="gap_metrics.completeness_component")
    from src.analysis.spatial import assign_grid_cell

    working = df.copy()
    working["grid_cell"] = assign_grid_cell(working, grid_size_deg)
    working = working[working["grid_cell"].notna() & working["scientific_name"].notna()]

    parsed_dates = pd.to_datetime(working["observation_date"], errors="coerce")
    working = working.assign(_sort_date=parsed_dates)

    results = []
    n_cells_excluded_too_few_records = 0
    for cell, group in working.groupby("grid_cell"):
        if len(group) < min_records_per_cell:
            n_cells_excluded_too_few_records += 1
            continue
        ordered = group.sort_values(by=["_sort_date", "record_id"], na_position="last")
        seen = set()
        cumulative_species = []
        for name in ordered["scientific_name"]:
            seen.add(name)
            cumulative_species.append(len(seen))

        n = len(cumulative_species)
        final_segment_start = max(0, int(n * 0.8) - 1)
        species_at_80pct = cumulative_species[final_segment_start]
        species_at_100pct = cumulative_species[-1]
        records_in_final_segment = n - final_segment_start
        new_species_in_final_segment = species_at_100pct - species_at_80pct
        slope = new_species_in_final_segment / records_in_final_segment if records_in_final_segment > 0 else None

        results.append({
            "grid_cell": cell,
            "n_records": n,
            "n_species": species_at_100pct,
            "final_segment_slope": round(slope, 4) if slope is not None else None,
            "completeness_estimate": round(1 - slope, 4) if slope is not None else None,
        })

    result_df = pd.DataFrame(results)
    return {
        "per_cell_completeness": result_df,
        "n_cells_analysed": len(result_df),
        "n_cells_excluded_too_few_records": n_cells_excluded_too_few_records,
        "min_records_per_cell_threshold": min_records_per_cell,
        "mean_completeness_estimate": float(result_df["completeness_estimate"].mean()) if not result_df.empty else None,
    }


REGISTRY: dict[str, MetricComponent] = {
    "spatial_density": MetricComponent(
        name="spatial_density",
        description="Record and unique-species count per grid cell (configurable resolution).",
        status="IMPLEMENTED_DESCRIPTIVE",
        literature_basis="Standard record-density baseline used throughout the bias literature "
                          "(e.g. Meyer, Kreft, Guralnick & Jetz 2015); see Stage 1 report Section 3.2.",
        function=_spatial_density_component,
    ),
    "taxonomic_evenness": MetricComponent(
        name="taxonomic_evenness",
        description="Pielou's evenness (J') of record counts across major taxonomic groups.",
        status="IMPLEMENTED_DESCRIPTIVE",
        literature_basis="Pielou's evenness as used in the Sardinia GBIF bias study; Stage 1 report Section 3.3.",
        function=_taxonomic_evenness_component,
    ),
    "temporal_evenness": MetricComponent(
        name="temporal_evenness",
        description="Coefficient of variation of record counts across years.",
        status="IMPLEMENTED_DESCRIPTIVE",
        literature_basis="Standard dispersion statistic; temporal-bias framing per Stage 1 report Section 3.4.",
        function=_temporal_evenness_component,
    ),
    "completeness_index_knowbr_style": MetricComponent(
        name="completeness_index_knowbr_style",
        description="Per-cell survey completeness via species-accumulation-curve final-segment slope (KnowBR/Hortal et al. method).",
        status="IMPLEMENTED_DESCRIPTIVE",
        literature_basis="KnowBR (Hortal et al. 2007-derived slope-of-accumulation-curve method); "
                          "Stage 1 report Section 3.1. Applied here for the first time to this "
                          "dataset -- the METHOD is literature-standard, but the resulting numbers "
                          "have NOT been independently validated against a known-complete reference "
                          "area for MMR. Requires at least min_records_per_cell (default 10) records "
                          "in a cell to produce an estimate; cells below that are excluded, not guessed.",
        function=_completeness_component,
    ),
    "composite_bogs": MetricComponent(
        name="composite_bogs",
        description="A single combined Biodiversity Observation Gap Score across spatial, taxonomic, and temporal dimensions.",
        status="NOT_IMPLEMENTED",
        literature_basis="No literature consensus found on whether/how to composite these dimensions "
                          "into one score; see Stage 1 report Section 13.2. Requires an explicit, "
                          "justified normalisation and weighting scheme plus a validation plan "
                          "(e.g. checking known well-studied sites score as 'low gap') before this "
                          "can be implemented as anything other than an arbitrary guess.",
    ),
}


def list_components() -> pd.DataFrame:
    rows = [{"name": c.name, "description": c.description, "status": c.status,
             "literature_basis": c.literature_basis} for c in REGISTRY.values()]
    return pd.DataFrame(rows)


def run_component(name: str, *args, **kwargs):
    if name not in REGISTRY:
        raise KeyError(f"Unknown gap-metric component: {name!r}. Known: {list(REGISTRY)}")
    return REGISTRY[name].run(*args, **kwargs)
