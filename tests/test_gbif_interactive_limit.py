"""
tests/test_gbif_interactive_limit.py

Regression test for the root cause of the "Run ingestion pipeline hangs
on Streamlit Cloud" bug: GBIF's synchronous search API had no fetch
bound smaller than the 100,000-record offset ceiling, so a single
interactive click could require ~334 sequential paginated requests.
_fetch_all_records() must now stop once max_records is reached, and
report that honestly via hit_interactive_limit -- never claiming the
partial result is the complete matching set.
"""

from __future__ import annotations

import src.ingestion.gbif as gbif_module


class _FakePage:
    def __init__(self, count, results, end_of_records):
        self._d = {"count": count, "results": results, "endOfRecords": end_of_records}

    def get(self, key, default=None):
        return self._d.get(key, default)


def test_fetch_all_records_stops_at_interactive_limit(monkeypatch):
    total_matching = 50_000  # GBIF reports far more than we want to fetch interactively
    calls = {"n": 0}

    def fake_search(offset, limit, **query_params):
        calls["n"] += 1
        results = [{"key": offset + i} for i in range(limit)]
        return {"count": total_matching, "results": results, "endOfRecords": False}

    monkeypatch.setattr(gbif_module, "occurrences",
                         type("FakeOccurrences", (), {"search": staticmethod(fake_search)}))

    records, run_info = gbif_module._fetch_all_records(
        query_params={}, page_size=100, max_offset=100_000, delay=0.0,
        max_records=250,
    )

    assert len(records) >= 250
    assert run_info["hit_interactive_limit"] is True
    assert run_info["hit_offset_cap"] is False
    # Should stop after ~3 pages (250/100), nowhere near the 100k offset cap.
    assert calls["n"] <= 4


def test_fetch_all_records_reports_progress(monkeypatch):
    def fake_search(offset, limit, **query_params):
        return {"count": 10, "results": [{"key": offset + i} for i in range(min(limit, 10 - offset))],
                "endOfRecords": offset + limit >= 10}

    monkeypatch.setattr(gbif_module, "occurrences",
                         type("FakeOccurrences", (), {"search": staticmethod(fake_search)}))

    messages = []
    records, run_info = gbif_module._fetch_all_records(
        query_params={}, page_size=5, max_offset=100_000, delay=0.0,
        max_records=None, on_progress=messages.append,
    )

    assert len(records) == 10
    assert any("Connecting to GBIF" in m for m in messages)
    assert any("Fetched" in m for m in messages)
