"""빈틈(BinTeum) 전역 설정 — 모든 수치 파라미터를 한 곳에 모은다.

기획서 §3.5의 CI 산식과 §p14의 실행환경 가정이 모두 이 파일에 대응한다.
값을 바꾸면 산식 문서(docs/데이터활용명세.md)도 함께 고쳐야 한다.
"""
from __future__ import annotations

import os
from pathlib import Path

VERSION = "1.0.0"
APP_NAME = "빈틈(BinTeum)"
APP_TAGLINE = "제주 여행의 빈 시간을 찾아주는 실측 혼잡 회피 Agent"

# ---------------------------------------------------------------- 경로
PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent.parent          # work/dacon-binteum
SRC_DIR = PROJECT_DIR / "src"
DATA_DIR = Path(os.environ.get("BINTEUM_DATA_DIR", PROJECT_DIR / "data"))
CATALOG_DIR = DATA_DIR / "catalog"
SNAPSHOT_DIR = DATA_DIR / "snapshot"
LIVE_DIR = SNAPSHOT_DIR / "live"
CACHE_DIR = Path(os.environ.get("BINTEUM_CACHE_DIR", PROJECT_DIR / "var" / "cache"))
OUT_DIR = Path(os.environ.get("BINTEUM_OUT_DIR", PROJECT_DIR / "out"))
STATIC_DIR = PKG_DIR / "static"

# ---------------------------------------------------------------- 허브 API
# 실제 데이터 조회 엔드포인트(2026-11-18 실호출 확인):
#   {HUB_PROXY_BASE}/{데이터키}/{프로젝트키}?startDate=&endDate=&limit=100
# `jejudatahub.net/api/data/view?id=`는 메타데이터만 주므로 데이터 조회에 쓰지 않는다.
HUB_PROXY_BASE = os.environ.get("JEJU_HUB_PROXY_BASE", "https://open.jejudatahub.net/api/proxy")
HUB_BASE_URL = os.environ.get("JEJU_HUB_BASE_URL", HUB_PROXY_BASE)   # 하위 호환
HUB_KEY_ENV = ("JEJU_DATA_HUB_KEY", "JEJU_HUB_KEY")     # 매뉴얼 표기 2가지를 모두 인정
HUB_TIMEOUT_S = float(os.environ.get("JEJU_HUB_TIMEOUT", "20"))
HUB_RETRIES = int(os.environ.get("JEJU_HUB_RETRIES", "2"))
# 응답 1회 상한(서버 고정: limit<=100). 넘는 구간은 날짜를 쪼개 반복 호출한다.
HUB_PAGE_LIMIT = int(os.environ.get("JEJU_HUB_PAGE_LIMIT", "100"))
HUB_SPLIT_DEPTH = int(os.environ.get("JEJU_HUB_SPLIT_DEPTH", "8"))

# 데이터셋별 프로젝트 데이터키 (제주데이터허브 프로젝트에 '연결'된 데이터만 값이 있다).
# 비어 있는 데이터셋은 호출하지 않고 not_connected로 표시한 뒤 스냅샷으로 폴백한다.
DATASET_DATA_KEYS = {
    # 공개 저장소에는 키 값을 두지 않는다. .env 또는 환경변수로 주입한다.
    "flow": os.environ.get("JEJU_HUB_DATA_KEY_FLOW", ""),   # 583 읍면동 단위 내국인 유동인구
    "tour": os.environ.get("JEJU_HUB_DATA_KEY_TOUR", ""),   # 591 프로젝트 미연결
    "tour_foreign": "",                             # 592 프로젝트 미연결
    "bus": "",                                      # 614 프로젝트 미연결
    "weather": "",                                  # 579 프로젝트 미연결
    "wifi": "",                                     # 618 프로젝트 미연결
}

# 허브 데이터 ID (기획서 §4.1 표와 1:1)
DATASET_IDS = {
    "flow": 583,      # 읍면동 단위 내국인 유동인구 (일)
    "tour": 591,      # 관광지별 내국인 유입자수 (월)
    "tour_foreign": 592,
    "bus": 614,       # 일일 노선별 버스 이용자 정보 (일)
    "weather": 579,   # 일별 기상 정보 (일)
    "wifi": 618,      # 제주 공공와이파이 AP 정보 (일)
}

# ---------------------------------------------------------------- CI 산식
# CI = 100 * Σ w_k·P_k / Σ w_k  (결측 항은 제외하고 자동 재정규화)
CI_WEIGHTS = {"visit": 0.45, "tour": 0.25, "bus": 0.20, "weather": 0.10}

# 583 visitPop 백분위 기준 창(주). "최근 8주 동일 요일유형" (기획서 §3.5)
BASELINE_WEEKS = 8
# 614 버스 수요 백분위 기준 창(주)
BUS_BASELINE_WEEKS = 8
# 591 계절 기준선: 관광지 월별 관광객 ÷ 최근 3년 동월 최대값
TOUR_BASELINE_YEARS = 3

