"""Planner Agent — 제약 하에서 '남은 하루' 동선을 3안으로 재구성한다.

그리디 + 이동시간 행렬. LLM을 쓰지 않는다(수치·순서는 코드가 정한다).
각 정류장에는 CI·근거 데이터ID·이동수단·소요가 붙는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from . import catalog, config, travel
from .catalog import catalog as spot_db
from .models import Constraints, CrowdScore, Plan, Spot, Stop

VARIANT_WEIGHTS = {
    "quiet": {"ci": 0.58, "travel": 0.24, "theme": 0.18},
    "short": {"ci": 0.26, "travel": 0.58, "theme": 0.16},
    "theme": {"ci": 0.30, "travel": 0.24, "theme": 0.46},
}
# 안별 1회 이동 상한(분). '이동 최소'는 같은 권역 클러스터 안에서만 고른다.
VARIANT_MAX_TRAVEL = {"quiet": 999.0, "short": 35.0, "theme": 45.0}
MEAL_CATEGORIES = ("시장", "미식", "항구")
MEAL_THEMES = ("미식", "시장")


def hhmm(minutes: int) -> str:
    minutes = int(round(minutes))
    hour, minute = divmod(max(0, minutes), 60)
    return f"{hour % 24:02d}:{minute:02d}"


def minutes_of(text: str) -> int:
    hour, _, minute = str(text).partition(":")
    return int(hour) * 60 + int(minute or 0)


@dataclass
class PlanContext:
    constraints: Constraints
    ci: dict[str, CrowdScore]
    day: str
    weather: dict | None = None


class Planner:
    def __init__(self, ctx: PlanContext, trace=None, blacklist: set[str] | None = None,
                 relax: bool = False):
        self.ctx = ctx
        self.c = ctx.constraints
        self.ci = ctx.ci
        self.trace = trace
        self.blacklist = set(blacklist or set())
        self.relax = relax
        self.origin = self._origin_point()
        self.max_travel = travel.reachable_minutes(self.c.mobility) * (1.7 if relax else 1.0)
        if self.c.low_walk and not relax:
            self.max_travel = min(self.max_travel, 32.0)   # 보행 부담 → 한 구간 32분 이내
        self.used: set[str] = set()
        self._limit = self.max_travel
        self.max_stops = 5 if (self.c.low_walk or self.c.party == "family_kid") else 6

    # ---------------------------------------------------------------- 공개
    def build(self) -> list[Plan]:
        plans = []
        for key in config.PLAN_VARIANTS:
            self.used = set()
            plan = self._build_one(key)
            plans.append(plan)
        return plans

    # ---------------------------------------------------------------- 내부
    def _origin_point(self) -> tuple[float, float]:
        if self.c.origin_spot and self.c.origin_spot in spot_db():
            spot = spot_db()[self.c.origin_spot]
            return (spot.lat, spot.lon)
        peers = catalog.spots_in_emd(self.c.origin_emd)
        if peers:
            return (sum(s.lat for s in peers) / len(peers), sum(s.lon for s in peers) / len(peers))
        return (33.4996, 126.5312)      # 제주시청 인근(위치 미상 시)

    def _build_one(self, key: str) -> Plan:
        weights = VARIANT_WEIGHTS[key]
        self._limit = min(self.max_travel, VARIANT_MAX_TRAVEL.get(key, self.max_travel))
        if self.relax:
            self._limit = self.max_travel
        start = self._start_minutes()
        end = minutes_of(self.c.end_time)
        if end <= start:
            end = min(23 * 60, start + 240)

        position = self.origin
        cursor = start
        stops: list[Stop] = []
        total_cost = 0
        travel_sum = 0.0
        distance_sum = 0.0
        warnings: list[str] = []
        meal_done = False

        for _ in range(self.max_stops):
            if cursor >= end - config.DEFAULT_RETURN_BUFFER_MIN:
                break
            best = self._best_next(position, cursor, key, weights, total_cost,
                                   meal_done, end)
            if best is None and key in ("short", "theme") and self._limit < self.max_travel:
                # '이동 최소'·'취향'도 하루가 비지 않도록 상한을 한 단계만 넓혀 재시도한다.
                self._limit = min(self.max_travel, self._limit * 1.6)
                best = self._best_next(position, cursor, key, weights, total_cost,
                                       meal_done, end)
            if best is None:
                break
            spot, arrive, travel_min, km, mode = best
            dwell = self._dwell(spot)
            depart = arrive + dwell
            if depart > end:
                depart = end
                dwell = max(20, end - arrive)
            score = self.ci.get(spot.id)
            ci_value = int(round(score.ci)) if score else -1
            stops.append(Stop(
                order=len(stops) + 1, spot_id=spot.id, spot_name=spot.name, emd=spot.emd,
                category=spot.category, indoor=spot.indoor,
                arrive=hhmm(arrive), depart=hhmm(depart), dwell_min=int(dwell),
                travel_min=int(round(travel_min)), travel_km=round(km, 1),
                ci=ci_value, ci_label=(score.label if score else "근거 없음"),
                cost_krw=spot.cost_krw,
                why=self._why(spot, score, mode, travel_min, km),
                evidence={
                    "hub_ids": {"flow": config.DATASET_IDS["flow"],
                                "tour": config.DATASET_IDS["tour"],
                                "bus": config.DATASET_IDS["bus"],
                                "weather": config.DATASET_IDS["weather"]},
                    "base_date": self.ctx.day,
                    "dropped_terms": score.dropped if score else [],
                    "terms": score.terms if score else {},
                    "confidence": score.confidence if score else "none",
                    "travel_mode": mode,
                },
            ))
            self.used.add(spot.id)
            total_cost += spot.cost_krw
            travel_sum += travel_min
            distance_sum += km
            cursor = depart
            position = (spot.lat, spot.lon)
            if spot.category in MEAL_CATEGORIES or set(spot.themes) & set(MEAL_THEMES):
                meal_done = True

        if not stops:
            warnings.append("조건을 만족하는 후보가 없어 동선을 만들지 못했습니다. 종료 시각·이동수단을 완화해 보세요.")
        if len(stops) < 2:
            warnings.append("방문지가 1곳뿐입니다. 종료 시각을 늦추거나 이동수단을 차량으로 두면 선택지가 늘어납니다.")
        if any((s.evidence.get("dropped_terms") or []) for s in stops):
            dropped = sorted({t for s in stops for t in s.evidence.get("dropped_terms", [])})
            warnings.append(f"데이터 결측으로 제외된 지수 항: {', '.join(dropped)} → 남은 항으로 가중치 재정규화")

        stop_ci = [s.ci for s in stops if s.ci >= 0]
        totals = {
            "stops": len(stops),
            "travel_min": int(round(travel_sum)),
            "distance_km": round(distance_sum, 1),
            "cost_krw": total_cost,
            "avg_ci": round(sum(stop_ci) / len(stop_ci), 1) if stop_ci else None,
            "attraction_min": int(sum(s.dwell_min for s in stops)),
            "span": f"{stops[0].arrive if stops else hhmm(start)}~{stops[-1].depart if stops else hhmm(end)}",
        }
        return Plan(
            key=key,
            label=config.PLAN_VARIANT_LABEL[key],
            headline=self._headline(key, totals),
            stops=stops,
            totals=totals,
            rationale=self._rationale(key, totals),
            warnings=warnings,
        )

    def _start_minutes(self) -> int:
        if getattr(self.c, "tomorrow", False):
            return config.DEFAULT_START_HOUR * 60
        now = self.c.now
        base = now.hour * 60 + now.minute + 20       # 준비·출발 여유 20분
        return max(base, config.DEFAULT_START_HOUR * 60)

    def _best_next(self, position, cursor, key, weights, total_cost, meal_done, end):
        best = None
        meal_window = (self.c.meal_needed and not meal_done
                       and 11 * 60 + 30 <= cursor <= 14 * 60)
        candidates = []
        for spot in catalog.spots():
            if spot.id in self.used or spot.id in self.blacklist:
                continue
            if not self._passes_filters(spot, total_cost, end):
                continue
            travel_min, km = travel.leg_cached(position, (spot.lat, spot.lon), self.c.mobility)
            if travel_min > self._limit:
                continue
            arrive = cursor + travel_min
            if not self._open_at(spot, arrive, self._dwell(spot)):
                continue
            score = self.ci.get(spot.id)
            if score is None:            # 근거 없는 추천 금지
                continue
            dwell = self._dwell(spot)
            depart = min(end, arrive + dwell)
            return_min, _ = travel.leg_cached((spot.lat, spot.lon), self.origin, self.c.mobility)
            if depart + return_min > end:      # 종료 시각까지 숙소(출발지) 복귀
                continue
            candidates.append((spot, arrive, travel_min, km, score))

        if meal_window:
            meals = [c for c in candidates if c[0].category in MEAL_CATEGORIES
                     or set(c[0].themes) & set(MEAL_THEMES)]
            if meals:
                candidates = meals

        for spot, arrive, travel_min, km, score in candidates:
            value = self._score(spot, score, travel_min, arrive, key, weights, meal_done)
            if best is None or value > best[0]:
                best = (value, spot, arrive, travel_min, km, self.c.mobility)
        if best is None:
            return None
        _, spot, arrive, travel_min, km, mode = best
        return spot, arrive, travel_min, km, mode

    def _passes_filters(self, spot: Spot, total_cost: int, end: int) -> bool:
        c = self.c
        if c.indoor_required and not spot.indoor and not self.relax:
            return False
        if c.low_walk and not spot.low_walk_ok:
            return False
        if c.party == "family_kid" and c.mobility == "walk" and not spot.stroller_ok:
            return False
        if c.budget_krw is not None and total_cost + spot.cost_krw > c.budget_krw:
            return False
        if self._dwell(spot) > max(30, end - 60):
            return False
        return True

    @staticmethod
    def _open_at(spot: Spot, arrive: float, dwell: int | None = None) -> bool:
        dwell = spot.dwell_min if dwell is None else dwell
        open_min = spot.open_min()
        close_min = spot.close_min()
        if close_min <= open_min:      # 24시간
            return True
        if arrive < open_min - 5:
            return False
        return arrive + dwell <= close_min

    def _dwell(self, spot: Spot) -> int:
        return spot.dwell_min

    def _score(self, spot: Spot, score: CrowdScore, travel_min, arrive, key, weights,
               meal_done) -> float:
        quiet = 1.0 - max(0.0, min(100.0, score.ci)) / 100.0
        near = 1.0 - min(1.0, travel_min / max(1.0, self._limit))
        if key == "short":
            near = near ** 2          # 가까운 곳에 더 강하게 몰리게
        theme = 0.0
        if self.c.themes:
            theme = 1.0 if set(self.c.themes) & set(spot.themes) else 0.0
            if spot.category in self.c.themes:
                theme = max(theme, 0.7)
        value = (weights["ci"] * quiet + weights["travel"] * near + weights["theme"] * theme)

        if self.c.meal_needed and not meal_done and (spot.category in MEAL_CATEGORIES):
            if 11 * 60 + 30 <= arrive <= 13 * 60 + 30:
                value += 0.18
        if self.c.party == "family_kid" and spot.stroller_ok:
            value += 0.05
        if self.c.indoor_required and spot.indoor:
            value += 0.08
        if key == "theme":
            # 테마 미지정 시에는 '카테고리 다양성'을 취향 대신 사용한다(같은 유형 반복 감점).
            used_categories = {catalog.catalog()[sid].category
                               for sid in self.used if sid in catalog.catalog()}
            if spot.category in used_categories:
                value -= 0.07
        if meal_done and spot.category in MEAL_CATEGORIES:
            value -= 0.06
        if self.ctx.weather and self.ctx.weather.get("bad_weather"):
            value += 0.04 if spot.indoor else -0.04
        if key == "theme" and score.confidence != "ok":
            value -= 0.05
        return value

    def _why(self, spot: Spot, score: CrowdScore | None, mode: str, travel_min: float,
             km: float) -> list[str]:
        lines: list[str] = []
        if score:
            p = score.terms.get("visit")
            visit_ev = score.evidence.get("visit", {})
            if p is not None:
                lines.append(
                    f"{spot.emd} 방문인구 백분위 {int(round(p * 100))}% "
                    f"(허브 583 · {visit_ev.get('base_date', '')} 기준 · "
                    f"동일 요일유형 {visit_ev.get('sample_days', 0)}일 표본)")
            t = score.terms.get("tour")
            if t is not None:
                tour_ev = score.evidence.get("tour", {})
                lines.append(
                    f"계절 기준선 {int(round(t * 100))}% — 최근 3년 동월 최대 대비 "
                    f"(허브 591 · 최신월 {tour_ev.get('latest_month', '')})")
            if "bus" in score.dropped:
                lines.append("버스 데이터 없음 → 이 후보에서는 P_bus 항 제외(가중치 재정규화)")
            else:
                b = score.terms.get("bus")
                bus_ev = score.evidence.get("bus", {})
                lines.append(
                    f"노선 수요 백분위 {int(round((b or 0) * 100))}% "
                    f"(허브 614 · 노선 {', '.join(spot.near_routes) or '없음'} · "
                    f"{bus_ev.get('sample_days', 0)}일 표본)")
            w = score.evidence.get("weather", {})
            if w and not w.get("missing"):
                lines.append(
                    f"날씨 {w.get('rain_mm', 0)}mm·최대풍속 {w.get('wind_max_ms', 0)}m/s "
                    f"→ {'실내 가산' if spot.indoor else '야외 감산'} (허브 579 · {w.get('observatory', '')})")
        lines.append(f"이동 {int(round(travel_min))}분 / {km:.1f}km ({_mode_ko(mode)}) · 체류 {spot.dwell_min}분")
        return lines

    def _headline(self, key: str, totals: dict) -> str:
        label = {"quiet": "가장 한산한 순서로", "short": "이동을 줄이고",
                 "theme": "취향에 맞춰"}[key]
        return (f"{label} {totals['stops']}곳 · 평균 CI "
                f"{totals['avg_ci'] if totals['avg_ci'] is not None else '-'} · "
                f"이동 {totals['travel_min']}분")

    def _rationale(self, key: str, totals: dict) -> str:
        base = {
            "quiet": "혼잡지수가 낮은 후보를 우선하고, 이동 부담은 최소한으로만 고려했습니다.",
            "short": "이동시간을 가장 크게 줄이는 조합입니다. 하루에 여러 곳을 무리 없이 도는 데 적합합니다.",
            "theme": "선호 테마와 실내 조건을 가장 크게 반영한 조합입니다.",
        }[key]
        extra = []
        if self.c.indoor_required:
            extra.append("실내 조건을 만족하는 곳만 배치했습니다")
        if self.c.low_walk:
            extra.append("걷기 부담이 적은 곳만 골랐습니다")
        if self.c.budget_krw is not None:
            extra.append(f"예산 {self.c.budget_krw:,}원 이내")
        return base + (" " + ", ".join(extra) + "." if extra else "")


def _mode_ko(mode: str) -> str:
    return {"car": "렌터카", "bus": "버스", "walk": "도보"}.get(mode, mode)
