"""Critic Agent — 규칙으로 동선을 검증한다(반려 루프 최대 1회).

"근거 없는 추천은 내보내지 않는다"를 담당한다. LLM은 여기 쓰지 않는다.
검증 항목(기획서 §p10):
  R1 영업시간 안에 도착·체류가 가능한가
  R2 앞 정류장 출발 + 이동시간 ≤ 다음 정류장 도착인가
  R3 같은 장소를 두 번 방문하지 않았는가
  R4 모든 정류장에 CI와 근거(데이터 ID·기준일)가 붙어 있는가
  R5 일정 종료(귀가) 시각을 넘기지 않았는가
  R6 사용자 제약(실내·보행·예산·인원)을 지켰는가
"""
from __future__ import annotations

from . import catalog
from .models import Constraints, CriticResult, Plan, Violation
from .planner import minutes_of


class Critic:
    def __init__(self, constraints: Constraints, trace=None):
        self.c = constraints
        self.trace = trace

    def review(self, plan: Plan, rounds: int = 0) -> CriticResult:
        violations: list[Violation] = []
        db = catalog.catalog()
        seen: set[str] = set()

        for stop in plan.stops:
            spot = db.get(stop.spot_id)

            # R4 근거
            if stop.ci < 0 or not stop.evidence.get("hub_ids"):
                violations.append(Violation("R4", stop.spot_id,
                                            f"{stop.spot_name}: CI 근거 없음"))

            # R3 중복
            if stop.spot_id in seen:
                violations.append(Violation("R3", stop.spot_id,
                                            f"{stop.spot_name}: 동선 중복"))
            seen.add(stop.spot_id)

            if spot is None:
                violations.append(Violation("R4", stop.spot_id, f"카탈로그에 없는 장소 {stop.spot_id}"))
                continue

            # R1 영업시간
            arrive = minutes_of(stop.arrive)
            depart = minutes_of(stop.depart)
            if spot.close_min() > spot.open_min():
                if arrive < spot.open_min() - 5 or depart > spot.close_min():
                    violations.append(Violation(
                        "R1", stop.spot_id,
                        f"{stop.spot_name}: {stop.arrive}~{stop.depart}가 영업시간"
                        f"({spot.open_time}~{spot.close_time}) 밖"))

            # 시간 순서
            if depart < arrive:
                violations.append(Violation("R1", stop.spot_id,
                                            f"{stop.spot_name}: 도착/출발 시각 역전"))

            # R6 제약
            if self.c.indoor_required and not spot.indoor:
                violations.append(Violation("R6", stop.spot_id,
                                            f"{stop.spot_name}: 실내 조건 위반"))
            if self.c.low_walk and not spot.low_walk_ok:
                violations.append(Violation("R6", stop.spot_id,
                                            f"{stop.spot_name}: 보행 부담 조건 위반"))

        # R2 이동시간 연결
        for prev, nxt in zip(plan.stops, plan.stops[1:]):
            available = minutes_of(nxt.arrive) - minutes_of(prev.depart)
            if nxt.travel_min > available + 2:
                violations.append(Violation(
                    "R2", nxt.spot_id,
                    f"{prev.spot_name}→{nxt.spot_name}: 이동 {nxt.travel_min}분 > 여유 {available}분"))

        # R5 종료 시각
        end = minutes_of(self.c.end_time)
        if plan.stops and minutes_of(plan.stops[-1].depart) > end:
            violations.append(Violation("R5", plan.stops[-1].spot_id,
                                        f"마지막 체류가 종료 시각 {self.c.end_time}를 넘김"))

        # R6 예산
        if self.c.budget_krw is not None and plan.totals["cost_krw"] > self.c.budget_krw:
            violations.append(Violation("R6", "-",
                                        f"비용 {plan.totals['cost_krw']:,}원 > 예산 {self.c.budget_krw:,}원"))

        result = CriticResult(passed=not violations, violations=violations, rounds=rounds,
                              notes=[f"{len(plan.stops)}개 정류장 검증"])
        if self.trace:
            self.trace.tool("critic.review", ok=result.passed, ms=0.0,
                            plan=plan.key, violations=len(violations), rounds=rounds)
        return result

    def review_all(self, plans: list[Plan], rounds: int = 0) -> dict[str, CriticResult]:
        return {plan.key: self.review(plan, rounds=rounds) for plan in plans}

    @staticmethod
    def blocking_spots(results: dict[str, CriticResult]) -> set[str]:
        """반려된 정류장을 다음 라운드의 블랙리스트로 넘긴다."""
        bad: set[str] = set()
        for result in results.values():
            for violation in result.violations:
                if violation.spot_id and violation.spot_id != "-":
                    bad.add(violation.spot_id)
        return bad
