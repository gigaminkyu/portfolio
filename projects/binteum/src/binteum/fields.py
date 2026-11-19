"""허브 응답 필드 별칭 사전.

허브 Open API의 응답 필드명은 데이터셋마다 표기가 다르다(카멜케이스/스네이크/한글).
인증키 없이 호출해 본 실측이 583·579·618 등 일부에만 있으므로,
파서는 "정확한 키 이름"이 아니라 "별칭 우선순위"로 값을 찾는다.
이렇게 하면 필드명이 조금 달라도 파이프라인이 죽지 않는다.
"""
from __future__ import annotations

ALIASES: dict[str, tuple[str, ...]] = {
    # --- 공통
    "date": ("baseDate", "base_date", "날짜", "date", "base_ymd"),
    "emd": ("emd", "emd_nm", "emdName", "읍면동", "행정동", "address_dong", "dong"),
    "city": ("city", "시군구", "sigungu", "resd"),
    "gender": ("gender", "sex", "성별"),
    "age": ("ageGroup", "age", "연령대", "age_group"),
    "visit_pop": ("visitPop", "visit_pop_cnt", "visit_pop", "방문인구", "tourist_pop"),
    "resd_pop": ("resdPop", "resd_pop_cnt", "resd_pop", "거주인구"),
    "work_pop": ("workPop", "work_pop_cnt", "work_pop", "직장인구"),
    # --- 591/592 관광지 관광객수
    "month": ("date", "base_ym", "년월", "ym", "baseDate", "날짜", "base_ymd"),
    "spot_name": ("name", "touristName", "관광지명", "tour_name", "spotName"),
    "pay_type": ("payType", "지불방법", "pay_type", "무료여부"),
    "visitors": ("visitors", "touristCnt", "관광객수", "userCnt", "count", "cnt"),
    # --- 614 버스
    "route": ("routeName", "route_name", "노선명", "bus_route_name"),
    "route_sub": ("routeSubName", "노선부제"),
    "move_type": ("moveType", "승차환승", "get_on_off_type"),
    "user_count": ("userCount", "user_count", "이용자수", "cnt"),
    # --- 579 날씨
    "observatory": ("observatoryName", "관측소명", "obs_name"),
    "avg_temp": ("averageTemperature", "avg_temp", "평균기온"),
    "low_temp": ("lowestTemperature", "최저기온"),
    "high_temp": ("highestTemperature", "최고기온"),
    "rain": ("dailyRainfall", "rain", "일강수량", "rainfall"),
    "wind_max": ("maximumWindSpeed", "max_wind", "최대풍속"),
    "wind_avg": ("averageWindSpeed", "평균풍속"),
    # --- 618 와이파이 AP
    "ap_group": ("ap_group_name", "AP그룹"),
    "ap_category": ("category", "카테고리"),
    "ap_category_detail": ("category_detail", "카테고리상세"),
    "install_loc": ("install_location_detail", "설치위치"),
    "lat": ("latitude", "lat", "위도"),
    "lon": ("longitude", "lon", "경도"),
}


def pick(row: dict, key: str, default=None):
    """별칭 우선순위대로 값을 찾아 돌려준다."""
    for alias in ALIASES.get(key, (key,)):
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return default


def as_int(value, default: int = 0) -> int:
    """'***' 마스킹, '1,234', '' 같은 표기를 안전하게 정수로."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text or set(text) <= {"*"}:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def as_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or set(text) <= {"*"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def norm_date(value) -> str:
    """2026-11-15 / 20261115 / 2026.11.15 → '20261115'."""
    if value is None:
        return ""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:8]


def norm_month(value) -> str:
    """2024-12 / 202412 / 2024.12 → '202412'. 8자리는 앞 6자리."""
    if value is None:
        return ""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]
