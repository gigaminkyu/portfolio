"""빈틈(BinTeum) 데이터 모델 — 에이전트 사이에서 주고받는 객체.

모든 수치 객체는 `evidence`(어느 데이터·어느 시점에서 왔는가)를 함께 들고 다닌다.
이 규칙 하나가 "근거 없는 추천 금지"(Critic 규칙 R4)를 코드로 강제한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any


# ------------------------------------------------------------------ 카탈로그
@dataclass(frozen=True)
class Spot:
    id: str
    name: str
    city: str
    emd: str
    lat: float
    lon: float
    category: str
    indoor: bool
    open_time: str          # "HH:MM"
    close_time: str         # "HH:MM" (24:00 허용)
    dwell_min: int
    cost_krw: int
    themes: tuple[str, ...]
    stroller_ok: bool
    low_walk_ok: bool
    near_routes: tuple[str, ...]

    def open_min(self) -> int:
        return _hhmm(self.open_time)

    def close_min(self) -> int:
        return _hhmm(self.close_time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["themes"] = list(self.themes)
        d["near_routes"] = list(self.near_routes)
        return d


def _hhmm(value: str) -> int:
    hour, _, minute = value.partition(":")
    return int(hour) * 60 + int(minute or 0)


# ------------------------------------------------------------------ 제약카드(Router 출력)
@dataclass
class Constraints:
    raw_query: str = ""
    origin_emd: str = ""            # 현재 위치의 읍면동
    origin_spot: str = ""           # 특정 스팟이면 id
    now: datetime = field(default_factory=datetime.now)
    end_time: str = "18:00"         # 귀가·일정 종료 시각
    party: str = "solo"             # solo | couple | family_kid | with_parents | friends
    mobility: str = "car"           # car | bus | walk
    indoor_required: bool = False
    low_walk: bool = False
    budget_krw: int | None = None
    themes: tuple[str, ...] = ()
    meal_needed: bool = True
    tomorrow: bool = False          # 종료 시각이 이미 지난 경우 → 다음 날 09:00 기준
    confidence: float = 0.0         # Router가 채운 필드 비율
    assumptions: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)   # 되물은 항목(최대 1개)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["now"] = self.now.isoformat(timespec="minutes")
        return d


# ------------------------------------------------------------------ 혼잡지수
@dataclass
class CrowdScore:
    spot_id: str
    spot_name: str
    ci: float                                # 0~100 (높을수록 붐빔)
    terms: dict[str, float]                  # 사용된 항의 0~1 백분위
    weights_used: dict[str, float]           # 재정규화 후 가중치
    dropped: list[str] = field(default_factory=list)   # 결측으로 제외된 항
    evidence: dict[str, Any] = field(default_factory=dict)  # 데이터ID·기준일·원값
    label: str = ""                          # 한산/보통/붐빔
    confidence: str = "ok"                   # ok | low_sample | partial

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ 동선
@dataclass
class Stop:
    order: int
    spot_id: str
    spot_name: str
    emd: str
    category: str
    indoor: bool
    arrive: str
    depart: str
    dwell_min: int
    travel_min: int
    travel_km: float
    ci: int
    ci_label: str
    cost_krw: int
    why: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    key: str
    label: str
    headline: str
    stops: list[Stop]
    totals: dict[str, Any]               # 이동분·거리·비용·평균 CI·방문 수
    rationale: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**{k: v for k, v in asdict(self).items() if k != "stops"},
                "stops": [s.to_dict() for s in self.stops]}


@dataclass
class Violation:
    rule: str
    spot_id: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CriticResult:
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    rounds: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "rounds": self.rounds,
                "violations": [v.to_dict() for v in self.violations],
                "notes": self.notes}


# ------------------------------------------------------------------ 데이터 출처
@dataclass
class DatasetProvenance:
    dataset: str            # flow | tour | bus | weather | wifi
    hub_id: int
    mode: str               # live | cache | snapshot | missing
    rows: int = 0
    base_date_max: str = ""
    source_note: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataProvenance:
    mode: str = "snapshot"        # live | snapshot | mixed | empty
    today: date | None = None
    datasets: list[DatasetProvenance] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {"mode": self.mode,
                "today": self.today.isoformat() if self.today else "",
                "note": self.note,
                "datasets": [d.to_dict() for d in self.datasets]}