# 날씨 항: 강수·강풍이면 야외 -·실내 + (0~1 클램프)
WEATHER_RAIN_FULL_MM = 10.0     # 이 값에서 강수 심각도 1.0
WEATHER_WIND_FULL_MS = 15.0     # 이 값에서 강풍 심각도 1.0
WEATHER_RAIN_TRIGGER_MM = 5.0   # 기획서에 명시한 임계(5mm↑)
WEATHER_WIND_TRIGGER_MS = 10.0  # 기획서에 명시한 임계(10m/s↑)

# ---------------------------------------------------------------- 이동·시간
# 도로 굴곡 계수(직선거리 → 실제 주행거리 근사)와 수단별 평균 속도
ROAD_FACTOR = 1.35
SPEED_KMH = {"car": 38.0, "bus": 22.0, "walk": 4.5}
BUS_WAIT_MIN = 8.0
TRANSFER_MIN = 5.0            # 렌터카 주차·도보 이동 여유
MAX_TRAVEL_MIN = {"car": 55.0, "bus": 70.0, "walk": 25.0}

# ---------------------------------------------------------------- 시간대 곡선(가정)
# 583은 일 단위 실측이므로 시간대 분포는 공개 데이터가 아니다.
# 아래 표는 "가정(assumption)"이며 UI·리포트에 '추정'으로 표기한다.
HOUR_PROFILE_ASSUMPTION = {
    "해변":   {0: .15, 6: .25, 9: .45, 11: .70, 13: .95, 15: 1.0, 17: .85, 19: .45, 21: .2, 23: .15},
    "자연":   {0: .05, 6: .15, 9: .60, 11: .95, 13: 1.0, 15: .90, 17: .55, 19: .2, 21: .1, 23: .05},
    "오름":   {0: .05, 6: .25, 9: .70, 11: .95, 13: .85, 15: .80, 17: .55, 19: .2, 21: .1, 23: .05},
    "시장":   {0: .05, 6: .20, 9: .55, 11: .90, 13: .85, 15: .70, 17: .95, 19: .90, 21: .5, 23: .1},
    "미식":   {0: .05, 6: .10, 9: .25, 11: .60, 13: .95, 15: .55, 17: .70, 19: 1.0, 21: .85, 23: .4},
    "실내문화": {0: .0, 6: .0, 9: .30, 11: .80, 13: .95, 15: 1.0, 17: .70, 19: .30, 21: .05, 23: .0},
    "테마파크": {0: .0, 6: .0, 9: .40, 11: .85, 13: 1.0, 15: .95, 17: .60, 19: .35, 21: .15, 23: .0},
    "역사":   {0: .0, 6: .05, 9: .35, 11: .85, 13: .95, 15: .90, 17: .60, 19: .25, 21: .05, 23: .0},
    "예술":   {0: .05, 6: .05, 9: .20, 11: .55, 13: .70, 15: .75, 17: .80, 19: .70, 21: .40, 23: .15},
    "항구":   {0: .10, 6: .35, 9: .70, 11: .85, 13: .80, 15: .70, 17: .65, 19: .50, 21: .30, 23: .15},
}
DEFAULT_HOUR_PROFILE = HOUR_PROFILE_ASSUMPTION["자연"]

# ---------------------------------------------------------------- 계획 기본값
DEFAULT_START_HOUR = 9
DEFAULT_END_HOUR = 18
DEFAULT_RETURN_BUFFER_MIN = 30     # 숙소 복귀 여유(동선 마지막 슬롯 이후)
PLAN_VARIANTS = ("quiet", "short", "theme")
PLAN_VARIANT_LABEL = {
    "quiet": "안 A · 한산 우선",
    "short": "안 B · 이동 최소",
    "theme": "안 C · 취향·실내 우선",
}
MAX_CRITIC_REJECTIONS = 1          # Critic 반려 루프 최대 1회 (기획서 §p10)

# ---------------------------------------------------------------- LLM (선택)
LLM_PROVIDER_ENV = "BINTEUM_LLM_PROVIDER"    # openai | anthropic | none
LLM_MODEL_ENV = "BINTEUM_LLM_MODEL"
LLM_TIMEOUT_S = float(os.environ.get("BINTEUM_LLM_TIMEOUT", "20"))
LLM_MAX_OUTPUT_TOKENS = 900


def hub_key() -> str:
    """환경변수에서 제주데이터허브 인증키를 읽는다. ZIP에는 절대 넣지 않는다."""
    for name in HUB_KEY_ENV:
        value = os.environ.get(name, "").strip()
        if value and not value.lower().startswith(("your", "xxxx", "<")):
            return value
    return ""


def llm_settings() -> dict:
    provider = os.environ.get(LLM_PROVIDER_ENV, "").strip().lower()
    if not provider:
        # 키만 있고 provider가 없으면 자동 감지
        if os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            provider = "none"
    model = os.environ.get(LLM_MODEL_ENV, "").strip()
    if not model:
        model = {"openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-latest",
                 "local": "qwen2.5:3b"}.get(provider, "")
    return {"provider": provider, "model": model}


def ensure_dirs() -> None:
    for path in (CACHE_DIR, OUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
