"""LLM 어댑터 (선택) + 환각 가드.

빈틈의 수치는 절대 LLM이 만들지 않는다. LLM은 Router의 문장 해석 보조와
Reporter의 "왜 여기인가" 문장 생성에만 쓰이고, 세 가지 안전장치를 통과해야 한다.

  1) 프롬프트 3원칙: 수치는 제공된 JSON만 인용 / 없는 데이터는 '없음' / JSON 스키마 강제
  2) 숫자 정규식 대조(numeric_guard): 응답 속 모든 숫자가 Tool 출력에 존재해야 한다
  3) 어떤 단계에서든 실패하면 결정론적 템플릿으로 폴백 (빈 화면·에러 없음)

평가자 환경에 LLM 키가 없어도 전체 파이프라인이 끝까지 돈다(BINTEUM_LLM_PROVIDER=none).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import config

OPENAI_URL = os.environ.get("BINTEUM_OPENAI_URL", "https://api.openai.com/v1/chat/completions")
ANTHROPIC_URL = os.environ.get("BINTEUM_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
# 로컬 추론 서버(OpenAI 호환): Ollama·vLLM·LM Studio 등. 센터 내부망·오프라인 시연용.
LOCAL_URL = os.environ.get("BINTEUM_LOCAL_URL", "http://127.0.0.1:11434/v1/chat/completions")

SYSTEM_PROMPT = """당신은 제주 여행 동선 도우미 '빈틈'의 서술 담당입니다.
규칙:
1. 제공된 JSON에 있는 수치만 인용합니다. 새 숫자를 계산하거나 추정하지 않습니다.
2. 데이터가 없으면 '없음'이라고 씁니다. 없는 사실을 만들지 않습니다.
3. 출력은 요청된 JSON 스키마만. 설명·인사말·면책 문구를 덧붙이지 않습니다.
4. 각 장소가 왜 지금 한산한지, 어떤 근거 데이터로 판단했는지를 2~3문장으로 씁니다."""

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


class Transport:
    def post(self, url: str, payload: dict, headers: dict, timeout: float) -> tuple[int, str]:
        data = json.dumps(payload).encode()
        request = urllib.request.Request(url, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")[:300]
        except Exception as exc:  # noqa: BLE001
            return 0, f"{type(exc).__name__}: {exc}"


@dataclass
class LLMResult:
    text: str
    ok: bool
    provider: str
    error: str = ""
    rejected_by_guard: list[str] | None = None


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None,
                 transport: Transport | None = None, trace=None):
        settings = config.llm_settings()
        self.provider = (provider or settings["provider"] or "none").lower()
        self.model = model or settings["model"]
        self.transport = transport or Transport()
        self.trace = trace

    @property
    def available(self) -> bool:
        if self.provider in ("none", "", "template", "off"):
            return False
        if self.provider == "openai":
            return bool(os.environ.get("OPENAI_API_KEY"))
        if self.provider == "anthropic":
            return bool(os.environ.get("ANTHROPIC_API_KEY"))
        if self.provider == "local":
            return True          # 로컬 서버는 키가 없다. 실패하면 템플릿으로 폴백된다.
        return False

    # ---------------------------------------------------------------- 호출
    def complete(self, prompt: str, system: str = SYSTEM_PROMPT,
                 allowed_numbers: set[str] | None = None,
                 max_tokens: int | None = None) -> LLMResult:
        if not self.available:
            return LLMResult(text="", ok=False, provider=self.provider,
                             error="LLM 비활성(템플릿 모드)")
        try:
            if self.provider == "openai":
                status, body = self.transport.post(
                    OPENAI_URL,
                    {"model": self.model, "temperature": 0.2,
                     "max_tokens": max_tokens or config.LLM_MAX_OUTPUT_TOKENS,
                     "messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": prompt}]},
                    {"Content-Type": "application/json",
                     "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
                    config.LLM_TIMEOUT_S)
                text = _openai_text(status, body)
            elif self.provider == "anthropic":
                status, body = self.transport.post(
                    ANTHROPIC_URL,
                    {"model": self.model, "max_tokens": max_tokens or config.LLM_MAX_OUTPUT_TOKENS,
                     "system": system, "messages": [{"role": "user", "content": prompt}]},
                    {"Content-Type": "application/json",
                     "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                     "anthropic-version": "2023-06-01"},
                    config.LLM_TIMEOUT_S)
                text = _anthropic_text(status, body)
            elif self.provider == "local":
                status, body = self.transport.post(
                    LOCAL_URL,
                    {"model": self.model, "temperature": 0.2,
                     "max_tokens": max_tokens or config.LLM_MAX_OUTPUT_TOKENS,
                     "messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": prompt}]},
                    {"Content-Type": "application/json"},
                    config.LLM_TIMEOUT_S)
                text = _openai_text(status, body)
            else:
                return LLMResult(text="", ok=False, provider=self.provider, error="미지원 provider")
        except Exception as exc:  # noqa: BLE001
            self._trace(False, str(exc))
            return LLMResult(text="", ok=False, provider=self.provider, error=str(exc))

        if not text:
            self._trace(False, "빈 응답")
            return LLMResult(text="", ok=False, provider=self.provider, error="빈 응답")

        if allowed_numbers is not None:
            invalid = numeric_guard(text, allowed_numbers)
            if invalid:
                self._trace(False, f"환각 가드 거부: {invalid[:5]}")
                return LLMResult(text="", ok=False, provider=self.provider,
                                 error="환각 가드: 근거 없는 숫자", rejected_by_guard=invalid)
        self._trace(True, "")
        return LLMResult(text=text.strip(), ok=True, provider=self.provider)

    def json_complete(self, prompt: str, allowed_numbers: set[str] | None = None) -> dict | None:
        result = self.complete(prompt, allowed_numbers=allowed_numbers)
        if not result.ok:
            return None
        return extract_json(result.text)

    def _trace(self, ok: bool, error: str) -> None:
        if self.trace:
            self.trace.tool(f"llm[{self.provider}]", ok=ok, ms=0.0, model=self.model,
                            error=error)


# ------------------------------------------------------------------ 유틸
def _openai_text(status: int, body: str) -> str:
    if status != 200:
        return ""
    try:
        payload = json.loads(body)
        return payload["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


def _anthropic_text(status: int, body: str) -> str:
    if status != 200:
        return ""
    try:
        payload = json.loads(body)
        return "".join(block.get("text", "") for block in payload.get("content", []))
    except Exception:
        return ""


def extract_json(text: str) -> dict | None:
    """LLM 응답에서 첫 JSON 객체를 뽑는다(코드펜스 허용)."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    for candidate in (cleaned, _slice_braces(cleaned)):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None


