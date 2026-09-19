# DATA_DICTIONARY.md

Documents every field in the standard internal schema
(`src/processing/schema.py`, `STANDARD_COLUMNS`) that all sources are
normalised into, plus each source's raw field layout as written by its
ingestion connector.

## Standard schema (`data/processed/combined_standard.csv`)

| Field | Type | Description | Populated by |
|---|---|---|---|
| `source` | string | `"GBIF"` \| `"iNaturalist"` | all |
| `record_id` | string | Source's own stable identifier (GBIF: occurrence key; iNaturalist: observation id) | all |
| `scientific_name` | string | Scientific name as given by the source | all |
| `taxonomic_rank` | string | Rank of identification (e.g. "species") where the source provides it | iNaturalist |
| `kingdom` | string | Taxonomic kingdom | GBIF |
| `phylum` | string | Taxonomic phylum | GBIF |
| `taxon_class` | string | Taxonomic class. **Named `taxon_class`, not `class`, because `class` is a reserved word in Python** -- this is a naming choice, not a data change. | GBIF |
| `order` | string | Taxonomic order | GBIF only (iNaturalist connector does not currently fetch full hierarchy) |
| `family` | string | Taxonomic family | GBIF only |
| `genus` | string | Taxonomic genus | GBIF only |
| `latitude` / `longitude` | float | Decimal degrees, WGS84 | all |
| `observation_date` | string | Source-provided date string, unparsed | all |
| `year` | Int64 (nullable) | Parsed year; unparseable/absent stays `<NA>`, never guessed | all |
| `basis_of_record` | string | e.g. `HUMAN_OBSERVATION`, `PRESERVED_SPECIMEN` (GBIF); assumed `HUMAN_OBSERVATION` for iNaturalist | all |
| `dataset` | string | GBIF: `datasetKey` (UUID); iNaturalist: platform name (no per-dataset granularity from this connector) | all |
| `publisher` | string | GBIF: `publishingOrgKey` (UUID); iNaturalist: platform name | all |
| `license` | string | License/terms identifier as given by the source | all |
| `has_media` | bool \| `"UNKNOWN"` | Whether the record has an associated photo/audio. `"UNKNOWN"` (not `False`) when the source's response doesn't disclose this at all -- see below. | all |
| `effort_distance_km` | float (nullable) | Structured survey distance, **only where the source provides it**. Currently always `<NA>` -- neither GBIF nor iNaturalist expose this. | none currently |
| `effort_duration_min` | float (nullable) | Structured survey duration, same caveat as above | none currently |
| `effort_complete_checklist` | bool (nullable) | Whether from a complete (not incidental) checklist, same caveat | none currently |
| `is_test_data` | bool | `False` for every row from a real ingestion connector. `True` only for rows constructed in `tests/`. Analysis code refuses to run (raises `ResearchIntegrityError`) if this is `True` outside of tests. | all (always `False` in real pipeline output) |

Cleaning adds these extra columns (see `src/processing/cleaning.py`):

| Field | Description |
|---|---|
| `invalid_coordinates_flag` | `True` if coordinates are out of range, missing, or exactly (0,0). Flagged, never used to remove the row. |
| `missing_<field>` (several) | `True` if that specific field is missing for that row. |
| `n_missing_core_fields` | Count of the above, per row. |

## `has_media` tri-state, explained

- `True`: the source's response included at least one photo/audio item.
- `False`: the source's response explicitly included a (possibly empty)
  media list/count for this record, and it was empty.
- `"UNKNOWN"`: the source's response for this record didn't include media
  information in a form this connector could interpret at all. This is
  deliberately distinct from `False` -- `False` is evidence of "no media",
  `"UNKNOWN"` is absence of evidence either way.

## Source-specific raw fields (written to `data/raw/`, never modified)

### GBIF (`gbif_raw.csv`) -- see `src/ingestion/gbif.py`, `RAW_FIELDS`
`gbif_key, occurrenceID, species, scientificName, kingdom, phylum, class,
order, family, genus, decimalLatitude, decimalLongitude, eventDate, year,
basisOfRecord, datasetKey, publishingOrgKey, occurrenceStatus, license,
has_media, media_count`

### iNaturalist (`inaturalist_raw.csv`) -- see `src/ingestion/inaturalist.py`, `RAW_FIELDS`
`inat_id, uuid, taxon_name, taxon_rank, iconic_taxon_name, latitude,
longitude, observed_on, quality_grade, license_code, photo_count,
user_login`

Note: `iconic_taxon_name` (e.g. "Aves", "Insecta", "Plantae") is NOT the
same as GBIF's full kingdom/phylum/class hierarchy -- it's iNaturalist's
own coarse category. It is preserved as a bonus column
(`inaturalist_iconic_taxon_name`) alongside the standard schema rather than
forced into `kingdom`/`taxon_class`, to avoid misrepresenting it as a full
taxonomic determination.

## Contextual (non-biodiversity) data: OSM road/path network

`data/raw/osm_roads_raw.csv` -- see `src/ingestion/osm_context.py`,
`RAW_FIELDS`. This is NOT a biodiversity source and is never merged into
`combined_standard.csv` or the standard schema above -- it feeds only the
Blind Spot Evidence page's accessibility analysis
(`src/analysis/blind_spot_evidence.py`).

`way_id, highway_type, vertex_index, latitude, longitude`

One row per geometry vertex of an OSM road/path way. `way_id` groups
vertices belonging to the same road/path; `highway_type` is OSM's own tag
(e.g. `residential`, `path`, `footway`); `vertex_index` is the vertex's
position within its way. Aggregated to a road-vertex-COUNT-per-grid-cell
density proxy by `src/analysis/blind_spot_evidence.py::road_density_by_cell`
-- explicitly not a true road-length-per-cell calculation.

## Why only two sources

An eBird connector was built and tested during development, then
deliberately removed -- see `RESEARCH_METHOD.md`, "Why eBird was removed".
`source` and downstream analysis code are not hard-coded to exactly two
values; a third source could be added later by writing a new
`src/ingestion/<name>.py` connector and a matching `normalise_<name>()` in
`src/processing/cleaning.py`, following the same pattern GBIF and
iNaturalist already use.

## Analysis-derived fields (not stored, computed on demand)

- `major_group` (`src/processing/taxonomy.py::assign_major_group`): a
  coarse, human-readable grouping of `kingdom`/`taxon_class` for charts
  (e.g. "Birds", "Insects", "Plants (other)"). Documented mapping, not a
  taxonomic claim beyond what the source recorded.
- `grid_cell` (`src/analysis/spatial.py::assign_grid_cell`): "lat,lon"
  string identifying the lower-left corner of the configurable-size grid
  cell a record falls into.
