# BIOGAP -- Biodiversity Observation Gap Analytics Platform

Working research title: *"Quantifying Biodiversity Observation Blind Spots: A
Data-Driven Framework for Spatial, Taxonomic and Temporal Gaps"*

BIOGAP identifies and visualises geographic, taxonomic, and temporal gaps in
publicly available biodiversity observation data (GBIF, iNaturalist) for the
Mumbai Metropolitan Region, India. It is a final-year Data Science major
project with two equally important outputs: a working software platform, and
a scientifically defensible research study.

**Read `RESEARCH_METHOD.md` and `DATA_PROVENANCE.md` before trusting any
number this app shows you.** Every statistic is labelled IMPLEMENTED,
PROPOSED, or NOT YET VALIDATED -- see the in-app Methodology page.

## Quick start

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

# Step 1 (CLI, optional): get real data from the command line
python -m src.pipeline

# Step 2: launch the app
streamlit run app.py
```

Step 1 is optional -- the app itself has a staged, in-app ingestion UI on
the Overview page ("Fetch GBIF observations", then optionally "Add
iNaturalist observations"), sized so a single click reliably finishes on
Streamlit Cloud instead of blocking on both sources at once. See "Staged
ingestion" below.

Full Windows/VS Code instructions, including what to do if step 1 fails,
are in `SETUP.md`.

## Staged ingestion (why there are two buttons, not one)

Earlier versions of this app had a single "Run ingestion pipeline" button
that ran every source back-to-back inside one blocking call. On Streamlit
Cloud this was unreliable: GBIF's search API alone could need dozens of
sequential paginated requests, iNaturalist's pagination had no enforced
upper bound, and the UI had nothing to show while blocked for minutes --
which looks like a lost connection, not a running job.

The Overview page has two independent controls, calling
`src.pipeline.run_source_pipeline()` for exactly one source at a time:

1. **Fetch GBIF observations** (primary) -- bounded to
   `CONFIG.gbif_interactive_record_limit` (default 8,000) records per click.
   Sufficient on its own to populate every analysis page.
2. **Add iNaturalist observations** (optional) -- bounded to
   `CONFIG.inaturalist_interactive_record_limit` (default 3,000).

Each button streams live progress (`st.status()`) and shows the result
immediately -- no forced page rerun. A later source failing never erases
an earlier source's successfully retained data (tracked in
`data/metadata/latest_source_state.json`); the combined dataset only ever
grows. Neither interactive limit is the full matching count -- if GBIF or
iNaturalist report more matches than the limit, that is stated explicitly
in the per-source result, never silently truncated without comment. For a
full, unbounded GBIF dataset, use `src/ingestion/gbif_bulk_download.py`'s
asynchronous download path (requires a free GBIF account) instead of
raising the interactive limit.

## Why eBird isn't in this project

An eBird connector was built and tested earlier in this project's
development, then deliberately removed. Reasoning: eBird's public API only
exposes recent (<=30-day), radius-based observations -- not the historical,
bounding-box archive that GBIF and iNaturalist both provide -- and requires
a separately-requested API key for comparatively little research value once
the recency/radius limitation is accounted for. GBIF + iNaturalist alone
already support genuine spatial, taxonomic, temporal, and cross-platform gap
analysis across multiple taxa, so removing eBird simplifies setup (no key to
request) without weakening the research design. See `RESEARCH_METHOD.md`.

## What's actually functional right now

- **Ingestion connectors** (`src/ingestion/`): real, working code against the
  official GBIF and iNaturalist REST APIs. Both were executed against the
  live APIs during development in an environment with restricted network
  access and failed with a real, specific HTTP error (not a bug) -- see
  `DATA_PROVENANCE.md`. They should work normally on a laptop with ordinary
  internet access.
- **Processing pipeline** (`src/processing/`): real normalisation into a
  shared schema, and real, minimal, documented cleaning. 64 automated tests
  pass against this code (`pytest tests/`).
- **Analysis functions** (`src/analysis/`): real spatial density/NNI,
  taxonomic representation/evenness, temporal coverage, and cross-platform
  comparison functions, all tested.
- **Blind Spot Evidence page** (`pages/04_Blind_Spot_Evidence.py`): the
  core "is this a recording gap or a real biodiversity gap" analysis.
  Ingests real OpenStreetMap road/path network data (`src/ingestion/
  osm_context.py`, a real Overpass API connector) as an accessibility
  proxy, computes a real Spearman correlation between accessibility and
  observation density, and classifies every grid cell into one of four
  evidence categories (likely recording gap / ambiguous / well sampled /
  recorded despite low access) based on quantile thresholds within the
  dataset itself. Also implements a real species-accumulation-curve
  completeness estimator (KnowBR/Hortal et al. method,
  `src/analysis/gap_metrics.py`) and a cross-platform disagreement index
  -- both previously documented stubs, now genuinely computed.
- **Streamlit application** (`app.py`, `pages/`): all 11 pages render
  correctly in both the "no real data yet" state and a data-populated
  state (verified with Streamlit's own `AppTest` framework during
  development). Custom visual theme (hidden Streamlit chrome, real logo
  mark, refined type/spacing) so it doesn't read as a default template.
- **Research Export page** (`pages/08_Research_Export.py`): generates a
  structured Methods + Results Markdown report -- study area, provenance,
  spatial/taxonomic/temporal/cross-platform tables -- computed live from
  whatever real data is currently ingested, downloadable for direct use
  in a paper draft. Refuses to run on an empty dataset (raises rather than
  showing placeholder numbers).
- **Gap-metric framework** (`src/analysis/gap_metrics.py`): a registry of
  candidate metric components. The descriptive ones (density, evenness) are
  genuinely implemented. A completeness estimator and any composite
  "Biodiversity Observation Gap Score" are intentionally **not**
  implemented -- calling them raises `NotImplementedError` with an
  explanation, rather than returning a guessed number.

## What is awaiting real data

Nothing in the codebase is blocked on more code being written. It is
blocked on **you running the ingestion pipeline from a machine with normal
internet access**. Until that happens, every analysis page will honestly
show "Verified dataset pending" instead of a chart.

## Commands you will run locally

```bash
python -m src.pipeline          # run ingestion for both sources
python -m src.ingestion.gbif    # run just GBIF (synchronous search, <100k records)
python -m src.ingestion.gbif_bulk_download   # GBIF async download, needs GBIF_USER/PWD/EMAIL
python -m src.ingestion.inaturalist
python -m src.ingestion.osm_context   # road/path accessibility data (for Blind Spot Evidence page)
pytest tests/                   # run the automated test suite
streamlit run app.py            # launch the application
```

## Unresolved technical/data-access issues

1. **GBIF/iNaturalist connectors are untested against a live network in
   the environment that built them** (sandboxed, no general internet
   access) -- they failed with a real 403 from the sandbox's own egress
   proxy, not from GBIF/iNaturalist. Run them yourself to get real results.
2. **The MMR bounding box is still a hand-built approximation by default**
   -- but `BoundingBox` now supports a real `polygon_wkt`
   (`src/config.py`), wired through to GBIF (native `geometry` param) and
   iNaturalist (rectangle query + local point-in-polygon post-filter via
   `shapely`, with excluded-point counts logged, not silently dropped).
   Once you have an authoritative MMR polygon, set `polygon_wkt` in
   `config.json` -- no other code changes needed.
3. **GBIF's 100,000-record synchronous search cap** now has a real,
   tested fallback: `src/ingestion/gbif_bulk_download.py` uses GBIF's
   asynchronous download endpoint. It correctly reports `UNTESTED` without
   a free GBIF account (`GBIF_USER`/`GBIF_PWD`/`GBIF_EMAIL`), and submits
   + polls + downloads for real once credentials are set. **Parsing the
   downloaded archive into the standard schema is NOT_IMPLEMENTED yet**
   (its file layout differs from the search API's JSON records) -- calling
   `parse_and_normalise_bulk_download()` raises `NotImplementedError`
   rather than guessing at the format. Separately, the interactive
   "Fetch GBIF observations" button in the app is bounded well below this
   100,000 cap (`CONFIG.gbif_interactive_record_limit`, default 8,000) so
   a single click stays reliable on Streamlit Cloud -- see "Staged
   ingestion" above. If GBIF reports more matches than that interactive
   limit, the app says so explicitly rather than implying the fetched
   subset is complete.
4. **India Biodiversity Portal** was investigated in an earlier feasibility
   stage and could not be confirmed as currently active/accessible -- no
   connector was built for it in this stage; see the project's Stage 1/1b
   feasibility reports.
5. **The OSM road/path connector measures vertex density, not true road
   length per cell** -- see `src/ingestion/osm_context.py` for exactly
   what this proxy does and does not capture. Population density (e.g.
   WorldPop) remains a documented, **NOT_IMPLEMENTED** enhancement --
   it would require raster processing (`rasterio`) and large downloads
   that risk reintroducing the exact memory/timeout problems the staged
   biodiversity ingestion redesign fixed. The Overpass query also does
   not yet respect a configured `polygon_wkt` -- it always queries the
   bounding box's rectangular envelope.

## Next step

Run `python -m src.pipeline` on a machine with normal internet access,
read the printed per-source status, and open the app's Methodology page to
see exactly what real data you now have before doing anything else.
