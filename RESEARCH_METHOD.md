# RESEARCH_METHOD.md

This document distinguishes **VERIFIED**, **IMPLEMENTED**, **PROPOSED**,
and **NOT YET VALIDATED** throughout, per project rules. It is structured
to map onto an eventual research paper's sections, but is not itself the
paper -- no Results section exists here because no real analysis has been
run on verified real data yet.

## Research question

Given publicly accessible biodiversity occurrence data for the Mumbai
Metropolitan Region, can we systematically identify and quantify where
recording effort is too sparse, too uneven, or too narrowly distributed to
support reliable inference about biodiversity patterns -- using only real,
traceable, open data and previously-validated methods, rather than an
invented and unvalidated scoring formula?

**Status: the question itself is PROPOSED**, refined across this project's
earlier feasibility stages (see the Stage 1 Research & Data Feasibility
Report and the Stage 1b Data Feasibility Test, both produced before this
codebase).

## Literature review (summary -- full review is the Stage 1 report)

Biodiversity observation bias is a well-established finding (Isaac et al.
2014; Meyer, Kreft, Guralnick & Jetz 2015; the 742-million-record Ecography
bias synthesis). Existing completeness/bias metrics include KnowBR-style
accumulation-curve-slope completeness (Hortal et al.), ES50/Hurlbert
rarefaction, Nearest Neighbour Index and Pielou's evenness for spatial and
taxonomic bias respectively, and pre/post cut-point comparisons for
temporal bias (as used in the "Digital Accessible Knowledge of the Birds of
India" study). **Status: VERIFIED as existing literature** (sourced and
cited in the Stage 1 report); **not independently re-verified in this
document**.

## Research gap

No peer-reviewed study combining spatial, taxonomic, and temporal bias into
one reproducible framework for an Indian metropolitan region was found
during the Stage 1 literature search. **Status: PROPOSED gap, NOT YET
VALIDATED as novel** -- a dedicated Google Scholar / Shodhganga search is
still required before this claim can appear in a paper introduction, per
the project's own research-integrity rule against claiming novelty without
literature verification.

## Data

- **Sources**: GBIF, iNaturalist. India Biodiversity Portal was investigated
  at the feasibility stage and not confirmed as currently accessible; no
  connector exists for it. An eBird connector was also built and tested
  during development, then deliberately removed -- see "Why eBird was
  removed" below. **Status: IMPLEMENTED (ingestion connectors)**; **actual
  data volumes for the study area: NOT YET VERIFIED** -- see
  DATA_PROVENANCE.md.
- **Geographic scope**: hand-built rectangular bounding box by default.
  **Status: PROPOSED / feasibility-only.** `BoundingBox` now supports a
  real `polygon_wkt` field (`src/config.py`) wired into GBIF (native WKT
  `geometry` param) and iNaturalist (rectangle query + local
  point-in-polygon post-filtering via `shapely`, excluded-point counts
  logged in provenance). **Status: infrastructure IMPLEMENTED and tested
  (`tests/test_config.py`, `tests/test_inaturalist_polygon.py`); the
  actual authoritative MMR polygon itself is NOT YET OBTAINED.**
- **Minimum viable dataset**: per the Stage 1 report, at minimum a GBIF
  download for the study area, cross-checked against a direct iNaturalist
  pull. **Status: PROPOSED**.

### Why eBird was removed

eBird's public API only exposes RECENT (<=30-day), RADIUS-based
observations -- not the historical, bounding-box archive GBIF and
iNaturalist both provide -- and requires a separately-requested API key.
Given the project's actual research questions (spatial/taxonomic/temporal
gaps over the available historical record), a source that can only see the
last 30 days near a handful of query points added setup friction without a
proportionate research-design benefit. GBIF (multi-taxon aggregator) +
iNaturalist (direct, multi-taxon, photo-verified) already support genuine
spatial, taxonomic, temporal, and cross-platform comparison. Full eBird
historical access (the EBD bulk dataset) remains a legitimate future
extension if effort-structured bird checklist data becomes specifically
necessary -- but is out of scope for the current design, not silently
dropped without a reason.

## Methodology

### Data collection
Real API connectors for GBIF and iNaturalist. **Status: IMPLEMENTED.**

### Data cleaning
Whitespace trimming, empty-string normalisation, implausible-year nulling,
invalid-coordinate flagging (not removal), missing-value indicator
columns, same-source exact-duplicate removal. No value is ever invented,
estimated, or imputed. **Status: IMPLEMENTED**, unit-tested
(`tests/test_cleaning.py`).

### Spatial analysis
Configurable-resolution grid density, per-cell species/source counts,
coverage summary, Nearest Neighbour Index (planar approximation).
**Status: IMPLEMENTED (descriptive)**; NNI methodology matches the cited
Sardinia GBIF bias study but has not been validated against ground truth
for MMR specifically.

