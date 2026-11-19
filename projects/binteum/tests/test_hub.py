"""허브 클라이언트 테스트 — 가짜 Transport로 200/502/403/타임아웃/캐시 4경로 재현.

이 개발 환경은 허브가 WAF로 차단되어(403) 실호출이 불가능하다. 그래서 '실시간 모드가
정말 동작하는가'를 코드 레벨에서 검증하는 것이 이 테스트의 목적이다.
"""
from __future__ import annotations

import json

import pytest

from binteum import config
from binteum.hub import FetchResult, HubClient, HttpResponse, _rows_from_payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        item = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def flow_payload(rows=3):
    return {"data": [
        {"baseDate": f"2026111{i}", "emd": "성산읍", "visitPop": 1000 + i} for i in range(rows)
    ]}


def test_live_fetch_success_and_endpoint_shape(tmp_path):
    """실제 엔드포인트는 /api/proxy/{데이터키}/{프로젝트키} 이고 키는 경로에 들어간다."""
    transport = FakeTransport([HttpResponse(200, json.dumps(flow_payload()))])
    client = HubClient(key="TESTKEY", transport=transport, cache_dir=tmp_path)
    result = client.fetch("flow", {"startDate": "20261101", "endDate": "20261115"})
    assert result.mode == "live" and result.rows
    call = transport.calls[0]
    assert call["url"].endswith("/" + config.DATASET_DATA_KEYS["flow"] + "/TESTKEY")
    assert "api/proxy" in call["url"]
    assert call["params"]["startDate"] == "20261101"
    assert call["params"]["limit"] == config.HUB_PAGE_LIMIT
    assert "key" not in call["params"] and "id" not in call["params"]
    assert result.requests == 1


def test_second_call_hits_cache_without_network(tmp_path):
    transport = FakeTransport([HttpResponse(200, json.dumps(flow_payload()))])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path)
    first = client.fetch("flow")
    second = client.fetch("flow")
    assert first.mode == "live"
    assert second.mode == "cache"
    assert len(transport.calls) == 1


def test_502_retries_then_reports_error(tmp_path, monkeypatch):
    monkeypatch.setitem(config.DATASET_DATA_KEYS, "bus", "BUSKEY")
    transport = FakeTransport([HttpResponse(502, ""), HttpResponse(502, "")])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path, retries=1,
                       sleep=lambda s: None)
    result = client.fetch("bus")
    assert result.mode == "error"
    assert not result.ok
    assert len(transport.calls) == 2
    assert "502" in result.error


def test_403_waf_is_not_retried(tmp_path):
    transport = FakeTransport([HttpResponse(403, "<html>blocked</html>")])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path, retries=3,
                       sleep=lambda s: None)
    result = client.fetch("flow")
    assert result.mode == "error"
    assert len(transport.calls) == 1, "403/400은 재시도해도 같으므로 1회만 호출"


def test_network_exception_is_contained(tmp_path):
    transport = FakeTransport([TimeoutError("timed out")])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path, retries=0,
                       sleep=lambda s: None)
    result = client.fetch("flow")
    assert result.mode == "error"
    assert "TimeoutError" in result.error


def test_unconnected_dataset_is_not_called(tmp_path):
    transport = FakeTransport([HttpResponse(200, json.dumps(flow_payload()))])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path)
    result = client.fetch("weather")
    assert result.mode == "not_connected" and not result.rows
    assert transport.calls == []


def test_has_more_splits_range_into_two_calls(tmp_path):
    """100행 상한에 걸리면 날짜 구간을 쪼개 두 번 호출하고 행을 합친다."""
    page = {"totCnt": 150, "hasMore": True, "data": [
        {"baseDate": "20261101", "emd": "성산읍", "visitPop": 1}]}
    tail = {"totCnt": 1, "hasMore": False, "data": [
        {"baseDate": "20261102", "emd": "성산읍", "visitPop": 2}]}
    transport = FakeTransport([
        HttpResponse(200, json.dumps(page)),
        HttpResponse(200, json.dumps(tail)),
        HttpResponse(200, json.dumps(tail)),
    ])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path)
    result = client.fetch("flow", {"startDate": "20261101", "endDate": "20261102"},
                          use_cache=False)
    # 1) 원구간 호출(hasMore) → 2) 왼쪽 날짜 3) 오른쪽 날짜 = 3회, 행은 두 조각의 합
    assert result.mode == "live" and len(result.rows) == 2
    assert result.requests == 3
    starts = sorted(c["params"]["startDate"] for c in transport.calls)
    assert starts == ["20261101", "20261101", "20261102"]


def test_no_key_means_missing_key_mode(tmp_path):
    transport = FakeTransport([HttpResponse(200, json.dumps(flow_payload()))])
    client = HubClient(key="", transport=transport, cache_dir=tmp_path)
    result = client.fetch("flow")
    assert result.mode == "missing_key"
    assert transport.calls == []


def test_html_error_page_is_not_parsed(tmp_path):
    transport = FakeTransport([HttpResponse(200, "<html>error</html>")])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path, retries=0,
                       sleep=lambda s: None)
    assert client.fetch("flow").rows == []


@pytest.mark.parametrize("payload", [
    [{"a": 1}],
    {"data": [{"a": 1}]},
    {"items": [{"a": 1}]},
    {"response": {"body": {"items": [{"a": 1}]}}},
    {"result": [{"a": 1}]},
])
def test_rows_from_payload_shapes(payload):
    assert _rows_from_payload(payload) == [{"a": 1}]


def test_rows_from_payload_garbage():
    assert _rows_from_payload("nope") == []
    assert _rows_from_payload({"data": "nope"}) == []


def test_fetch_result_ok_requires_rows():
    assert not FetchResult(dataset="flow", hub_id=583, mode="live", rows=[]).ok
    assert FetchResult(dataset="flow", hub_id=583, mode="cache", rows=[{}]).ok


def test_probe_reports_mode(tmp_path):
    transport = FakeTransport([HttpResponse(200, json.dumps(flow_payload()))])
    client = HubClient(key="K", transport=transport, cache_dir=tmp_path)
    probe = client.probe()
    assert probe["has_key"] is True
    assert probe["mode"] == "live"
    assert probe["rows"] == 3
