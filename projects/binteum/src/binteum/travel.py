"""이동시간 계산 — 직선거리 × 도로 굴곡 계수 ÷ 수단별 평균 속도.

지도·경로 API에 의존하지 않는다. 외부 지도 API 허용 여부가 확인되지 않았고
(대회 게시판 문의 미답변), 센터 PC에서 외부 도메인이 차단될 수 있기 때문에
"좌표만으로 계산되는 결정론적 근사"를 택했다. 오차는 Critic이 여유시간으로 흡수한다.
"""
from __future__ import annotations

import math
from functools import lru_cache

from . import config

EARTH_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def road_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * config.ROAD_FACTOR


def travel_minutes(distance_km: float, mode: str) -> float:
    mode = mode if mode in config.SPEED_KMH else "car"
    minutes = distance_km / config.SPEED_KMH[mode] * 60.0
    if mode == "bus":
        minutes += config.BUS_WAIT_MIN
    minutes += config.TRANSFER_MIN
    return round(minutes, 1)


def leg(origin: tuple[float, float], target: tuple[float, float], mode: str) -> tuple[float, float]:
    """(분, km) — 두 좌표 사이 이동."""
    km = road_km(origin[0], origin[1], target[0], target[1])
    return travel_minutes(km, mode), round(km, 2)


def reachable_minutes(mode: str) -> float:
    return config.MAX_TRAVEL_MIN.get(mode, 55.0)


@lru_cache(maxsize=4096)
def _cached_leg(lat1: float, lon1: float, lat2: float, lon2: float, mode: str) -> tuple[float, float]:
    return leg((lat1, lon1), (lat2, lon2), mode)


def leg_cached(origin: tuple[float, float], target: tuple[float, float], mode: str) -> tuple[float, float]:
    return _cached_leg(origin[0], origin[1], target[0], target[1], mode)


def mode_for_route(distance_km: float, requested: str, spot_low_walk: bool) -> str:
    """걷기 힘든 동반이면 먼 거리는 차량으로 승격한다."""
    if requested == "walk" and distance_km > 2.5:
        return "bus"
    if requested == "car" and distance_km < 1.2:
        return "walk"
    return requested