### Taxonomic analysis
Major-group representation (documented kingdom/class -> group mapping),
Pielou's evenness, most-recorded-species breakdown. **Status: IMPLEMENTED
(descriptive)**. No external MMR species checklist has been verified, so
"over/under-represented" is always relative to this dataset's own
distribution, never to a validated expectation of true regional richness.

### Temporal analysis
Per-year and per-month record counts, coefficient of variation, relative
(quantile-based) low-coverage-year flagging. **Status: IMPLEMENTED
(descriptive)**. The quantile threshold is a user-adjustable, relative
statement about the dataset's own distribution -- not a validated
"adequate sampling" cutoff, which does not exist yet for this project.

### Observation effort
Effort fields exist in the schema (`effort_distance_km`,
`effort_duration_min`, `effort_complete_checklist`) but are populated only
where a source provides them. **Status: currently empty for both
connectors as implemented** -- neither GBIF nor iNaturalist expose
structured survey effort. Integrating a source that does (e.g. eBird's
full EBD checklist export) remains **PROPOSED, NOT YET IMPLEMENTED**.

### Cross-platform comparison
Per-source taxonomic-composition shares, temporal ranges, and spatial
extents (grid cells occupied), explicitly NOT raw record-count comparisons,
plus a documented per-platform methodology caveat shown alongside every
chart. **Status: IMPLEMENTED**, unit-tested
(`tests/test_cross_platform.py`). A per-cell cross-platform disagreement
index (which cells are recorded by only one platform) is also
**IMPLEMENTED** (`src/analysis/blind_spot_evidence.py::
cross_platform_disagreement_by_cell`) -- corroborating (not conclusive)
evidence that a platform-empty cell reflects platform-specific bias
rather than a genuine absence, since a truly unvisited area would be
empty on every platform, not just one.

### Blind-spot evidence: accessibility vs. observation density
The central "is this a recording gap or a real biodiversity gap" test.
**Status: IMPLEMENTED**
(`src/analysis/blind_spot_evidence.py::observation_vs_accessibility`),
unit-tested (`tests/test_blind_spot_evidence.py`). Method:

1. Fetch real OpenStreetMap road/path geometry for the study area via the
   Overpass API (`src/ingestion/osm_context.py`) -- a documented,
   literature-grounded accessibility proxy (Tiago et al. 2017 found
   path/trail density the strongest predictor of citizen-science
   observation frequency in 7 of 8 taxonomic groups studied). This
   connector counts OSM way-geometry VERTICES per grid cell as a density
   proxy -- explicitly NOT a true road-length-per-cell calculation, which
   would require line-in-polygon geometric intersection not implemented
   here.
2. Build the FULL grid covering the study area, including cells with zero
   observations and zero roads (unlike the density functions used
   elsewhere, which only return occupied cells) -- necessary because the
   whole point is examining cells with low/zero recording.
3. Compute the actual Spearman correlation (`scipy.stats.spearmanr`,
   a real statistical test) between road-vertex density and observation
   density across all cells.
4. Classify each cell into one of four categories using quantile
   thresholds relative to THIS dataset's own distribution (not fixed,
   externally-validated cutoffs): LIKELY_RECORDING_GAP (high
   accessibility, low recording -- the key finding), AMBIGUOUS_LOW_ACCESS
   (low accessibility, low recording -- cause not distinguishable from
   this analysis alone), WELL_SAMPLED, and RECORDED_DESPITE_LOW_ACCESS.

**This produces evidence for an argument, not proof.** Every place this
analysis is surfaced (the Blind Spot Evidence page, the Research Export
report) uses hedged language ("evidence consistent with...") and never
claims to have definitively distinguished a recording gap from a genuine
ecological absence. Population density (e.g. WorldPop) as a second
accessibility covariate remains **PROPOSED, NOT YET IMPLEMENTED** -- see
"Known limitations" below.

### Survey completeness (species-accumulation-curve method)
**Status: IMPLEMENTED** (`src/analysis/gap_metrics.py::
_completeness_component`, registered as `completeness_index_knowbr_style`),
unit-tested. For each grid cell with at least a configurable minimum number
of records (default 10), records are ordered (by parsed observation date
where available, falling back to record ID), cumulative distinct-species
count is tracked as records are added one at a time, and the SLOPE of the
final 20% segment of that curve is used as a completeness estimate --
following the standard method behind KnowBR (Hortal et al.). A flat final
segment (few/no new species in the last 20% of records) suggests the cell
is close to fully surveyed for however many records exist; a steep final
segment suggests real undersampling independent of the raw record count.
**The METHOD is literature-standard; the resulting numbers have NOT been
independently validated against a known-complete reference area for MMR**
-- this is stated explicitly everywhere the metric is shown, consistent
with this project's status-labelling rules.

