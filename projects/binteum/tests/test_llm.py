"""LLM 어댑터·환각 가드 테스트 (실제 호출 없이 가짜 전송 계층 사용)."""
from __future__ import annotations

import json

import pytest

from binteum.llm import (LLMClient, collect_numbers, extract_json, numeric_guard)


class FakePost:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.calls = []

    def post(self, url, payload, headers, timeout):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        return self.status, self.body


def openai_body(text: str) -> str:
    return json.dumps({"choices": [{"message": {"content": text}}]})


def anthropic_body(text: str) -> str:
    return json.dumps({"content": [{"type": "text", "text": text}]})


def test_openai_call_uses_model_and_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    transport = FakePost(200, openai_body("좋은 동선입니다."))
    client = LLMClient(provider="openai", model="gpt-4o-mini", transport=transport)
    result = client.complete("질문")
    assert result.ok and result.text == "좋은 동선입니다."
    assert transport.calls[0]["payload"]["model"] == "gpt-4o-mini"
    assert transport.calls[0]["headers"]["Authorization"].startswith("Bearer ")


def test_anthropic_call(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    transport = FakePost(200, anthropic_body("문장"))
    client = LLMClient(provider="anthropic", model="claude-3-5-haiku-latest",
                       transport=transport)
    assert client.complete("질문").text == "문장"
    assert "x-api-key" in transport.calls[0]["headers"]


def test_missing_key_disables_llm():
    client = LLMClient(provider="openai", model="x")
    # 환경변수가 없으면 available=False → 호출 없이 실패 결과
    assert client.available is False
    result = client.complete("q")
    assert result.ok is False
    assert "LLM 비활성" in result.error


def test_http_error_returns_not_ok(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = LLMClient(provider="openai", transport=FakePost(429, "{}"))
    result = client.complete("q")
    assert result.ok is False


def test_numeric_guard_rejects_invented_numbers():
    allowed = collect_numbers({"ci": 41.5, "travel_min": 78, "stops": 5})
    assert numeric_guard("CI 41.5, 이동 78분", allowed) == []
    bad = numeric_guard("CI 41.5, 이동 12분", allowed)
    assert "12" in bad


def test_llm_output_with_hallucinated_number_is_dropped(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    transport = FakePost(200, openai_body("이곳의 혼잡지수는 97입니다."))
    client = LLMClient(provider="openai", transport=transport)
    result = client.complete("q", allowed_numbers={"41", "41.5"})
    assert result.ok is False
    assert result.rejected_by_guard


def test_json_complete_parses_fenced_block(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    transport = FakePost(200, openai_body('```json\n{"origin_emd":"성산읍"}\n```'))
    client = LLMClient(provider="openai", transport=transport)
    assert client.json_complete("q")["origin_emd"] == "성산읍"


def test_extract_json_handles_noise():
    assert extract_json('설명... {"a": 1} 끝') == {"a": 1}
    assert extract_json("not json") is None


def test_collect_numbers_walks_nested():
    numbers = collect_numbers({"a": [1, 2.5, {"b": "3개"}]})
    assert {"1", "2.5", "3"} <= numbers
    assert "999" not in numbers


def test_local_provider_uses_openai_compatible_endpoint():
    from binteum import llm as llm_mod
    transport = FakePost(200, openai_body("로컬 문장"))
    client = LLMClient(provider="local", model="qwen2.5:3b", transport=transport)
    assert client.available is True           # 키 없이도 사용 가능
    result = client.complete("질문")
    assert result.ok and result.text == "로컬 문장"
    assert transport.calls[0]["url"] == llm_mod.LOCAL_URL
    assert "Authorization" not in transport.calls[0]["headers"]


def test_local_provider_failure_is_contained():
    transport = FakePost(500, "{}")
    client = LLMClient(provider="local", transport=transport)
    result = client.complete("질문")
    assert result.ok is False
