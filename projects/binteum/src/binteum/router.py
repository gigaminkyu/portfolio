"""Router Agent — 사용자 문장에서 여행 제약을 뽑아 '제약카드'로 만든다.

규칙 우선(결정론적) + LLM 보조(선택). LLM이 없거나 실패해도 규칙만으로 동작한다.
제약이 비면 **딱 1개만** 되묻는다(기획서 §3.4). 나머지는 기본값 + 가정 목록으로 남긴다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import catalog, config
from .models import Constraints
from .llm import LLMClient, collect_numbers

PARTY_RULES: tuple[tuple[str, str], ...] = (
    (r"아이|애(?![월])|아기|유아|아동|초등|아들|딸|조카", "family_kid"),
    (r"부모님|어머니|아버지|어르신|할머니|할아버지|장모|장인|효도", "with_parents"),
    (r"커플|신혼|남편|아내|와이프|남친|여친|부부|연인", "couple"),
    (r"친구|동료|일행|단체", "friends"),
    (r"혼자|혼행|나 ?혼자|솔로", "solo"),
)
THEME_WORDS: dict[str, str] = {
    "해변": "해변", "바다": "해변", "해수욕": "해변", "오름": "오름", "시장": "시장",
    "맛집": "미식", "먹": "미식", "미식": "미식", "식당": "미식", "카페": "카페",
    "야경": "야경", "사진": "사진", "자연": "자연", "숲": "산책", "산책": "산책",
    "역사": "역사", "예술": "예술", "미술": "예술", "가족": "가족", "액티비티": "액티비티",
    "체험": "액티비티", "정원": "정원", "과학": "과학",
}
MOBILITY_RULES: tuple[tuple[str, str], ...] = (
    (r"렌터카|렌트|운전|차로|차량|자가용", "car"),
    (r"버스|대중교통|노선|시내버스", "bus"),
    (r"도보|걸어서|걷기로|자전거", "walk"),
)
def _minutes(hhmm: str) -> int:
    hour, _, minute = str(hhmm).partition(":")
    try:
        return int(hour) * 60 + int(minute or 0)
    except ValueError:
        return 0


TIME_END_PATTERNS = (
    r"(\d{1,2})\s*시\s*(?:까지|전까지|전에|마감)",
    r"(\d{1,2})\s*시(?:\s*\d{1,2}\s*분)?\s*(?:에\s*)?(?:귀가|복귀|숙소|집에|돌아)",
    r"(?:귀가|복귀|숙소\s*복귀)\D{0,6}(\d{1,2})\s*시",
)


class Router:
    def __init__(self, llm: LLMClient | None = None, trace=None):
        self.llm = llm
        self.trace = trace

    def parse(self, query: str = "", *, now: datetime | None = None,
              spot_id: str | None = None, emd: str | None = None,
              end_time: str | None = None, party: str | None = None,
              mobility: str | None = None, indoor: bool | None = None,
              budget: int | None = None, themes: str | list | None = None,
              use_llm: bool = True) -> Constraints:
        now = now or datetime.now()
        text = (query or "").strip()
        constraints = Constraints(raw_query=text, now=now)
        assumptions: list[str] = []

        # --- 위치: 명시 입력 > 문장 속 관광지 > 문장 속 읍면동
        if spot_id:
            spot = catalog.catalog().get(spot_id)
            if spot:
                constraints.origin_spot = spot.id
                constraints.origin_emd = spot.emd
        if not constraints.origin_emd and emd:
            constraints.origin_emd = emd
        if not constraints.origin_emd and text:
            spot = catalog.find_spot(text)
            if spot:
                constraints.origin_spot = spot.id
                constraints.origin_emd = spot.emd
            else:
                constraints.origin_emd = catalog.near_emd(text)

        # --- 종료 시각
        end = end_time or self._parse_end_time(text, now)
        constraints.end_time = end
        if not end_time and end:
            assumptions.append(f"종료 시각 {end} — 문장/기본값에서 추정")
        # 이미 지난 시각을 종료로 주면 오늘 안에 남은 시간이 없다 → 다음 날 09:00 기준으로 계산
        if end and _minutes(end) <= now.hour * 60 + now.minute + 20:
            constraints.tomorrow = True
            assumptions.append(
                f"현재 {now.strftime('%H:%M')}이 종료 시각 {end} 이후 → 다음 날 "
                f"{config.DEFAULT_START_HOUR:02d}:00 출발 기준으로 계산")

        # --- 동행
        constraints.party = party or self._parse_party(text) or "solo"
        if not party and not self._parse_party(text):
            assumptions.append("동행 미지정 → 1인 여행으로 가정")

        # --- 이동수단
        parsed_mobility = mobility or self._parse_mobility(text)
        if parsed_mobility:
            constraints.mobility = parsed_mobility
        else:
            constraints.mobility = "car"
            assumptions.append("이동수단 미지정 → 렌터카 가정(제주 방문객 다수)")

        # --- 실내 요구·보행 부담
        constraints.indoor_required = bool(indoor) if indoor is not None else self._parse_indoor(text)
        constraints.low_walk = self._parse_low_walk(text)
        if constraints.party in ("family_kid", "with_parents"):
            constraints.low_walk = constraints.low_walk or constraints.party == "with_parents"

        # --- 예산·테마
        constraints.budget_krw = budget if budget is not None else self._parse_budget(text)
        constraints.themes = tuple(self._parse_themes(themes, text))

        # --- 남은 필드 신뢰도
        filled = sum(1 for value in (
            constraints.origin_emd, constraints.end_time, party,
            parsed_mobility, constraints.themes,
        ) if value)
        constraints.confidence = round(min(1.0, filled / 5.0), 2)

        # --- 규칙으로 못 채운 위치는 LLM에게 한 번 묻는다(있을 때만)
        if use_llm and self.llm and self.llm.available and not constraints.origin_emd:
            llm_filled = self._llm_fill(text, now)
            if llm_filled:
                emd_value = llm_filled.get("origin_emd") or ""
                if catalog.near_emd(emd_value):
                    constraints.origin_emd = catalog.near_emd(emd_value)
                if llm_filled.get("end_time"):
                    constraints.end_time = str(llm_filled["end_time"])[:5]
                if not constraints.themes and isinstance(llm_filled.get("themes"), list):
                    constraints.themes = tuple(str(t) for t in llm_filled["themes"][:3])

        if not constraints.origin_emd:
            constraints.asked = ["현재 계신 읍면동(또는 근처 관광지)을 알려주세요."]
        elif len(constraints.assumptions) >= 3 and not constraints.themes:
            constraints.asked = []            # 되묻지 않고 기본값으로 진행

        constraints.assumptions = assumptions
        if self.trace:
            self.trace.tool("router.parse", ok=bool(constraints.origin_emd), ms=0.0,
                            constraints=constraints.to_dict())
        return constraints

    # ---------------------------------------------------------------- 규칙
    @staticmethod
    def _parse_end_time(text: str, now: datetime) -> str:
        if text:
            for pattern in TIME_END_PATTERNS:
                match = re.search(pattern, text)
                if match:
                    hour = int(match.group(1))
                    if hour < 12 and re.search(r"오후|저녁|밤", text):
                        hour += 12
                    # '6시까지'를 오전 6시로 읽지 않도록: 이미 지난 시각이면 오후로 본다.
                    if hour < 12 and hour <= now.hour:
                        hour += 12
                    if 6 <= hour <= 24:
                        return f"{min(hour, 23):02d}:00"
        if now.hour < 15:
            return f"{config.DEFAULT_END_HOUR:02d}:00"
        return f"{min(23, now.hour + 4):02d}:00"

    @staticmethod
    def _parse_party(text: str) -> str:
        for pattern, value in PARTY_RULES:
            if re.search(pattern, text or ""):
                return value
        return ""

    @staticmethod
    def _parse_mobility(text: str) -> str:
        for pattern, value in MOBILITY_RULES:
            if re.search(pattern, text or ""):
                return value
        return ""

    @staticmethod
    def _parse_indoor(text: str) -> bool:
        if not text:
            return False
        if re.search(r"실외|야외|밖에서", text) and not re.search(r"실내", text):
            return False
        return bool(re.search(r"실내|비 ?(?:가|와)|우천|박물관|전시", text))

    @staticmethod
    def _parse_low_walk(text: str) -> bool:
        return bool(re.search(r"걷기\s*(?:힘들|어려|싫)|무릎|다리 ?(?:아프|불편)|휠체어|유모차|짧게 걷", text or ""))

    @staticmethod
    def _parse_budget(text: str):
        if not text:
            return None
        won = re.search(r"(\d{4,6})\s*원", text)
        if won:
            return int(won.group(1))
        man = re.search(r"(\d{1,2}(?:\.\d)?)\s*만\s*원", text)
        if man:
            return int(float(man.group(1)) * 10000)
        return None

    @staticmethod
    def _parse_themes(themes, text: str) -> list[str]:
        found: list[str] = []
        if isinstance(themes, str):
            found.extend(t.strip() for t in re.split(r"[,| ]+", themes) if t.strip())
        elif isinstance(themes, (list, tuple)):
            found.extend(str(t) for t in themes if str(t).strip())
        for word, theme in THEME_WORDS.items():
            if word in (text or "") and theme not in found:
                found.append(theme)
        return found[:4]

    def _llm_fill(self, text: str, now: datetime) -> dict | None:
        prompt = (
            "다음 여행 문장에서 제약을 추출해 JSON으로만 답하세요.\n"
            '스키마: {"origin_emd": "문장에 나온 읍면동 또는 빈 문자열", '
            '"end_time": "HH:MM 또는 빈 문자열", "themes": ["해변","오름","시장","미식","실내","가족" 중 최대 3개"]}\n'
            f"현재 시각: {now.strftime('%Y-%m-%d %H:%M')}\n문장: {text}\n"
            "없는 값은 빈 문자열로 두고 추측해서 만들지 마세요."
        )
        allowed = collect_numbers({"now": now.strftime("%Y %m %d %H")})
        return self.llm.json_complete(prompt, allowed_numbers=allowed) if self.llm else None