## Candidate metric development (Biodiversity Observation Gap Score)

See `src/analysis/gap_metrics.py` for the live, authoritative registry.
Summary:

| Component | Status | Note |
|---|---|---|
| Spatial density | IMPLEMENTED_DESCRIPTIVE | Record/species count per configurable grid cell |
| Taxonomic evenness | IMPLEMENTED_DESCRIPTIVE | Pielou's J' across major groups |
| Temporal evenness | IMPLEMENTED_DESCRIPTIVE | Coefficient of variation across years |
| Completeness index (KnowBR-style) | IMPLEMENTED_DESCRIPTIVE | Final-segment accumulation-curve slope per cell (min. 10 records); method-standard, not yet validated against a known-complete reference area for MMR |
| Composite BOGS (single combined score) | NOT_IMPLEMENTED | No literature consensus found on whether/how to composite dimensions; requires an explicit, justified normalisation/weighting scheme plus a validation plan before implementation would be anything other than a guess |

**No final BOGS formula is proposed anywhere in this codebase or this
document.** This is deliberate, per project rules against manufacturing
novelty or presenting an unvalidated metric as finished.

## Validation

**No metric in this codebase has been validated against ground truth or an
independent reference dataset.** "IMPLEMENTED_DESCRIPTIVE" means the
statistic is correctly computed from real data using a standard, cited
formula -- it does not mean the statistic has been shown to correlate with,
or substitute for, true biodiversity completeness. A validation plan
(e.g., checking that known well-studied sites such as Bhandup Pumping
Station or Sewri score as "low gap" once real data and a candidate
composite metric both exist) is itself **PROPOSED, NOT YET DESIGNED IN
DETAIL.**

## Results

Not present in this document. Results will only be added after a real
`python -m src.pipeline` run on a machine with real internet access, using
real retrieved data, following the analysis methods described above.

## Limitations (known now, before any results exist)

1. The bounding box includes area outside true MMR and may exclude true
   edge areas -- see `RESEARCH_METHOD.md`'s "Data" section and
   DATA_PROVENANCE.md.
2. This project uses two sources, not three -- eBird was deliberately
   excluded (see "Why eBird was removed" above), so any bird-specific
   effort-structured data eBird would have provided is simply absent, not
   attempted-and-failed.
3. GBIF's synchronous search API caps at 100,000 records; a genuinely
   data-rich study area would require GBIF's asynchronous occurrence-
   download endpoint. **Status: fallback IMPLEMENTED**
   (`src/ingestion/gbif_bulk_download.py`, correctly reports `UNTESTED`
   without a free GBIF account), **but parsing the downloaded archive into
   the standard schema is NOT_IMPLEMENTED** -- its file layout differs
   from the search API's JSON records. Separately, and much more often in
   practice: the app's interactive "Fetch GBIF observations" button is
   further bounded to `CONFIG.gbif_interactive_record_limit` (default
   8,000) so a single click stays reliable in a Streamlit session -- this
   is a deliberate, disclosed interactive sample, not a claim of
   completeness, and does not by itself constitute the "genuinely
   data-rich" case above unless GBIF's own reported match count is also
   checked (which the app does, and reports honestly when the two
   diverge).
4. No cross-platform de-duplication of the SAME real-world observation
   reported to multiple platforms is implemented -- only same-source exact
   duplicates are removed. Cross-platform matching (species + coordinates
   + date, within tolerance) is a harder, probabilistic problem that
   belongs in a documented future analysis step, not silent cleaning.
5. Taxonomic hierarchy (order/family/genus) is currently only reliably
   populated from GBIF; iNaturalist records have thinner hierarchy fields
   in the standard schema as implemented.
6. The blind-spot evidence analysis (accessibility vs. observation
   density) has three specific, disclosed limitations: (a) its
   accessibility proxy counts OSM way vertices, not true road length per
   cell; (b) its four-category classification uses quantile thresholds
   relative to THIS dataset's own distribution, not externally validated
   absolute cutoffs, so results are not directly comparable across
   differently-sized datasets; (c) it currently uses only one
   accessibility covariate (roads/paths) -- population density, which the
   literature also identifies as a predictor, is not yet included (see
   "Why eBird was removed"-adjacent reasoning: raster population data
   would require `rasterio` and large downloads out of scope for the
   current Streamlit Cloud deployment). The analysis is designed and
   labelled throughout as evidence for an argument, not proof of a true
   ecological absence.

## Conclusion

Not present. See "Results" above.
