"""카탈로그·데이터 로딩 테스트 — 스키마, 결측, 별칭 파싱, 스냅샷 우선순위."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from binteum import catalog, config, fields
from binteum.data import DataPortal


def test_catalog_size_and_uniqueness():
    spots = catalog.spots()
    assert 40 <= len(spots) <= 80, "카탈로그는 40~60곳 규모로 유지한다"
    assert len({s.id for s in spots}) == len(spots)
    assert len(catalog.emds()) >= 20
    assert len(catalog.routes()) >= 10


def test_catalog_times_and_flags():
    for spot in catalog.spots():
        assert 0 <= spot.open_min() <= 24 * 60
        assert 0 < spot.close_min() <= 24 * 60
        assert spot.dwell_min >= 20
        assert spot.cost_krw >= 0
        assert spot.themes, spot.id
        assert 33.0 < spot.lat < 33.7 and 126.0 < spot.lon < 127.1, spot.id


def test_find_spot_and_near_emd():
    assert catalog.find_spot("성산일출봉").id == "seongsan-ilchulbong"
    assert catalog.find_spot("지금 성산일출봉 앞인데 붐벼").id == "seongsan-ilchulbong"
    assert catalog.near_emd("성산에 있는데 너무 붐벼") == "성산읍"
    assert catalog.near_emd("중문") == "중문동"
    assert catalog.near_emd("") == ""


def test_field_aliases_and_masking():
    row = {"baseDate": "2026-11-15", "emd": "성산읍", "visitPop": "***", "resdPop": 1200}
    assert fields.norm_date(row["baseDate"]) == "20261115"
    assert fields.pick(row, "emd") == "성산읍"
    assert fields.as_int(fields.pick(row, "visit_pop")) == 0        # 마스킹은 0으로
    assert fields.as_int(fields.pick(row, "resd_pop")) == 1200
    assert fields.as_int("1,234") == 1234
    assert fields.norm_month("2024.12") == "202412"


def test_snapshot_provenance_marks_synthetic(snapshot_dir):
    manifest = json.loads((Path(snapshot_dir) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "synthetic-demo"
    assert manifest["datasets"], "데이터셋 목록이 비어 있으면 안 된다"


def test_portal_loads_all_five_datasets(portal):
    assert portal.datasets["flow"].ok
    for name in ("flow", "tour", "bus", "weather", "wifi"):
        assert portal.datasets[name].ok, name
    modes = {d.mode for d in portal.provenance.datasets}
    # flow 는 ZIP 동봉 실측 수집분(collected), 나머지는 합성 데모 스냅샷(snapshot)
    assert modes == {"snapshot", "collected"}
    assert portal.datasets["flow"].prov.mode == "collected"
    assert portal.provenance.mode == "mixed"
    note = portal.provenance.note
    assert "실측" in note and "합성" in note


def test_portal_series_helpers(portal):
    series = portal.visit_series("성산읍")
    assert len(series) > 30
    assert all(isinstance(v, int) and v > 0 for v in series.values())
    tour = portal.tour_series("성산일출봉")
    assert max(tour) == "202412"
    bus = portal.bus_series(("101",))
    assert bus
    weather = portal.weather_for(33.45, 126.94)
    assert weather is not None and weather.observatory in ("성산", "제주", "서귀포", "고산")


def test_portal_prefers_collected_over_snapshot(tmp_path, monkeypatch):
    from binteum import config as cfg

    snap = tmp_path / "snap"
    live = tmp_path / "live"
    snap.mkdir()
    live.mkdir()
    (snap / "flow.json").write_text(json.dumps({"meta": {"source": "synthetic-demo"}, "rows": [
        {"baseDate": "20261115", "emd": "성산읍", "visitPop": 100}]}), encoding="utf-8")
    (live / "flow.json").write_text(json.dumps({"meta": {"source": "jeju-datahub-live"}, "rows": [
        {"baseDate": "20261115", "emd": "성산읍", "visitPop": 999}]}), encoding="utf-8")
    portal = DataPortal(offline=True, snapshot_dir=snap, live_dir=live)
    portal.load()
    assert portal.datasets["flow"].prov.mode == "collected"
    assert portal.visit_series("성산읍")["20261115"] == 999


def test_missing_dataset_degrades_without_crash(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "flow.json").write_text(json.dumps({"meta": {}, "rows": [
        {"baseDate": "20261115", "emd": "성산읍", "visitPop": 10}]}), encoding="utf-8")
    portal = DataPortal(offline=True, snapshot_dir=snap, live_dir=tmp_path / "none")
    portal.load()
    assert portal.datasets["bus"].prov.mode == "missing"
    assert portal.provenance.mode == "snapshot"


def test_empty_portal_reports_empty(tmp_path):
    portal = DataPortal(offline=True, snapshot_dir=tmp_path / "empty", live_dir=tmp_path / "none")
    provenance = portal.load()
    assert provenance.mode == "empty"
    assert all(d.mode == "missing" for d in provenance.datasets)


@pytest.mark.parametrize("raw,expected", [
    ({"관광지명": "성산일출봉", "날짜": "2024-12", "관광객수": "1,000"},
     {"name": "성산일출봉", "month": "202412", "visitors": 1000}),
    ({"touristName": "비자림", "base_ym": "202407", "touristCnt": 25},
     {"name": "비자림", "month": "202407", "visitors": 25}),
])
def test_tour_normalization_aliases(raw, expected):
    record = DataPortal._norm_tour(raw)
    for key, value in expected.items():
        assert record[key] == value


def test_flow_normalization_skips_incomplete_rows():
    assert DataPortal._norm_flow({"baseDate": "20261115"}) is None
    assert DataPortal._norm_flow({"emd": "성산읍"}) is None
    assert DataPortal._norm_flow({"summary": "..."}) is None
