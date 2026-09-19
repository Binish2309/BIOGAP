import pandas as pd

from src.config import BoundingBox
import src.ingestion.inaturalist as inat_module


def test_inaturalist_polygon_post_filter_excludes_points_outside_real_polygon(monkeypatch, tmp_path):
    # Triangle covering only the lower-left half of the rectangle envelope.
    wkt = "POLYGON((72.75 18.75, 73.35 18.75, 72.75 19.50, 72.75 18.75))"
    bbox = BoundingBox(polygon_wkt=wkt)

    fake_rows = [
        {"inat_id": 1, "uuid": "u1", "taxon_name": "Corvus splendens", "taxon_rank": "species",
         "iconic_taxon_name": "Aves", "latitude": 18.80, "longitude": 72.80,  # inside triangle
         "observed_on": "2022-01-01", "quality_grade": "research", "license_code": "CC0",
         "photo_count": 1, "user_login": "a"},
        {"inat_id": 2, "uuid": "u2", "taxon_name": "Pavo cristatus", "taxon_rank": "species",
         "iconic_taxon_name": "Aves", "latitude": 19.45, "longitude": 73.30,  # inside rectangle, outside triangle
         "observed_on": "2022-01-02", "quality_grade": "research", "license_code": "CC0",
         "photo_count": 0, "user_login": "b"},
        {"inat_id": 3, "uuid": "u3", "taxon_name": None, "taxon_rank": None,
         "iconic_taxon_name": None, "latitude": None, "longitude": None,  # missing coords
         "observed_on": None, "quality_grade": "needs_id", "license_code": None,
         "photo_count": 0, "user_login": "c"},
    ]

    def fake_fetch_all_records(bbox_params, per_page, max_results, delay, **kwargs):
        return fake_rows, {"pages_fetched": 1, "used_id_above_strategy": False,
                            "total_results_reported": 3, "hit_result_limit": False}

    monkeypatch.setattr(inat_module, "_fetch_all_records", fake_fetch_all_records)
    # Isolate BOTH the raw CSV and the provenance JSON to tmp_path, so this
    # test never touches the real project's data/raw/ or data/metadata/.
    monkeypatch.setattr(inat_module, "RAW_DIR", tmp_path)
    monkeypatch.setattr(inat_module, "write_provenance",
                         lambda record, filename: (tmp_path / filename).write_text(""))

    record = inat_module.run_inaturalist_ingestion(bbox=bbox, raw_output_name="test_inat_polygon.csv")

    assert record.status == "SUCCESS"
    assert record.records_retrieved == 3
    assert record.records_retained == 1  # only the point inside the real triangle
    reasons = {e["reason"]: e["count"] for e in record.excluded_records}
    assert any("outside the real configured polygon" in r for r in reasons)
    assert any("missing coordinates" in r for r in reasons)