def _slice_braces(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else ""


def numeric_guard(text: str, allowed: set[str]) -> list[str]:
    """응답 속 숫자 중 Tool 출력에 없는 값을 찾아낸다."""
    allowed_norm = {str(a) for a in allowed}
    allowed_ints = set()
    for token in allowed_norm:
        try:
            value = float(token)
        except ValueError:
            continue
        allowed_ints.add(str(int(value)))
        allowed_ints.add(f"{value:.1f}")
    bad = []
    for match in NUMBER_RE.findall(text or ""):
        token = match.rstrip(".")
        if token in allowed_ints:
            continue
        try:
            if f"{float(token):g}" in {f"{float(a):g}" for a in allowed_norm}:
                continue
        except ValueError:
            pass
        bad.append(token)
    return bad


def collect_numbers(payload: Any) -> set[str]:
    """근거 JSON에서 숫자 토큰을 모두 모아 가드의 허용 집합을 만든다."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            found.add(f"{node:g}" if isinstance(node, float) else str(node))
            if isinstance(node, float):
                found.add(str(round(node)))
                found.add(f"{node:.1f}")
            return
        if isinstance(node, str):
            for token in NUMBER_RE.findall(node):
                found.add(token)
            return
        if isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
            return
        if isinstance(node, (list, tuple, set)):
            for item in node:
                walk(item)

    walk(payload)
    return found
