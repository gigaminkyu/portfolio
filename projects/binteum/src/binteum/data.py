"""Data Agent의 Tool 계층 — 이중 모드(실시간 / 스냅샷) 데이터 로딩과 정규화.

로딩 우선순위(각 데이터셋 독립):
  1) 허브 Open API 실호출 (JEJU_DATA_HUB_KEY 가 있을 때, --offline 이 아닐 때)
  2) 로컬 캐시 (같은 파라미터 재실행 → 네트워크 불필요)
  3) data/snapshot/live/*.json  (사용자가 `cli fetch` 로 받아 둔 실제 수집분)
  4) data/snapshot/*.json       (ZIP에 동봉된 데모 스냅샷 — 기본 동작 보장)
  5) 없음 → 결측 처리(가중치 자동 재정규화)

각 데이터셋의 출처(mode)는 응답 JSON·화면 배지·trace에 그대로 노출된다.
평가자가 어떤 환경에서 실행해도 "이 숫자가 어디서 왔는지"를 항상 알 수 있다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from . import config, fields
from .hub import HubClient
from .models import DatasetProvenance, DataProvenance

MODE_KO = {
    "live": "실시간 허브 API",
    "cache": "허브 API 캐시",
    "collected": "직접 수집 스냅샷",
    "snapshot": "동봉 데모 스냅샷",
    "partial": "일부 결측",
    "missing": "결측",
}


def _d(value: str) -> date | None:
    try:
        return datetime.strptime(fields.norm_date(value), "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


@dataclass
class Dataset:
    name: str
    rows: list[dict] = field(default_factory=list)
    prov: DatasetProvenance | None = None

    @property
    def ok(self) -> bool:
        return bool(self.rows)


class Weather:
    """한 시점·한 지점의 기상값(579 + 578 조인)."""

    def __init__(self, *, date_str: str, observatory: str, rain: float, wind_max: float,
                 wind_avg: float, avg_temp: float, high: float, low: float, lat: float, lon: float):
        self.date = date_str
        self.observatory = observatory
        self.rain = rain
        self.wind_max = wind_max
        self.wind_avg = wind_avg
        self.avg_temp = avg_temp
        self.high = high
        self.low = low
        self.latlat = (lat, lon)

    @property
    def bad_weather(self) -> bool:
        return (self.rain >= config.WEATHER_RAIN_TRIGGER_MM
                or self.wind_max >= config.WEATHER_WIND_TRIGGER_MS)

    def to_dict(self) -> dict:
        return {"date": self.date, "observatory": self.observatory, "rain_mm": self.rain,
                "wind_max_ms": self.wind_max, "avg_temp_c": self.avg_temp,
                "bad_weather": self.bad_weather}


class DataPortal:
    """5개 데이터셋을 한 번에 로딩하고, 지수 계산에 필요한 조회 API를 제공한다."""

    def __init__(self, hub: HubClient | None = None, offline: bool = False,
                 snapshot_dir: Path | None = None, live_dir: Path | None = None,
                 trace=None):
        self.hub = hub if hub is not None else HubClient(trace=trace)
        self.offline = offline
        self.snapshot_dir = Path(snapshot_dir or config.SNAPSHOT_DIR)
        self.live_dir = Path(live_dir or config.LIVE_DIR)
        self.trace = trace
        self.datasets: dict[str, Dataset] = {}
        self.provenance = DataProvenance()
        self.reference_date: str = ""
        self._loaded = False

    # ---------------------------------------------------------------- 로딩
    def load(self, today: date | None = None) -> DataProvenance:
        today = today or date.today()
        provs: list[DatasetProvenance] = []
        for name in ("flow", "tour", "bus", "weather", "wifi"):
            dataset = self._load_one(name, today)
            self.datasets[name] = dataset
            if dataset.prov:
                provs.append(dataset.prov)
        modes = {p.mode for p in provs if p.mode not in ("missing",)}
        real = modes & {"live", "cache", "collected"}
        if not modes:
            overall = "empty"
        elif modes <= {"live", "cache"}:
            overall = "live"
        elif modes <= {"live", "cache", "collected"}:
            overall = "collected"
        elif not real:
            overall = "snapshot"
        else:
            overall = "mixed"
        self.reference_date = self._reference_date(today)
        self.provenance = DataProvenance(
            mode=overall, today=_d(self.reference_date) or today, datasets=provs,
            note=self._overall_note(overall, provs),
        )
        self._loaded = True
        return self.provenance

    def _load_one(self, name: str, today: date) -> Dataset:
        hub_id = config.DATASET_IDS[name]
        error = ""

        if self.hub.has_key and not self.offline:
            result = self.hub.fetch(name, self._query_params(name, today))
            if result.ok:
                normalized = self._normalize(name, result.rows)
                if normalized:
                    return Dataset(name, normalized, DatasetProvenance(
                        dataset=name, hub_id=hub_id, mode=result.mode,
                        rows=len(normalized), base_date_max=self._max_key(normalized),
                        source_note=f"허브 Open API id={hub_id}"))
                error = f"정규화 결과 0행 (mode={result.mode})"
            else:
                error = result.error or "실호출 실패"

        for mode, folder in (("collected", self.live_dir), ("snapshot", self.snapshot_dir)):
            path = folder / f"{name}.json"
            payload = _read_json(path)
            if payload is None:
                continue
            rows = self._normalize(name, payload.get("rows", []))
            if not rows:
                continue
            meta = payload.get("meta", {})
            note = meta.get("note", "")
            if mode == "snapshot" and meta.get("source"):
                note = f"{note} (source={meta.get('source')})".strip()
            self._trace(name, mode, len(rows), error)
            return Dataset(name, rows, DatasetProvenance(
                dataset=name, hub_id=hub_id, mode=mode, rows=len(rows),
                base_date_max=self._max_key(rows),
                source_note=f"{note} · {meta.get('path', path.name)}".strip(" ·"),
                error=error))

        self._trace(name, "missing", 0, error)
        return Dataset(name, [], DatasetProvenance(
            dataset=name, hub_id=hub_id, mode="missing", rows=0,
            error=error or "스냅샷 없음"))

    @staticmethod
    def _query_params(name: str, today: date) -> dict[str, Any]:
        """허브 파라미터. 583·614의 '분석 시작일/종료일' 표기는 발급 후 첫 실호출로
        확정해야 하며(README 문제해결 참고), 실패해도 스냅샷 폴백으로 동작한다."""
        end = today
        start = today - timedelta(days=config.BASELINE_WEEKS * 7 + 7)
        if name in ("flow", "bus", "weather"):
            return {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d")}
        if name in ("tour", "tour_foreign"):
            return {"startMonth": f"{today.year - config.TOUR_BASELINE_YEARS}01",
                    "endMonth": f"{today.year - 1}12"}
        return {}

    # ---------------------------------------------------------------- 정규화
    def _normalize(self, name: str, rows: Iterable[dict]) -> list[dict]:
        handler = getattr(self, f"_norm_{name}", None)
        if handler is None:
            return [r for r in rows if isinstance(r, dict)]
        out: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            record = handler(row)
            if record:
                out.append(record)
        return out

    @staticmethod
    def _norm_flow(row: dict) -> dict | None:
        emd = str(fields.pick(row, "emd", "") or "").strip()
        day = fields.norm_date(fields.pick(row, "date"))
        if not emd or not day:
            return None
        visit = fields.as_int(fields.pick(row, "visit_pop"))
        return {"date": day, "city": str(fields.pick(row, "city", "") or "").strip(),
                "emd": emd, "gender": str(fields.pick(row, "gender", "전체") or "전체"),
                "age": str(fields.pick(row, "age", "계") or "계"),
                "visit": visit,
                "resd": fields.as_int(fields.pick(row, "resd_pop")),
                "work": fields.as_int(fields.pick(row, "work_pop"))}

    @staticmethod
    def _norm_tour(row: dict) -> dict | None:
        name = str(fields.pick(row, "spot_name", "") or "").strip()
        month = fields.norm_month(fields.pick(row, "month"))
        if not name or len(month) != 6:
            return None
        return {"month": month, "name": name,
                "visitors": fields.as_int(fields.pick(row, "visitors")),
                "pay_type": str(fields.pick(row, "pay_type", "") or "")}

    @staticmethod
    def _norm_bus(row: dict) -> dict | None:
        route = str(fields.pick(row, "route", "") or "").strip()
        day = fields.norm_date(fields.pick(row, "date"))
        if not route or not day:
            return None
        return {"date": day, "route": route,
                "move_type": str(fields.pick(row, "move_type", "") or ""),
                "users": fields.as_int(fields.pick(row, "user_count"))}

    @staticmethod
    def _norm_weather(row: dict) -> dict | None:
        day = fields.norm_date(fields.pick(row, "date"))
        if not day:
            return None
        return {"date": day,
                "observatory": str(fields.pick(row, "observatory", "") or ""),
                "rain": fields.as_float(fields.pick(row, "rain")),
                "wind_max": fields.as_float(fields.pick(row, "wind_max")),
                "wind_avg": fields.as_float(fields.pick(row, "wind_avg")),
                "avg_temp": fields.as_float(fields.pick(row, "avg_temp")),
                "high": fields.as_float(fields.pick(row, "high_temp")),
                "low": fields.as_float(fields.pick(row, "low_temp")),
                "lat": fields.as_float(fields.pick(row, "lat")),
                "lon": fields.as_float(fields.pick(row, "lon"))}

    @staticmethod
    def _norm_wifi(row: dict) -> dict | None:
        lat = fields.as_float(fields.pick(row, "lat"))
        lon = fields.as_float(fields.pick(row, "lon"))
        category = str(fields.pick(row, "ap_category", "") or "").strip()
        if not lat or not lon:
            return None
        return {"category": category,
                "detail": str(fields.pick(row, "ap_category_detail", "") or ""),
                "place": str(fields.pick(row, "install_loc", "") or ""),
                "emd": str(fields.pick(row, "emd", "") or ""),
                "lat": lat, "lon": lon,
                "base_date": fields.norm_date(fields.pick(row, "date"))}

    # ---------------------------------------------------------------- 조회 API
    def _ref(self) -> str:
        return self.reference_date or self._reference_date(date.today())

    def _reference_date(self, today: date) -> str:
        dates: list[str] = []
        for dataset in self.datasets.values():
            for row in dataset.rows:
                value = row.get("date")
                if value:
                    dates.append(value)
        if not dates:
            return today.strftime("%Y%m%d")
        latest = max(_d(d) or today for d in dates)
        # 스냅샷이 미래(데모)일 수 있으므로 today와 min을 취한다
        return min(latest, today).strftime("%Y%m%d") if latest > today else latest.strftime("%Y%m%d")

    def _max_key(self, rows: list[dict]) -> str:
        values = [r.get("date") or r.get("month") or "" for r in rows]
        return max(values) if values else ""

    def flow_dates(self) -> list[str]:
        return sorted({r["date"] for r in self.datasets.get("flow", Dataset("flow")).rows
                       if r["date"] <= self._ref()})

    def visit_series(self, emd: str) -> dict[str, int]:
        """읍면동별 일별 방문인구(성·연령 합산)."""
        series: dict[str, int] = {}
        for row in self.datasets.get("flow", Dataset("flow")).rows:
            if row["emd"] != emd or row["date"] > self._ref():
                continue
            series[row["date"]] = series.get(row["date"], 0) + row["visit"]
        return series

    def emd_list(self) -> list[str]:
        return sorted({r["emd"] for r in self.datasets.get("flow", Dataset("flow")).rows})

    def tour_series(self, name: str) -> dict[str, int]:
        series: dict[str, int] = {}
        for row in self.datasets.get("tour", Dataset("tour")).rows:
            if _name_match(row["name"], name):
                series[row["month"]] = series.get(row["month"], 0) + row["visitors"]
        return series

    def tour_names(self) -> list[str]:
        return sorted({r["name"] for r in self.datasets.get("tour", Dataset("tour")).rows})

    def bus_series(self, routes: Iterable[str]) -> dict[str, int]:
        wanted = set(routes)
        series: dict[str, int] = {}
        for row in self.datasets.get("bus", Dataset("bus")).rows:
            if wanted and row["route"] not in wanted:
                continue
            if row["date"] > self._ref():
                continue
            series[row["date"]] = series.get(row["date"], 0) + row["users"]
        return series

    def weather_for(self, lat: float, lon: float, day: str | None = None) -> Weather | None:
        day = day or self._ref()
        rows = [r for r in self.datasets.get("weather", Dataset("weather")).rows
                if r["date"] == day]
        if not rows:
            return None
        best = min(rows, key=lambda r: (abs(r["lat"] - lat) + abs(r["lon"] - lon))
                   if r["lat"] and r["lon"] else 9e9)
        return Weather(date_str=best["date"], observatory=best["observatory"],
                       rain=best["rain"], wind_max=best["wind_max"],
                       wind_avg=best["wind_avg"], avg_temp=best["avg_temp"],
                       high=best["high"], low=best["low"],
                       lat=best["lat"], lon=best["lon"])

    def wifi_aps(self) -> list[dict]:
        return list(self.datasets.get("wifi", Dataset("wifi")).rows)

    # ---------------------------------------------------------------- 내부
    def _overall_note(self, mode: str, provs: list | None = None) -> str:
        real = [p.dataset for p in (provs or []) if p.mode in ("live", "cache", "collected")]
        demo = [p.dataset for p in (provs or []) if p.mode == "snapshot"]
        if mode == "live":
            return "허브 Open API 실시간 응답으로 계산했습니다."
        if mode == "collected":
            return ("제주데이터허브에서 직접 수집한 실측 스냅샷으로 계산했습니다"
                    f"({', '.join(real)}).")
        if mode == "snapshot":
            return ("ZIP에 동봉된 스냅샷으로 계산했습니다. 스냅샷 meta.source 값이 "
                    "synthetic-demo 이면 실측이 아닌 스키마 검증용 합성 데이터입니다.")
        if mode == "mixed":
            return (f"실측 수집분({', '.join(real)})과 합성 데모 스냅샷({', '.join(demo)})을 "
                    "함께 사용했습니다. 데이터셋별 출처는 배지와 결과 JSON에 표시됩니다.")
        if mode == "empty":
            return "모든 데이터셋이 결측입니다. CI를 계산할 수 없습니다."
        return ""

    def _trace(self, dataset: str, mode: str, rows: int, error: str) -> None:
        if self.trace:
            self.trace.tool(f"data_load[{dataset}]", ok=mode not in ("missing",),
                            ms=0.0, mode=mode, rows=rows, error=error)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _name_match(candidate: str, target: str) -> bool:
    a = str(candidate).replace(" ", "")
    b = str(target).replace(" ", "")
    return bool(a and b) and (a == b or b in a or a in b)
