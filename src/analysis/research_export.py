"""
src/analysis/research_export.py

Generates a structured, citation-ready Methods + Results summary directly
from the real, currently-ingested dataset -- for pasting into (or adapting
for) an actual research paper draft.

HARD RULE: every number in the generated report is computed live from
data/processed/combined_standard.csv and data/metadata/pipeline_run_summary.json
-- both of which only exist once a real ingestion run has produced real
data. This module refuses to run on an empty/missing dataset (raises
ValueError) rather than emitting a report with placeholder numbers. It
never runs on is_test_data rows (enforced by the analysis functions it
calls, which already guard against that).

The report deliberately still reads like a first draft, not a finished
paper: every section either reports a real computed number or explicitly
says what is NOT YET available (e.g. no validated Gap Score) -- matching
RESEARCH_METHOD.md's VERIFIED/IMPLEMENTED/PROPOSED/NOT_YET_VALIDATED
distinctions rather than smoothing over them for presentation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.config import CONFIG, BoundingBox
from src.analysis.spatial import coverage_summary, nearest_neighbor_index
from src.analysis.taxonomic import group_representation, pielou_evenness, species_representation
from src.analysis.temporal import yearly_coverage, coefficient_of_variation, low_coverage_years
from src.analysis.cross_platform import cross_platform_summary
from src.analysis.blind_spot_evidence import observation_vs_accessibility, cross_platform_disagreement_by_cell
from src.analysis.gap_metrics import run_component
from src.utils.data_status import dataset_summary_stats
from src.processing.validation import assert_no_test_data_in_research_path


def build_report_data(df: pd.DataFrame, run_summary: dict | None,
                       bbox: BoundingBox | None = None,
                       grid_size_deg: float | None = None,
                       osm_df: pd.DataFrame | None = None) -> dict:
    """
    Compute every number the report needs, once, from the real dataset.
    Returns a plain dict of sub-results so the Streamlit page and the
    Markdown renderer both read from the same computed values -- no
    number is computed twice (and so cannot silently drift between the
    on-screen preview and the downloaded file).

    osm_df is optional: if provided (real OSM road/path data has been
    ingested), the report includes the blind-spot accessibility evidence
    section. If not, that section is honestly omitted with a note, never
    faked.
    """
    if df is None or df.empty:
        raise ValueError(
            "build_report_data() requires a non-empty real dataset. "
            "Run ingestion first -- this function refuses to generate a "
            "report from no data rather than filling it with placeholders."
        )
    assert_no_test_data_in_research_path(df, caller="research_export.build_report_data")

    bbox = bbox or CONFIG.bbox
    grid_size_deg = grid_size_deg or CONFIG.spatial_default_grid_size_deg

    overview = dataset_summary_stats(df)
    spatial = coverage_summary(df, grid_size_deg)
    nni = nearest_neighbor_index(df)
    tax_rep = group_representation(df)
    evenness = pielou_evenness(tax_rep.set_index("major_group")["record_count"])
    top_species = species_representation(df, top_n=10)
    yearly = yearly_coverage(df)
    cv = coefficient_of_variation(yearly["record_count"]) if not yearly.empty else None
    low_years = low_coverage_years(yearly, quantile_threshold=0.25) if not yearly.empty else pd.DataFrame()

    n_sources = df["source"].dropna().nunique()
    cross_platform = cross_platform_summary(df, grid_size_deg) if n_sources >= 2 else None

    blind_spot = None
    if osm_df is not None and not osm_df.empty:
        blind_spot = observation_vs_accessibility(df, osm_df, bbox, grid_size_deg)
        if blind_spot["status"] != "OK":
            blind_spot = None  # honestly omit rather than include a non-result

    completeness = run_component("completeness_index_knowbr_style", df, grid_size_deg=grid_size_deg)

    disagreement = None
    if n_sources >= 2:
        disagreement_df = cross_platform_disagreement_by_cell(df, grid_size_deg)
        if not disagreement_df.empty:
            disagreement = {
                "single_platform_share": float(disagreement_df["is_single_platform_only"].mean()),
                "n_cells": int(len(disagreement_df)),
            }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bbox": bbox,
        "grid_size_deg": grid_size_deg,
        "overview": overview,
        "spatial": spatial,
        "nni": nni,
        "taxonomic_representation": tax_rep,
        "evenness": evenness,
        "top_species": top_species,
        "yearly_coverage": yearly,
        "temporal_cv": cv,
        "low_coverage_years": low_years,
        "cross_platform": cross_platform,
        "blind_spot": blind_spot,
        "completeness": completeness,
        "cross_platform_disagreement": disagreement,
        "run_summary": run_summary,
    }


def _provenance_table_md(run_summary: dict | None) -> str:
    if not run_summary:
        return "_No provenance record available._"
    rows = ["| Source | Status | Retrieved | Retained | Accessed (UTC) |",
            "|---|---|---|---|---|"]
    for source, prov in run_summary.get("provenance_by_source", {}).items():
        rows.append(
            f"| {source} | {prov.get('status', 'n/a')} | {prov.get('records_retrieved', 0):,} | "
            f"{prov.get('records_retained', 0):,} | {prov.get('access_datetime_utc', 'n/a')} |"
        )
    return "\n".join(rows)


def render_markdown_report(data: dict) -> str:
    """Compose the full Markdown report string from build_report_data()'s
    output. Pure formatting -- no new numbers are computed here."""
    bbox: BoundingBox = data["bbox"]
    ov = data["overview"]
    sp = data["spatial"]
    nni = data["nni"]
    tax = data["taxonomic_representation"]
    top_sp = data["top_species"]
    yearly = data["yearly_coverage"]
    low_years = data["low_coverage_years"]
    cp = data["cross_platform"]

    lines = []
    lines.append("# BIOGAP -- Data Summary Report")
    lines.append(f"*Generated {data['generated_at_utc']} \u2014 all figures computed live from the "
                 "currently-ingested real dataset.*\n")

    lines.append("## 1. Study area and data")
    lines.append(
        f"- Bounding box: lat {bbox.min_lat}\u2013{bbox.max_lat}, lon {bbox.min_lon}\u2013{bbox.max_lon} "
        f"({'official polygon' if bbox.is_official_polygon else '**feasibility approximation, not an official MMR boundary**'})"
    )
    lines.append(f"- Total records: **{ov['n_records']:,}**")
    lines.append(f"- Named species: **{ov['n_species']:,}**" if ov["n_species"] is not None else "- Named species: n/a")
    lines.append(f"- Date coverage: **{ov['date_coverage'] or 'n/a'}**")
    lines.append(f"- Sources: {', '.join(f'{k} ({v:,})' for k, v in ov['records_by_source'].items())}\n")

    lines.append("### Ingestion provenance")
    lines.append(_provenance_table_md(data["run_summary"]))
    lines.append("")

    lines.append("## 2. Spatial coverage")
    lines.append(
        f"- Occupied grid cells (at {data['grid_size_deg']}\u00b0 resolution): **{sp['n_occupied_cells']:,}**\n"
        f"- Georeferenced records: **{sp['n_records_with_coordinates']:,}**\n"
        f"- Median records per occupied cell: **{sp.get('records_per_occupied_cell_median') or 0:.1f}**"
    )
    if nni:
        lines.append(
            f"- Nearest Neighbour Index: **{nni['nni']:.3f}** (n={nni['n_points']:,}) \u2014 "
            f"{'clustered' if nni['nni'] < 1 else 'dispersed' if nni['nni'] > 1 else 'random'} "
            "pattern of records (planar approximation on decimal-degree coordinates)."
        )
    lines.append("")

    lines.append("## 3. Taxonomic representation")
    if data["evenness"] is not None:
        lines.append(f"Pielou's evenness across major taxonomic groups: **J' = {data['evenness']:.3f}**\n")
    lines.append("| Major group | Records | Unique species | Share of records |")
    lines.append("|---|---|---|---|")
    for _, row in tax.iterrows():
        lines.append(f"| {row['major_group']} | {row['record_count']:,} | {row['unique_species']:,} | "
                     f"{row['share_of_records']:.1%} |")
    lines.append("\n**Top 10 most-recorded species:**\n")
    lines.append("| Scientific name | Records | Share of identified records |")
    lines.append("|---|---|---|")
    for _, row in top_sp.iterrows():
        lines.append(f"| *{row['scientific_name']}* | {row['record_count']:,} | "
                     f"{row['share_of_identified_records']:.1%} |")
    lines.append("")

    lines.append("## 4. Temporal coverage")
    if not yearly.empty:
        lines.append(f"- Years with records: **{yearly.shape[0]}** "
                     f"({int(yearly['year'].min())}\u2013{int(yearly['year'].max())})")
        if data["temporal_cv"] is not None:
            lines.append(f"- Coefficient of variation (yearly record counts): **{data['temporal_cv']:.2f}**")
        if not low_years.empty:
            lines.append(f"- Relatively low-coverage years (bottom quartile of this dataset): "
                         f"{', '.join(str(y) for y in sorted(low_years['year']))}")
    else:
        lines.append("_No parseable year data available._")
    lines.append("")

    if cp is not None:
        lines.append("## 5. Cross-platform comparison")
        lines.append(f"Sources compared: {', '.join(cp['sources_present'])}\n")
        lines.append("| Source | Earliest year | Latest year | Occupied cells | Georeferenced records |")
        lines.append("|---|---|---|---|---|")
        temp_by_source = {r["source"]: r for r in cp["temporal_range"]}
        spatial_by_source = {r["source"]: r for r in cp["spatial_extent"]}
        for s in cp["sources_present"]:
            t, sx = temp_by_source.get(s, {}), spatial_by_source.get(s, {})
            lines.append(f"| {s} | {t.get('earliest_year', 'n/a')} | {t.get('latest_year', 'n/a')} | "
                         f"{sx.get('n_occupied_cells', 'n/a')} | {sx.get('n_records_with_coordinates', 'n/a')} |")
        lines.append("\n*Raw record counts are not compared directly across platforms; see caveats "
                     "in the in-app Cross-Platform page and RESEARCH_METHOD.md.*\n")

    disagreement = data.get("cross_platform_disagreement")
    if disagreement is not None:
        lines.append(f"Cells recorded by only one platform: **{disagreement['single_platform_share']:.0%}** "
                     f"of {disagreement['n_cells']:,} occupied cells. If an area were genuinely unvisited, "
                     "no platform would have records there -- single-platform cells are corroborating "
                     "(not conclusive) evidence of platform-specific recording bias.\n")

    blind_spot = data.get("blind_spot")
    lines.append("## 6. Blind-spot evidence (accessibility vs. observation density)")
    if blind_spot is None:
        lines.append(
            "_Not included in this report -- requires real OpenStreetMap road/path context data, "
            "which has not been ingested yet. See the Blind Spot Evidence page in the app. This "
            "section is deliberately omitted here rather than filled with a placeholder._\n"
        )
    else:
        corr = blind_spot["correlation"]
        if corr is not None:
            lines.append(
                f"Spearman correlation between road/path density (accessibility proxy) and "
                f"observation density across {corr['n_cells']:,} grid cells: "
                f"**r = {corr['spearman_r']:.3f}** (p = {corr['p_value']:.4f}).\n"
            )
            if corr["spearman_r"] > 0.2 and corr["p_value"] < 0.05:
                lines.append(
                    "This positive, statistically significant correlation is consistent with the "
                    "documented citizen-science accessibility-bias mechanism (Tiago et al. 2017 and "
                    "related literature, see RESEARCH_METHOD.md) -- i.e. this dataset's recording "
                    "pattern is plausibly shaped by where people can easily go, not purely by "
                    "underlying biodiversity.\n"
                )
        cat_counts = blind_spot["category_counts"]
        lines.append("| Category | Cells | Interpretation |")
        lines.append("|---|---|---|")
        interpretations = {
            "LIKELY_RECORDING_GAP": "High accessibility, low recording -- strongest evidence of a recording (not biodiversity) gap",
            "AMBIGUOUS_LOW_ACCESS": "Low accessibility, low recording -- cannot distinguish cause from this analysis alone",
            "WELL_SAMPLED": "High accessibility, high recording",
            "RECORDED_DESPITE_LOW_ACCESS": "High recording despite low accessibility -- notable",
        }
        for cat, interp in interpretations.items():
            lines.append(f"| {cat.replace('_', ' ').title()} | {cat_counts.get(cat, 0):,} | {interp} |")
        lines.append(
            f"\nClassification thresholds: bottom/top {blind_spot['thresholds_used']['low_quantile']:.0%} "
            f"of this dataset's own observation-count and road-vertex-count distributions -- "
            "relative to this dataset, not externally validated absolute cutoffs.\n"
        )

    completeness = data.get("completeness")
    lines.append("## 7. Survey completeness (species-accumulation-curve method)")
    if completeness and completeness["n_cells_analysed"] > 0:
        lines.append(
            f"Cells with enough records to estimate ({completeness['min_records_per_cell_threshold']}+ "
            f"records): **{completeness['n_cells_analysed']}**. Mean completeness estimate: "
            f"**{completeness['mean_completeness_estimate']:.2f}** (1.0 = accumulation curve fully "
            "flattened; 0.0 = still rising steeply, i.e. likely undersampled).\n"
        )
        lines.append(
            "Method: species-accumulation-curve final-segment slope, following the standard approach "
            "behind KnowBR (Hortal et al.) -- applied here for the first time to this dataset. The "
            "METHOD is literature-standard; these specific numbers have not been independently "
            "validated against a known-complete reference area for this study area.\n"
        )
    else:
        lines.append(
            "_No grid cell currently has enough records to compute a meaningful completeness "
            "estimate. This will become available as more data is ingested._\n"
        )

    lines.append("## 8. What this report does NOT include")
    lines.append(
        "- No Biodiversity Observation Gap Score (BOGS) \u2014 no validated composite metric exists "
        "yet; see `RESEARCH_METHOD.md` for the candidate-component framework and why compositing "
        "is deliberately not implemented.\n"
        "- No claim of novelty \u2014 not yet verified against a dedicated literature search.\n"
        "- No claim that observation counts reflect biodiversity abundance \u2014 these are recorded "
        "occurrences only.\n"
        "- The blind-spot evidence above (Section 6) is evidence FOR AN ARGUMENT, not proof \u2014 it "
        "cannot definitively distinguish a recording gap from a genuine ecological absence, only "
        "make one explanation more or less plausible than the other.\n"
        "- The study-area boundary is a feasibility bounding box, not an official administrative "
        "polygon, unless otherwise stated above."
    )

    return "\n".join(lines)
