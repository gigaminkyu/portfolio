"""CI 산식 단위 테스트 — 재정규화·백분위·날씨항·시간대 추정."""
from __future__ import annotations

import pytest

from binteum import config, travel
from binteum.index import (CrowdIndexer, hour_estimate, hour_factor, label_for,
                           percentile, renormalize, weather_severity, weather_term)


def test_weights_sum_to_one():
    assert sum(config.CI_WEIGHTS.values()) == pytest.approx(1.0)


def test_renormalize_drops_missing_bus_and_rebalances():
    terms = {"visit": 0.8, "tour": 0.6, "bus": None, "weather": 0.2}
    ci, weights, dropped = renormalize(terms)
    assert dropped == ["bus"]
    assert "bus" not in weights
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    # 남은 항으로만 계산: (0.45*0.8 + 0.25*0.6 + 0.10*0.2) / 0.80
    expected = (0.45 * 0.8 + 0.25 * 0.6 + 0.10 * 0.2) / 0.80 * 100
    assert ci == pytest.approx(round(expected, 1))


def test_renormalize_all_missing_returns_zero():
    ci, weights, dropped = renormalize({"visit": None, "bus": None})
    assert ci == 0.0 and weights == {}
    assert set(dropped) == {"visit", "bus"}


def test_renormalize_clamps_out_of_range():
    ci, _, _ = renormalize({"visit": 2.0, "tour": -1.0, "bus": 0.5, "weather": 0.5})
    assert 0 <= ci <= 100


def test_percentile_midrank():
    population = [10, 20, 30, 40]
    assert percentile(10, population) == pytest.approx(0.125)
    assert percentile(40, population) == pytest.approx(0.875)
    assert percentile(25, population) == pytest.approx(0.5)
    assert percentile(10, []) is None


def test_percentile_ties_get_average_rank():
    assert percentile(20, [20, 20, 20]) == pytest.approx(0.5)


def test_weather_term_moves_outdoor_and_indoor_opposite():
    severe = weather_severity(rain_mm=10, wind_max=0)
    assert severe == pytest.approx(1.0)
    assert weather_term(1.0, indoor=False) == 0.0
    assert weather_term(1.0, indoor=True) == 1.0
    assert weather_term(0.0, indoor=False) == 0.5
    assert weather_term(0.0, indoor=True) == 0.5


def test_weather_severity_triggers_on_wind():
    assert weather_severity(0, 10) > 0.6
    assert weather_severity(0, 0) == 0.0


def test_labels_thresholds():
    assert label_for(80) == "붐빔"
    assert label_for(70) == "붐빔"
    assert label_for(69.9) == "보통"
    assert label_for(45) == "보통"
    assert label_for(44.9) == "한산"


def test_hour_factor_and_estimate_bounds():
    assert 0.0 <= hour_factor("해변", 13) <= 1.0
    assert hour_factor("해변", 13) > hour_factor("해변", 4)
    for hour in range(24):
        value = hour_estimate(80, "시장", hour)
        assert 0 <= value <= 100
    assert hour_estimate(100, "시장", 0) <= 100


def test_travel_time_grows_with_distance_and_mode():
    near = travel.leg_cached((33.46, 126.94), (33.47, 126.95), "car")
    far = travel.leg_cached((33.46, 126.94), (33.24, 126.55), "car")
    assert near[0] < far[0]
    car = travel.leg_cached((33.46, 126.94), (33.24, 126.55), "car")
    bus = travel.leg_cached((33.46, 126.94), (33.24, 126.55), "bus")
    walk = travel.leg_cached((33.46, 126.94), (33.24, 126.55), "walk")
    assert car[0] < bus[0] < walk[0]


def test_indexer_uses_only_percentiles_not_absolute_counts(portal_fixture):
    portal, indexer = portal_fixture
    from binteum.catalog import catalog
    spot = catalog()["seongsan-ilchulbong"]
    score = indexer.score(spot)
    assert 0 <= score.ci <= 100
    assert score.evidence["visit"]["unit"].startswith("연인원")
    assert "몇 명" not in str(score.evidence)
    assert score.evidence["visit"]["hub_id"] == 583
    assert set(score.terms) == {"visit", "tour", "bus", "weather"}
