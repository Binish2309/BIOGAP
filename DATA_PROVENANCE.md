# DATA_PROVENANCE.md

How real data is sourced, tracked, and audited in BIOGAP.

## The provenance contract

Every ingestion run, from every source, produces a `ProvenanceRecord`
(`src/utils/provenance.py`) written to `data/metadata/<source>_provenance.json`,
containing:

- `source`, `source_url_or_api` -- exactly which platform and endpoint
- `access_datetime_utc` -- when the request was made
- `query_parameters` -- the exact parameters sent
- `geographic_filter` -- the bounding box used, and whether it's an
  official polygon (`is_official_polygon`) or a feasibility approximation
- `records_retrieved` / `records_retained`
- `cleaning_operations` -- what was done at the ingestion stage (currently
  none -- cleaning is a separate stage, see `cleaning_report` in the
  pipeline summary)
- `excluded_records` -- records dropped and why (currently always empty at
  ingestion; exact-duplicate removal happens at the cleaning stage and is
  logged there instead)
- `licensing_info` -- the license mix actually observed in the download
- `status` -- one of `SUCCESS`, `FAILED`, `UNTESTED`
- `error_detail` -- the real exception, verbatim, if `FAILED`
- `extra_notes` -- source-specific caveats (e.g. GBIF's 100k offset cap)

Existing provenance files are never overwritten -- a re-run appends a
numbered suffix (`gbif_provenance_1.json`, etc.), so the history of every
ingestion attempt is preserved.

Running `python -m src.pipeline` (both sources), or clicking either of
the Overview page's staged "Fetch GBIF observations" / "Add iNaturalist
observations" buttons (one source at a time), writes a combined
`data/metadata/pipeline_run_summary.json` bundling every source's most
recent provenance plus the cleaning report and
overall `data_status` for that run. A separate, intentionally-overwritten
`data/metadata/latest_source_state.json` tracks only "what each source's
most recent successful attempt was" so a single-source run can recombine
its fresh data with the other sources' prior results without re-running
them -- this file is app state, not an audit trail, and does not replace
the numbered provenance history above.

## Status meanings -- read carefully

- **SUCCESS**: the connector reached the live API and got a real (possibly
  zero-record) response. `records_retained` tells you how many rows made
  it into `data/raw/` and onward.
- **FAILED**: the connector reached out but got a real error (network,
  HTTP, timeout). The exact exception is in `error_detail`. No data is
  written for that source. This is NOT the same as `UNTESTED`.
- **UNTESTED**: the connector was never attempted -- currently only occurs
  for `src/ingestion/gbif_bulk_download.py` when no GBIF account
  credentials are configured. This is explicit so it's never confused
  with a network failure.

## What actually happened during development

This codebase was written and reviewed in a sandboxed environment with
restricted network access (no general internet, only software-package
registries reachable). Both the GBIF and iNaturalist connectors were
executed for real against their live endpoints and got a real `403
Forbidden` from the sandbox's own egress proxy -- not from GBIF or
iNaturalist. This is recorded, verbatim, in this project's development
history. It means:

- The connector CODE has been syntax-checked, unit-tested (with mock data,
  isolated in `tests/`), and confirmed to make a correctly-formed request
  to the correct real endpoint.
- The connector has **not** been confirmed to successfully retrieve and
  parse a real GBIF/iNaturalist response, because no real response was
  ever received in that environment.
- Running it from a normal laptop with ordinary internet access is the
  actual test, and its result should be trusted over any assumption made
  here.


## Licensing, by source

- **GBIF**: license is set per record by the original publisher, always
  present in the download metadata (`CC0_1_0`, `CC_BY_4_0`,
  `CC_BY_NC_4_0`, or similar). `licensing_info` in the provenance record
  reports the actual mix observed in each run -- do not assume a single
  license for the whole dataset.
- **iNaturalist**: license set per observation by the uploader, same three
  common options as GBIF. This connector does not filter by
  `quality_grade`, so both "research" and "needs_id" grade observations
  are included -- note this if comparing counts to GBIF's iNaturalist
  mirror, which only republishes Research Grade observations.
- **OpenStreetMap (contextual, not a biodiversity source)**: Open Database
  License (ODbL) -- share-alike, attribution to "OpenStreetMap
  contributors" required in any published output using this data (e.g. a
  research paper figure built from the blind-spot evidence map). Fetched
  via the free, key-free Overpass API; see `src/ingestion/osm_context.py`
  for exactly what is queried and why it is a vertex-count proxy, not a
  true road-length measurement.

## Geographic filter status

The current geographic filter (`src/config.py::BoundingBox`, default
lat 18.75-19.50, lon 72.75-73.35) is a **hand-built rectangular
approximation** of the Mumbai Metropolitan Region, constructed from known
reference coordinates of MMR's constituent cities/towns -- it is NOT an
official MMRDA administrative polygon. Every provenance record's
`geographic_filter.is_official_polygon` field is `false` until this is
replaced with a real polygon (see RESEARCH_METHOD.md for the planned
approach). Note: the OSM/Overpass connector currently always queries the
bounding box's rectangular envelope regardless of `polygon_wkt` -- see
`src/ingestion/osm_context.py`'s module docstring.
