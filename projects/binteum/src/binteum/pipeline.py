"""오케스트레이터 — 4역할(6단계) 에이전트 파이프라인.

    Router → Data → Index(코드) → Planner → Critic → Reporter

계약:
* 어떤 단계가 실패해도 예외로 끝나지 않는다. 결과 JSON의 `ok`/`notes`로 알린다.
* Critic이 반려하면 블랙리스트를 걸고 **1회만** 재계획한다(무한 루프 방지).
* 모든 실행은 out/runs/{run_id}.json 과 out/reports/{run_id}.html 로 남는다.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import config, reporter
from .catalog import catalog as spot_db
from .critic import Critic
from .data import DataPortal
from .index import CrowdIndexer, hour_estimate
from .llm import LLMClient
from .models import Constraints
from .planner import PlanContext, Planner
from .router import Router
from .trace import Trace

AUTONOMY = {
    "자율 수행": ["허브 데이터 조회", "혼잡지수 계산", "후보 동선 생성", "근거 문장 생성"],
    "사람 확인 필요": ["외부 전송(카톡·메일)", "예약·결제", "일정 확정"],
    "금지": ["위치 이력 서버 저장", "개인정보 수집", "예약 대행"],
}


class BinTeumPipeline:
    def __init__(self, *, offline: bool = False, llm: LLMClient | None = None,
                 portal: DataPortal | None = None, trace: Trace | None = None,
                 save: bool = True):
        config.ensure_dirs()
        self.trace = trace or Trace()
        self.llm = llm if llm is not None else LLMClient(trace=self.trace)
        self.offline = offline
        self.portal = portal or DataPortal(offline=offline, trace=self.trace)
        self.save = save

    # ---------------------------------------------------------------- 실행
    def run(self, query: str = "", **inputs) -> dict:
        started = time.time()
        self.trace.log("pipeline_start", {"query": query, "inputs": inputs,
                                         "offline": self.offline,
                                         "llm": self.llm.provider})

        # ① Router
        t0 = time.time()
        router = Router(llm=self.llm, trace=self.trace)
        constraints = router.parse(query, **inputs)
        self.trace.tool("router", ok=True, ms=(time.time() - t0) * 1000,
                        emd=constraints.origin_emd, asked=constraints.asked)
        if constraints.asked and not constraints.origin_emd:
            payload = self._needs_input(constraints, started)
            return self._finish(payload)

        # ② Data
        t0 = time.time()
        provenance = self.portal.load(today=constraints.now.date())
        self.trace.tool("data", ok=provenance.mode != "empty",
                        ms=(time.time() - t0) * 1000, mode=provenance.mode)
        if provenance.mode == "empty":
            payload = self._empty_data(constraints, provenance, started)
            return self._finish(payload)

        # ③ Index (순수 파이썬)
        t0 = time.time()
        indexer = CrowdIndexer(self.portal, trace=self.trace)
        scores = indexer.score_all(self.portal.reference_date)
        self.trace.tool("index", ok=bool(scores), ms=(time.time() - t0) * 1000,
                        scored=len(scores),
                        avg_ci=round(sum(s.ci for s in scores.values()) / max(1, len(scores)), 1))

        weather = self._weather_for(constraints)
        ctx = PlanContext(constraints=constraints, ci=scores,
                          day=self.portal.reference_date, weather=weather)

        # ④ Planner + ⑤ Critic (반려 시 1회 재계획)
        rounds = 0
        planner = Planner(ctx, trace=self.trace)
        plans = planner.build()
        critic = Critic(constraints, trace=self.trace)
        reviews = critic.review_all(plans, rounds=0)
        history = [self._critic_round(0, reviews)]
        rejected = {k: v for k, v in reviews.items() if not v.passed}
        if rejected and rounds < config.MAX_CRITIC_REJECTIONS:
            rounds += 1
            blocking = Critic.blocking_spots(rejected)
            self.trace.log("critic_reject", {"plans": list(rejected), "blocking": sorted(blocking)})
            planner = Planner(ctx, trace=self.trace, blacklist=blocking)
            plans = planner.build()
            reviews = critic.review_all(plans, rounds=rounds)
            self.trace.log("critic_replan", {"blocking": sorted(blocking), "round": rounds})
        history.append(self._critic_round(rounds, reviews))

        # ⑥ Reporter
        t0 = time.time()
        payload = self._payload(constraints, provenance, plans, reviews, rounds,
                                scores, weather, started, indexer, history)
        payload = reporter.enrich(payload, self.llm, trace=self.trace)
        self.trace.tool("reporter", ok=True, ms=(time.time() - t0) * 1000,
                        plan_a=payload["summary"]["best_plan"])
        return self._finish(payload)

    # ---------------------------------------------------------------- 조립
    def _payload(self, constraints: Constraints, provenance, plans, reviews, rounds,
                 scores, weather, started: float, indexer: CrowdIndexer,
                 history: list[dict] | None = None) -> dict:
        now = constraints.now
        comparisons = []
        for plan in plans:
            if not plan.stops:
                continue
            first = plan.stops[0]
            category = spot_db().get(first.spot_id).category if first.spot_id in spot_db() else "자연"
            comparisons.append({
                "plan": plan.key,
                "spot": first.spot_name,
                "ci_now": hour_estimate(first.ci, category, now.hour),
                "ci_next_hour": hour_estimate(first.ci, category, now.hour + 1),
                "basis": "일 단위 실측 CI × 시간대 가정 곡선(추정)",
            })

        best = self._best_plan(plans, reviews)
        summary = {
            "best_plan": best.key if best else "",
            "best_label": best.label if best else "",
            "headline": best.headline if best else "",
            "avg_ci": best.totals["avg_ci"] if best else None,
            "stops": best.totals["stops"] if best else 0,
            "travel_min": best.totals["travel_min"] if best else 0,
            "comparisons": comparisons,
            "critic_rounds": rounds,
            "critic_passed": all(r.passed for r in reviews.values()),
            "critic_history": history or [],
            "rejections": {k: [v.message for v in r.violations] for k, r in reviews.items() if not r.passed},
        }
        notes = [
            "혼잡지수는 '예측'이 아니라 실측·계절 보정 기반 상대 순위입니다.",
            "관광지 내부 인원은 공개 데이터가 없어 직접 관측하지 않습니다(591은 월 단위).",
            "공휴일은 평일로 계산합니다.",
            "'지금 vs 1시간 뒤'는 시간대 가정 곡선을 곱한 추정값입니다.",
        ]
        if provenance.mode in ("snapshot", "mixed"):
            notes.insert(0, provenance.note)
        return {
            "ok": True,
            "run_id": self.trace.run_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_ms": int((time.time() - started) * 1000),
            "app": {"name": config.APP_NAME, "version": config.VERSION,
                    "tagline": config.APP_TAGLINE},
            "constraints": constraints.to_dict(),
            "data": provenance.to_dict(),
            "weather": weather,
            "plans": [p.to_dict() for p in plans],
            "critic": {k: v.to_dict() for k, v in reviews.items()},
            "summary": summary,
            "notes": notes,
            "autonomy": AUTONOMY,
            "llm": {"provider": self.llm.provider, "available": self.llm.available},
            "trace_path": str(self.trace.path),
        }

    @staticmethod
    def _critic_round(round_no: int, reviews) -> dict:
        return {
            "round": round_no,
            "passed": sum(1 for r in reviews.values() if r.passed),
            "total": len(reviews),
            "violations": [v.message for r in reviews.values() for v in r.violations],
        }

    @staticmethod
    def _best_plan(plans, reviews):
        candidates = [p for p in plans if p.stops and reviews.get(p.key) and reviews[p.key].passed]
        if not candidates:
            candidates = [p for p in plans if p.stops]
        if not candidates:
            return None
        values = [p.totals["avg_ci"] for p in candidates if p.totals["avg_ci"] is not None]
        floor = min(values) if values else 0
        # 혼잡도가 비슷하면(8점 이내) 하루를 더 알차게 쓰는 안을 고른다.
        near_best = [p for p in candidates
                     if p.totals["avg_ci"] is not None and p.totals["avg_ci"] <= floor + 8]
        pool = near_best or candidates
        return max(pool, key=lambda p: (p.totals["stops"], -p.totals["avg_ci"]))

    def _weather_for(self, constraints: Constraints) -> dict | None:
        spot = spot_db().get(constraints.origin_spot) if constraints.origin_spot else None
        lat, lon = (spot.lat, spot.lon) if spot else (33.4996, 126.5312)
        weather = self.portal.weather_for(lat, lon, self.portal.reference_date)
        return weather.to_dict() if weather else None

    # ---------------------------------------------------------------- 예외 경로
    def _needs_input(self, constraints: Constraints, started: float) -> dict:
        self.trace.log("needs_input", {"asked": constraints.asked})
        return {
            "ok": False, "status": "needs_input", "run_id": self.trace.run_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_ms": int((time.time() - started) * 1000),
            "constraints": constraints.to_dict(),
            "asked": constraints.asked,
            "message": " ".join(constraints.asked),
            "plans": [], "summary": {"best_plan": ""}, "notes": [],
        }

    def _empty_data(self, constraints: Constraints, provenance, started: float) -> dict:
        return {
            "ok": False, "status": "no_data", "run_id": self.trace.run_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_ms": int((time.time() - started) * 1000),
            "constraints": constraints.to_dict(), "data": provenance.to_dict(),
            "plans": [], "summary": {"best_plan": ""},
            "notes": ["모든 데이터셋이 결측입니다. data/snapshot/ 에 스냅샷을 넣거나 "
                      "JEJU_DATA_HUB_KEY 를 설정하세요."],
        }

    def _finish(self, payload: dict) -> dict:
        if self.save:
            paths = save_outputs(payload)
            payload["outputs"] = paths
        self.trace.close("ok" if payload.get("ok") else payload.get("status", "error"))
        return payload

    def close(self) -> None:
        try:
            self.trace.close("ok")
        except Exception:
            pass


def save_outputs(payload: dict) -> dict:
    config.ensure_dirs()
    run_id = payload.get("run_id") or "run"
    runs = config.OUT_DIR / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    json_path = runs / f"{run_id}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        reports = reporter.write_report_files(payload)
    except Exception as exc:  # noqa: BLE001 - 리포트 실패가 파이프라인을 죽이지 않게
        print(f"[warn] 리포트 생성 실패: {exc}")
        reports = {"html": "", "md": ""}
    return {"json": str(json_path),
            "html": reports.get("html", ""),
            "md": reports.get("md", ""),
            "trace": payload.get("trace_path", "")}
