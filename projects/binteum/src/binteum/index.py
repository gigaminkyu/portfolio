"""Index Agent — 혼잡지수(CI) 계산. **LLM이 아니라 순수 파이썬**이다.

    CI(i,t) = 100 × Σ w_k·P_k / Σ w_k     (결측 항은 제외 후 자동 재정규화)

    P_visit  : 583 읍면동 방문인구(visitPop)의 "최근 8주 동일 요일유형" 백분위
    P_tour   : 591 관광지 월별 관광객수 ÷ 최근 3년 동월 최대값 (계절 기준선)
    P_bus    : 614 노선 이용자수의 "최근 8주 동일 요일유형" 백분위
    P_weather: 강수·강풍 심각도 → 야외 -, 실내 + (0~1 클램프)

설계상 중요한 두 가지:
① 583의 visitPop은 "하루 동안 시간대별 방문인구를 더한 연인원"이므로(운영진 답변)
   절대 인원으로 표기하지 않고 **백분위만** 쓴다. 몇 명인지는 화면에 쓰지 않는다.
② 614 API가 502로 죽어도 지수가 조용히 틀리지 않도록, 결측 항의 가중치를
   남은 항에 재분배하고 화면에 "버스 데이터 제외" 배지를 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping

from . import config
from .catalog import catalog
from .data import DataPortal
from .models import CrowdScore, Spot

LABELS = ((70.0, "붐빔"), (45.0, "보통"), (0.0, "한산"))


def weekday_type(day: str) -> str:
    """평일/주말 구분. 공휴일은 고려하지 않는다(한계로 문서화)."""
    try:
        d = datetime.strptime(day, "%Y%m%d")
    except ValueError:
        return "weekday"
    return "weekend" if d.weekday() >= 5 else "weekday"


def percentile(value: float, population: Iterable[float]) -> float | None:
    """경험적 백분위(0~1, mid-rank). 표본이 비면 None."""
    values = [v for v in population if v is not None]
    if not values:
        return None
    less = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (less + 0.5 * equal) / len(values)


def label_for(ci: float) -> str:
    for threshold, name in LABELS:
        if ci >= threshold:
            return name
    return "한산"


def renormalize(terms: Mapping[str, float | None],
                weights: Mapping[str, float] | None = None) -> tuple[float, dict, list[str]]:
    """결측(None) 항을 제외하고 남은 가중치 합이 1이 되도록 재정규화한다."""
    weights = dict(weights or config.CI_WEIGHTS)
    used = {k: float(v) for k, v in terms.items() if v is not None}
    dropped = sorted(k for k, v in terms.items() if v is None)
    total = sum(weights.get(k, 0.0) for k in used)
    if not used or total <= 0:
        return 0.0, {}, dropped
    used_weights = {k: weights.get(k, 0.0) / total for k in used}
    ci = sum(used_weights[k] * max(0.0, min(1.0, used[k])) for k in used) * 100.0
    return round(ci, 1), {k: round(v, 4) for k, v in used_weights.items()}, dropped


def weather_term(severity: float, indoor: bool) -> float:
    """악천후일수록 야외는 한산(낮게), 실내는 붐빔(높게)."""
    severity = max(0.0, min(1.0, severity))
    value = 0.5 + 0.5 * severity if indoor else 0.5 - 0.5 * severity
    return max(0.0, min(1.0, value))


def weather_severity(rain_mm: float, wind_max: float) -> float:
    rain = min(1.0, max(0.0, rain_mm) / config.WEATHER_RAIN_FULL_MM)
    wind = min(1.0, max(0.0, wind_max) / config.WEATHER_WIND_FULL_MS)
    return max(rain, wind)


def hour_factor(category: str, hour: int) -> float:
    """시간대 가정 곡선(assumption). 실측이 아니므로 화면에 '추정'으로 표기한다."""
    profile = config.HOUR_PROFILE_ASSUMPTION.get(category, config.DEFAULT_HOUR_PROFILE)
    keys = sorted(profile)
    hour = max(0, min(23, int(hour)))
    low = max(k for k in keys if k <= hour)
    high = min((k for k in keys if k >= hour), default=low)
    if high == low:
        return profile[low]
    ratio = (hour - low) / (high - low)
    return profile[low] + (profile[high] - profile[low]) * ratio


def hour_estimate(ci: float, category: str, hour: int) -> int:
    """일 단위 CI에 시간대 가정 곡선을 곱한 '추정' 값(0~100)."""
    factor = hour_factor(category, hour)
    return int(round(max(0.0, min(100.0, ci * (0.6 + 0.4 * factor)))))


@dataclass
class _Window:
    days: list[str]
    same_type: list[str]


class CrowdIndexer:
    def __init__(self, portal: DataPortal, trace=None):
        self.portal = portal
        self.trace = trace
        self._cache: dict[tuple[str, str], CrowdScore] = {}

    # ---------------------------------------------------------------- 공개
    def score(self, spot: Spot, day: str | None = None) -> CrowdScore:
        day = day or self.portal._ref()
        key = (spot.id, day)
        if key in self._cache:
            return self._cache[key]

        evidence: dict = {}
        terms: dict[str, float | None] = {}

        # ---- P_visit (583)
        series = self.portal.visit_series(spot.emd)
        window = self._window(day, config.BASELINE_WEEKS)
        same_type = [d for d in window.days if weekday_type(d) == weekday_type(day)]
        current = series.get(day)
        if current is None and series:
            latest = max(series)
            current = series[latest]
            evidence["visit_fallback_date"] = latest
        population = [series[d] for d in same_type if d in series]
        terms["visit"] = percentile(current, population) if current is not None else None
        evidence["visit"] = {
            "hub_id": config.DATASET_IDS["flow"], "emd": spot.emd,
            "base_date": day, "weekday_type": weekday_type(day),
            "sample_days": len(population), "rank_pct": terms["visit"],
            "unit": "연인원(일 합계) — 백분위만 사용",
        }

        # ---- P_tour (591)
        tour = self.portal.tour_series(spot.name)
        if not tour:
            emd_peers = [s for s in catalog().values() if s.emd == spot.emd and s.id != spot.id]
            for peer in emd_peers:
                tour = self.portal.tour_series(peer.name)
                if tour:
                    evidence["tour_proxy"] = peer.name
                    break
        terms["tour"] = self._tour_term(tour, day)
        evidence["tour"] = {
            "hub_id": config.DATASET_IDS["tour"],
            "matched_name": evidence.get("tour_proxy", spot.name),
            "latest_month": max(tour) if tour else "",
            "monthwise_available": len(tour),
            "rank": terms["tour"],
            "unit": "월 관광객수 ÷ 최근 3년 동월 최대값",
        }

        # ---- P_bus (614)
        bus = self.portal.bus_series(spot.near_routes)
        bus_current = bus.get(day)
        if bus_current is None and bus:
            bus_current = bus[max(bus)]
        bus_population = [bus[d] for d in same_type if d in bus]
        terms["bus"] = percentile(bus_current, bus_population) if bus_current is not None else None
        evidence["bus"] = {
            "hub_id": config.DATASET_IDS["bus"], "routes": list(spot.near_routes),
            "base_date": day, "sample_days": len(bus_population),
            "rank_pct": terms["bus"],
        }

        # ---- P_weather (579 + 578 좌표)
        weather = self.portal.weather_for(spot.lat, spot.lon, day)
        if weather is not None:
            severity = weather_severity(weather.rain, weather.wind_max)
            terms["weather"] = weather_term(severity, spot.indoor)
            evidence["weather"] = {
                "hub_id": config.DATASET_IDS["weather"], "observatory": weather.observatory,
                "base_date": weather.date, "rain_mm": weather.rain,
                "wind_max_ms": weather.wind_max, "severity": round(severity, 3),
                "indoor": spot.indoor, "term": round(terms["weather"], 3),
            }
        else:
            terms["weather"] = None
            evidence["weather"] = {"hub_id": config.DATASET_IDS["weather"], "missing": True}

        ci, weights_used, dropped = renormalize(terms)
        confidence = "ok"
        if len(population) < 20 or (terms["bus"] is not None and len(bus_population) < 20):
            confidence = "low_sample"
        if dropped:
            confidence = "partial" if confidence == "ok" else confidence

        result = CrowdScore(spot_id=spot.id, spot_name=spot.name, ci=ci,
                            terms={k: (round(v, 4) if v is not None else None)
                                   for k, v in terms.items()},
                            weights_used=weights_used, dropped=dropped,
                            evidence=evidence, label=label_for(ci), confidence=confidence)
        self._cache[key] = result
        return result

    def score_all(self, day: str | None = None) -> dict[str, CrowdScore]:
        return {spot_id: self.score(spot, day) for spot_id, spot in catalog().items()}

    @staticmethod
    def estimate_at(ci: float, category: str, hour: int) -> int:
        return hour_estimate(ci, category, hour)

    # ---------------------------------------------------------------- 내부
    @staticmethod
    def _tour_term(tour: Mapping[str, int], day: str) -> float | None:
        if not tour:
            return None
        month = day[4:6]
        years = sorted({int(m[:4]) for m in tour})
        if not years:
            return None
        candidates = [f"{y}{month}" for y in years[-config.TOUR_BASELINE_YEARS:]]
        values = [tour[m] for m in candidates if m in tour]
        if not values:
            return None
        peak = max(values)
        if peak <= 0:
            return None
        current_month = candidates[-1] if candidates[-1] in tour else max(
            (m for m in tour if m[4:6] == month), default="")
        if not current_month:
            return None
        return max(0.0, min(1.0, tour[current_month] / peak))

    @staticmethod
    def _window(day: str, weeks: int) -> _Window:
        try:
            end = datetime.strptime(day, "%Y%m%d").date()
        except ValueError:
            end = date.today()
        start = end - timedelta(days=weeks * 7)
        days = [(start + timedelta(days=i)).strftime("%Y%m%d")
                for i in range((end - start).days + 1)]
        return _Window(days=days, same_type=[d for d in days if weekday_type(d) == weekday_type(day)])
