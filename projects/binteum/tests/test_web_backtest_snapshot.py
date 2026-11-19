"""웹 서버·백테스트·스냅샷 생성 테스트."""
from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from binteum import backtest, config, snapshot_build
from binteum.web import Handler, State


# ------------------------------------------------------------------ 웹
@pytest.fixture()
def live_server(tmp_out):
    Handler.state = State(offline=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read()


def post(url: str, payload: dict):
    data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read())


def test_health_and_meta(live_server):
    status, body = get(f"{live_server}/api/health")
    assert status == 200 and json.loads(body)["ok"] is True
    status, body = get(f"{live_server}/api/meta")
    meta = json.loads(body)
    assert meta["emds"] and meta["spots"]
    assert meta["data"]["mode"] in ("mixed", "snapshot", "collected")


def test_static_files(live_server):
    for path, needle in (("/", b"<html"), ("/app.js", b"renderResult"),
                         ("/style.css", b"--teal")):
        status, body = get(f"{live_server}{path}")
        assert status == 200
        assert needle in body


def test_plan_endpoint(live_server):
    status, payload = post(f"{live_server}/api/plan",
                           {"emd": "성산읍", "end_time": "18:00", "party": "family_kid",
                            "mobility": "car", "themes": ["가족"]})
    assert status == 200
    assert payload["ok"] is True
    assert len(payload["plans"]) == 3
    assert payload["data"]["mode"] in ("mixed", "snapshot", "collected")


def test_unknown_path_returns_404(live_server):
    request = urllib.request.Request(f"{live_server}/nope")
    try:
        urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    else:                                   # pragma: no cover
        raise AssertionError("404가 와야 한다")


# ------------------------------------------------------------------ 백테스트
def test_spearman_correctness():
    assert backtest.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert backtest.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert backtest.spearman([1, 2], [1, 2]) is None      # 표본 부족


def test_rank_with_ties():
    assert backtest.ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_backtest_runs_and_writes(tmp_out):
    payload = backtest.run(offline=True)
    assert payload["spots_scored"] > 40
    assert payload["weights_sensitivity"]["rows"]
    assert payload["seasonal_rank"]["mean"] is not None
    assert -1 <= payload["seasonal_rank"]["mean"] <= 1
    paths = backtest.save(payload)
    assert "백테스트" in open(paths["md"], encoding="utf-8").read()


# ------------------------------------------------------------------ 스냅샷
def test_snapshot_is_deterministic(tmp_path):
    a = snapshot_build.build(dest=tmp_path / "a", seed=7)
    b = snapshot_build.build(dest=tmp_path / "b", seed=7)
    for name in ("flow", "tour", "bus", "weather", "wifi"):
        rows_a = json.loads((tmp_path / "a" / f"{name}.json").read_text(encoding="utf-8"))["rows"]
        rows_b = json.loads((tmp_path / "b" / f"{name}.json").read_text(encoding="utf-8"))["rows"]
        assert rows_a == rows_b, name
    assert a["source"] == "synthetic-demo"
    assert set(a["datasets"]) == {"flow", "tour", "bus", "weather", "wifi"}


def test_snapshot_rows_follow_hub_schema(tmp_path):
    snapshot_build.build(dest=tmp_path, seed=7)
    flow = json.loads((tmp_path / "flow.json").read_text(encoding="utf-8"))["rows"][0]
    assert {"baseDate", "city", "emd", "gender", "ageGroup", "resdPop", "workPop",
            "visitPop"} <= set(flow)
    tour = json.loads((tmp_path / "tour.json").read_text(encoding="utf-8"))["rows"][0]
    assert {"date", "name", "payType", "visitors"} <= set(tour)
    weather = json.loads((tmp_path / "weather.json").read_text(encoding="utf-8"))["rows"][0]
    assert {"observatoryName", "baseDate", "dailyRainfall", "maximumWindSpeed"} <= set(weather)
