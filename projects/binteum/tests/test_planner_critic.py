"""Planner·Critic 테스트 — 제약 준수, 종료시각 복귀, 근거 부착, 반려 규칙."""
from __future__ import annotations

from datetime import datetime

import pytest

from binteum.catalog import catalog
from binteum.critic import Critic
from binteum.models import Plan, Stop
from binteum.planner import PlanContext, Planner, minutes_of
from binteum.router import Router

NOW = datetime(2026, 11, 16, 10, 0)


def make_context(portal, indexer, **kwargs):
    constraints = Router().parse(kwargs.pop("query", ""), now=kwargs.pop("now", NOW), **kwargs)
    scores = indexer.score_all(portal.reference_date)
    weather = None
    return PlanContext(constraints=constraints, ci=scores,
                       day=portal.reference_date, weather=weather)


def test_three_plans_have_distinct_labels_and_stops(portal, indexer):
    ctx = make_context(portal, indexer, emd="성산읍", end_time="18:00", party="family_kid")
    plans = Planner(ctx).build()
    assert [p.key for p in plans] == ["quiet", "short", "theme"]
    assert all(p.stops for p in plans), "각 안은 최소 1곳을 제안해야 한다"
    assert len({p.label for p in plans}) == 3


def test_plan_respects_end_time_and_return(portal, indexer):
    ctx = make_context(portal, indexer, emd="성산읍", end_time="18:00")
    for plan in Planner(ctx).build():
        last = plan.stops[-1]
        assert minutes_of(last.depart) <= minutes_of("18:00")
        # 마지막 정류장에서 출발지로 돌아오는 시간까지 18:00 안에 들어와야 한다
        from binteum import travel
        from binteum.catalog import spots_in_emd
        peers = spots_in_emd("성산읍")
        origin = (sum(s.lat for s in peers) / len(peers), sum(s.lon for s in peers) / len(peers))
        spot = catalog()[last.spot_id]
        back_min, _ = travel.leg_cached((spot.lat, spot.lon), origin, "car")
        assert minutes_of(last.depart) + back_min <= minutes_of("18:00") + 1


def test_indoor_constraint_is_enforced(portal, indexer):
    ctx = make_context(portal, indexer, emd="성산읍", end_time="18:00", indoor=True)
    for plan in Planner(ctx).build():
        for stop in plan.stops:
            assert catalog()[stop.spot_id].indoor, f"{stop.spot_name}는 실외"


def test_low_walk_constraint_is_enforced(portal, indexer):
    ctx = make_context(portal, indexer, emd="중문동", end_time="17:00", party="with_parents")
    for plan in Planner(ctx).build():
        for stop in plan.stops:
            assert catalog()[stop.spot_id].low_walk_ok, stop.spot_name


def test_every_stop_has_evidence(portal, indexer):
    ctx = make_context(portal, indexer, emd="애월읍", end_time="20:00")
    for plan in Planner(ctx).build():
        for stop in plan.stops:
            assert stop.ci >= 0
            assert stop.evidence["hub_ids"]["flow"] == 583
            assert stop.why and "583" in stop.why[0]
            assert stop.evidence["base_date"] == portal.reference_date


def test_no_duplicate_stops(portal, indexer):
    ctx = make_context(portal, indexer, emd="구좌읍", end_time="19:00")
    for plan in Planner(ctx).build():
        ids = [s.spot_id for s in plan.stops]
        assert len(ids) == len(set(ids))


def test_budget_is_respected(portal, indexer):
    ctx = make_context(portal, indexer, emd="성산읍", end_time="18:00", budget=15000)
    for plan in Planner(ctx).build():
        assert plan.totals["cost_krw"] <= 15000


def test_critic_passes_generated_plans(portal, indexer):
    ctx = make_context(portal, indexer, emd="표선면", end_time="18:00")
    plans = Planner(ctx).build()
    reviews = Critic(ctx.constraints).review_all(plans)
    assert all(r.passed for r in reviews.values()), [r.violations for r in reviews.values()]


def _bad_plan(spot_id: str, arrive: str, depart: str, ci: int = 40) -> Plan:
    spot = catalog()[spot_id]
    stop = Stop(order=1, spot_id=spot.id, spot_name=spot.name, emd=spot.emd,
                category=spot.category, indoor=spot.indoor, arrive=arrive, depart=depart,
                dwell_min=60, travel_min=0, travel_km=0.0, ci=ci, ci_label="한산",
                cost_krw=spot.cost_krw,
                why=["테스트"], evidence={"hub_ids": {"flow": 583}, "base_date": "20261116"})
    return Plan(key="quiet", label="테스트", headline="", stops=[stop],
                totals={"stops": 1, "travel_min": 0, "distance_km": 0.0,
                        "cost_krw": spot.cost_krw, "avg_ci": ci, "attraction_min": 60, "span": ""})


def test_critic_rejects_outside_opening_hours(portal, indexer):
    ctx = make_context(portal, indexer, emd="구좌읍", end_time="20:00")
    plan = _bad_plan("manjanggul", "17:30", "18:30")     # 09:00~17:00 밖
    result = Critic(ctx.constraints).review(plan)
    assert not result.passed
    assert any(v.rule == "R1" for v in result.violations)


def test_critic_rejects_missing_evidence(portal, indexer):
    ctx = make_context(portal, indexer, emd="구좌읍", end_time="20:00")
    plan = _bad_plan("bijarim", "10:00", "11:00", ci=-1)
    plan.stops[0].evidence = {}
    result = Critic(ctx.constraints).review(plan)
    assert any(v.rule == "R4" for v in result.violations)


def test_critic_rejects_duplicates_and_impossible_travel(portal, indexer):
    ctx = make_context(portal, indexer, emd="구좌읍", end_time="20:00")
    plan = _bad_plan("bijarim", "10:00", "11:00")
    twin = _bad_plan("bijarim", "11:00", "12:00").stops[0]
    twin.order = 2
    twin.travel_min = 90          # 여유(0분)보다 훨씬 긴 이동
    plan.stops.append(twin)
    result = Critic(ctx.constraints).review(plan)
    rules = {v.rule for v in result.violations}
    assert "R3" in rules and "R2" in rules


def test_critic_rejects_indoor_violation(portal, indexer):
    ctx = make_context(portal, indexer, emd="성산읍", end_time="18:00", indoor=True)
    plan = _bad_plan("gimnyeong-beach", "10:00", "11:00")
    result = Critic(ctx.constraints).review(plan)
    assert any(v.rule == "R6" for v in result.violations)


def test_blocking_spots_collects_ids(portal, indexer):
    ctx = make_context(portal, indexer, emd="구좌읍", end_time="20:00")
    plan = _bad_plan("manjanggul", "17:30", "18:30")
    reviews = {"quiet": Critic(ctx.constraints).review(plan)}
    assert Critic.blocking_spots(reviews) == {"manjanggul"}
