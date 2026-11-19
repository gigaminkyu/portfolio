"""파이프라인 통합 테스트 — 6단계가 끝까지 돌고, 폴백·반려 루프·출력물이 남는지."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from binteum import config, reporter
from binteum.llm import LLMClient
from binteum.pipeline import BinTeumPipeline
from binteum.trace import Trace

NOW = datetime(2026, 11, 16, 10, 0)


def build(tmp_out, **kwargs):
    trace = Trace(path=tmp_out / "traces" / "t.jsonl")
    return BinTeumPipeline(offline=True, trace=trace, llm=LLMClient(provider="none",
                                                                   trace=trace), **kwargs)


def test_pipeline_end_to_end(tmp_out):
    pipeline = build(tmp_out)
    payload = pipeline.run("성산인데 애 데리고 6시까지 실내 위주로", emd="성산읍", now=NOW)
    assert payload["ok"] is True
    assert payload["data"]["mode"] in ("mixed", "snapshot", "collected")
    assert len(payload["plans"]) == 3
    assert payload["summary"]["best_plan"] in {"quiet", "short", "theme"}
    assert payload["critic"]["quiet"]["passed"] is True
    assert payload["notes"], "한계 문구가 붙어야 한다"
    assert payload["autonomy"]["금지"], "자율 범위 경계가 결과에 포함되어야 한다"
    assert payload["outputs"]["json"] and Path(payload["outputs"]["json"]).exists()
    assert payload["outputs"]["html"] and Path(payload["outputs"]["html"]).exists()
    assert Path(payload["trace_path"]).exists()


def test_trace_records_tool_calls(tmp_out):
    pipeline = build(tmp_out)
    payload = pipeline.run("", emd="중문동", now=NOW)
    lines = Path(payload["trace_path"]).read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line)["event"] for line in lines]
    assert "pipeline_start" in events
    assert "tool_call" in events
    assert "run_end" in events


def test_needs_input_when_location_missing(tmp_out):
    pipeline = build(tmp_out)
    payload = pipeline.run("지금 붐비는데 어디 가지", now=NOW)
    assert payload["ok"] is False
    assert payload["status"] == "needs_input"
    assert payload["asked"]


def test_no_data_path_returns_graceful_payload(tmp_out, tmp_path):
    from binteum.data import DataPortal
    empty = tmp_path / "empty_snapshot"
    empty.mkdir()
    portal = DataPortal(offline=True, snapshot_dir=empty, live_dir=tmp_path / "none")
    pipeline = build(tmp_out, portal=portal)
    payload = pipeline.run("", emd="성산읍", now=NOW)
    assert payload["ok"] is False
    assert payload["status"] == "no_data"
    assert payload["notes"]


def test_critic_rejection_triggers_one_replan(tmp_out, monkeypatch):
    """1차 검증을 일부러 반려시켜, 반려 → 재계획 1회가 실제로 돌고 기록되는지 본다."""
    from binteum.critic import Critic
    from binteum.models import Violation

    state = {"n": 0}
    original = Critic.review_all

    def patched(self, plans, rounds=0):
        results = original(self, plans, rounds=rounds)
        if state["n"] == 0:
            state["n"] += 1
            first = results[next(iter(results))]
            first.passed = False
            first.violations.append(
                Violation("R1", plans[0].stops[0].spot_id, "테스트용 인위적 반려"))
        return results

    monkeypatch.setattr(Critic, "review_all", patched)
    pipeline = build(tmp_out)
    payload = pipeline.run("", emd="구좌읍", end_time="18:00", now=NOW)
    history = payload["summary"]["critic_history"]
    assert payload["summary"]["critic_rounds"] == 1, "반려는 최대 1회까지만"
    assert len(history) == 2
    assert any("테스트용" in message for message in history[0]["violations"])
    assert history[-1]["passed"] == history[-1]["total"]


def test_llm_failure_falls_back_to_template(tmp_out):
    class BrokenLLM(LLMClient):
        def __init__(self):
            super().__init__(provider="openai")
            self.provider = "openai"

        @property
        def available(self):
            return True

        def complete(self, *a, **k):
            from binteum.llm import LLMResult
            return LLMResult(text="", ok=False, provider="openai", error="quota")

    trace = Trace(path=tmp_out / "traces" / "t2.jsonl")
    pipeline = BinTeumPipeline(offline=True, trace=trace, llm=BrokenLLM())
    payload = pipeline.run("", emd="성산읍", now=NOW)
    assert payload["ok"] is True
    assert payload["summary"]["narrative"]
    assert payload["summary"].get("narrative_source") == "template"


def test_share_text_is_kakao_ready(tmp_out):
    pipeline = build(tmp_out)
    payload = pipeline.run("", emd="성산읍", now=NOW)
    text = payload["share_text"]
    assert text.startswith("[빈틈]")
    assert "CI" in text


def test_reports_are_written_and_self_contained(tmp_out):
    pipeline = build(tmp_out)
    payload = pipeline.run("", emd="성산읍", now=NOW)
    html = Path(payload["outputs"]["html"]).read_text(encoding="utf-8")
    assert "__BINTEUM_PRESET__" in html
    assert "<style>" in html and "style.css" not in html
    assert payload["run_id"] in html
    md = Path(payload["outputs"]["md"]).read_text(encoding="utf-8")
    assert "빈틈(BinTeum) 실행 결과" in md


def test_repeat_runs_are_stable(tmp_out):
    a = build(tmp_out).run("", emd="한림읍", end_time="18:00", now=NOW)
    b = build(tmp_out).run("", emd="한림읍", end_time="18:00", now=NOW)
    ids_a = [s["spot_id"] for s in a["plans"][0]["stops"]]
    ids_b = [s["spot_id"] for s in b["plans"][0]["stops"]]
    assert ids_a == ids_b, "같은 입력·같은 데이터면 같은 결과여야 한다(재현성)"
