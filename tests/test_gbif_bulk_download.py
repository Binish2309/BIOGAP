import pytest

from src.config import BoundingBox
from src.ingestion.gbif_bulk_download import (
    _build_geometry_predicate, request_bulk_download, parse_and_normalise_bulk_download,
)


def test_build_geometry_predicate_from_rectangle():
    bbox = BoundingBox(min_lat=18.75, max_lat=19.50, min_lon=72.75, max_lon=73.35)
    predicate = _build_geometry_predicate(bbox)
    assert predicate.startswith("geometry = POLYGON((")
    assert "72.75 18.75" in predicate  # lon lat order, as GBIF/WKT expects


def test_build_geometry_predicate_from_polygon_passthrough():
    wkt = "POLYGON((72.75 18.75, 73.35 18.75, 73.35 19.5, 72.75 19.5, 72.75 18.75))"
    bbox = BoundingBox(polygon_wkt=wkt)
    predicate = _build_geometry_predicate(bbox)
    assert predicate == f"geometry = {wkt}"


def test_request_bulk_download_is_untested_without_credentials(monkeypatch, tmp_path):
    for var in ("GBIF_USER", "GBIF_PWD", "GBIF_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    # Redirect provenance writes to an isolated tmp dir so this test never
    # touches the real project's data/metadata/ folder.
    import src.ingestion.gbif_bulk_download as mod
    monkeypatch.setattr(mod, "write_provenance",
                         lambda record, filename: (tmp_path / filename).write_text(""))
    record = request_bulk_download(poll=False)
    assert record.status == "UNTESTED"
    assert "GBIF_USER" in record.error_detail


def test_parse_and_normalise_bulk_download_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        parse_and_normalise_bulk_download(None)
