"""
tests/test_inaturalist_interactive_limit.py

Regression test for a real bug found while diagnosing the ingestion
hang: the iNaturalist connector's id_above pagination strategy switched
pagination MODE once max_results was approached, but never actually
STOPPED at max_results -- it would keep paging (bounded only by the API
running out of results) for as long as matching data existed. For a
biodiversity hotspot like Mumbai this could run for a very long time.
_fetch_all_records() must now stop once max_results is reached.
"""

from __future__ import annotations

import src.ingestion.inaturalist as inat_module


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_all_records_stops_at_max_results(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params, timeout):
        calls["n"] += 1
        per_page = params["per_page"]
        # Simulate an API with far more matching records than max_results.
        results = [{"id": calls["n"] * per_page + i, "taxon": {}, "geojson": None, "photos": []}
                   for i in range(per_page)]
        return _FakeResponse({"total_results": 100_000, "results": results})

    monkeypatch.setattr(inat_module, "requests",
                         type("FakeRequests", (), {"get": staticmethod(fake_get)}))

    rows, run_info = inat_module._fetch_all_records(
        bbox_params={}, per_page=200, max_results=500, delay=0.0,
    )

    assert len(rows) >= 500
    assert run_info["hit_result_limit"] is True
    # Before the fix, this loop had no bound tied to max_results at all --
    # it would have kept calling fake_get indefinitely (bounded here only
    # by this test's fake always returning a full page). A tight call
    # count confirms the new explicit stop condition is what ended it.
    assert calls["n"] <= 5


def test_fetch_all_records_reports_progress(monkeypatch):
    def fake_get(url, params, timeout):
        results = [{"id": 1, "taxon": {}, "geojson": None, "photos": []}]
        return _FakeResponse({"total_results": 1, "results": results if params.get("page", 2) == 1 else []})

    monkeypatch.setattr(inat_module, "requests",
                         type("FakeRequests", (), {"get": staticmethod(fake_get)}))

    messages = []
    rows, run_info = inat_module._fetch_all_records(
        bbox_params={}, per_page=200, max_results=500, delay=0.0,
        on_progress=messages.append,
    )

    assert any("Connecting to iNaturalist" in m for m in messages)
    assert any("Fetched" in m for m in messages)
