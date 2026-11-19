"""관광지 카탈로그 로더 — data/catalog/spots.csv (58곳).

좌표는 공개 정보 기반 근사값이며, 영업시간·요금은 2026-11 기준 공개 안내를
수기로 정리한 값이다(변동 가능). 카탈로그는 "대안 후보 풀"일 뿐이며,
추천의 근거 수치는 항상 허브 데이터에서 계산한다.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from . import config
from .models import Spot

REQUIRED_COLUMNS = ("id", "name", "city", "emd", "lat", "lon", "category", "indoor",
                    "open_time", "close_time", "dwell_min", "cost_krw", "themes")


def _bool(text: str) -> bool:
    return str(text).strip().upper() in ("Y", "TRUE", "1", "YES")


def load_spots(path: Path | None = None) -> list[Spot]:
    path = Path(path or config.CATALOG_DIR / "spots.csv")
    with path.open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"카탈로그 컬럼 누락: {missing} ({path})")
        spots = []
        for row in reader:
            if not row.get("id"):
                continue
            themes = tuple(t for t in (row.get("themes") or "").split("|") if t)
            routes = tuple(r for r in (row.get("near_routes") or "").split("|") if r)
            spots.append(Spot(
                id=row["id"].strip(),
                name=row["name"].strip(),
                city=row["city"].strip(),
                emd=row["emd"].strip(),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                category=row["category"].strip(),
                indoor=_bool(row["indoor"]),
                open_time=row["open_time"].strip(),
                close_time=row["close_time"].strip(),
                dwell_min=int(row["dwell_min"]),
                cost_krw=int(row["cost_krw"]),
                themes=themes,
                stroller_ok=_bool(row.get("stroller_ok", "N")),
                low_walk_ok=_bool(row.get("low_walk_ok", "N")),
                near_routes=routes,
            ))
    ids = [s.id for s in spots]
    if len(ids) != len(set(ids)):
        raise ValueError("카탈로그에 중복 id가 있습니다")
    return spots


@lru_cache(maxsize=1)
def catalog() -> dict[str, Spot]:
    return {s.id: s for s in load_spots()}


def spots() -> list[Spot]:
    return list(catalog().values())


def emds() -> list[str]:
    seen: list[str] = []
    for spot in spots():
        if spot.emd not in seen:
            seen.append(spot.emd)
    return seen


def routes() -> list[str]:
    seen: list[str] = []
    for spot in spots():
        for route in spot.near_routes:
            if route not in seen:
                seen.append(route)
    return seen


def spots_in_emd(emd: str) -> list[Spot]:
    return [s for s in spots() if s.emd == emd]


def find_spot(text: str) -> Spot | None:
    """이름·id 부분일치로 스팟 찾기(정확일치 우선)."""
    if not text:
        return None
    norm = text.replace(" ", "")
    db = catalog()
    for spot in db.values():
        if norm == spot.id or norm == spot.name.replace(" ", ""):
            return spot
    for spot in db.values():
        if norm in spot.name.replace(" ", "") or spot.name.replace(" ", "") in norm:
            return spot
    return None


def near_emd(text: str) -> str:
    """'성산에 있는데' 처럼 읍면동 이름만 들어온 경우를 잡는다."""
    if not text:
        return ""
    norm = text.replace(" ", "")
    for emd in emds():
        base = emd.replace(" ", "")
        short = base[:-1] if base.endswith(("읍", "면", "동")) else base
        if base in norm or (len(short) >= 2 and short in norm):
            return emd
    return ""
