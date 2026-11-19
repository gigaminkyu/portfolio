"""Router 테스트 — 한국어 문장에서 제약을 뽑아내는지."""
from __future__ import annotations

from datetime import datetime

import pytest

from binteum.router import Router

NOW = datetime(2026, 11, 16, 13, 10)


@pytest.fixture()
def router():
    return Router(llm=None)


def test_family_with_indoor_and_end_time(router):
    c = router.parse("성산에 있는데 지금 너무 붐벼. 애 데리고 6시까지는 실내, 저녁엔 바다", now=NOW)
    assert c.origin_emd == "성산읍"
    assert c.party == "family_kid"
    assert c.indoor_required is True
    assert c.end_time == "18:00"
    assert "해변" in c.themes


def test_bus_budget_night(router):
    c = router.parse("애월인데 버스 타고 다녀, 예산 3만원, 21시까지 야경", now=NOW)
    assert c.origin_emd == "애월읍"
    assert c.mobility == "bus"
    assert c.budget_krw == 30000
    assert c.end_time == "21:00"
    assert "야경" in c.themes


def test_parents_low_walk(router):
    c = router.parse("중문에서 부모님 모시고 걷기 힘드셔", now=NOW)
    assert c.party == "with_parents"
    assert c.low_walk is True


def test_spot_name_sets_emd(router):
    c = router.parse("성산일출봉 앞이야", now=NOW)
    assert c.origin_spot == "seongsan-ilchulbong"
    assert c.origin_emd == "성산읍"


def test_defaults_when_text_is_empty(router):
    c = router.parse("", emd="구좌읍", now=NOW)
    assert c.origin_emd == "구좌읍"
    assert c.mobility == "car"
    assert c.assumptions, "기본값을 쓴 이유가 남아야 한다"


def test_missing_location_asks_exactly_one_question(router):
    c = router.parse("지금 너무 붐비는데 어디 가지", now=NOW)
    assert c.origin_emd == ""
    assert len(c.asked) == 1


def test_end_time_afternoon_word(router):
    c = router.parse("오후 3시까지 실내 위주로", emd="제주시", now=NOW)
    assert c.end_time == "15:00"


def test_late_start_gets_four_hours(router):
    late = datetime(2026, 11, 16, 19, 0)
    c = router.parse("", emd="연동", now=late)
    assert c.end_time == "23:00"


def test_mobility_explicit_walk(router):
    c = router.parse("도보로 걸어서 다닐 거야", emd="서귀동", now=NOW)
    assert c.mobility == "walk"


def test_themes_list_input(router):
    c = router.parse("", emd="성산읍", themes=["오름", "사진"], now=NOW)
    assert set(c.themes) == {"오름", "사진"}


def test_constraints_serializable(router):
    c = router.parse("성산인데 애랑 3시까지", now=NOW)
    data = c.to_dict()
    assert data["origin_emd"] == "성산읍"
    assert isinstance(data["now"], str)
