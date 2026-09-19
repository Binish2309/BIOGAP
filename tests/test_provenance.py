import json

from src.utils.provenance import ProvenanceRecord, write_provenance, untested_connector_record, now_utc_iso
from src.config import METADATA_DIR


def test_untested_connector_record_has_untested_status():
    record = untested_connector_record(
        source="GBIF (bulk download)", source_url_or_api="https://example.invalid",
        query_parameters={"a": 1}, geographic_filter={"bbox": {}},
        reason="no API key",
    )
    assert record.status == "UNTESTED"
    assert record.records_retrieved == 0
    assert "no API key" in record.error_detail


def test_write_provenance_writes_valid_json_and_avoids_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.provenance.METADATA_DIR", tmp_path)
    record = ProvenanceRecord(
        source="GBIF", source_url_or_api="https://api.gbif.org/v1/occurrence/search",
        access_datetime_utc=now_utc_iso(), query_parameters={}, geographic_filter={},
        taxonomic_filter=None, records_retrieved=5, records_retained=5,
        cleaning_operations=[], excluded_records=[], licensing_info=None, status="SUCCESS",
    )
    path1 = write_provenance(record, "test_prov.json")
    path2 = write_provenance(record, "test_prov.json")  # should not overwrite
    assert path1 != path2
    assert path1.exists() and path2.exists()
    data = json.loads(path1.read_text())
    assert data["status"] == "SUCCESS"
    assert data["records_retrieved"] == 5
