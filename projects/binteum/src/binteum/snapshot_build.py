"""데모 스냅샷 생성기 — 허브 스키마를 그대로 따르는 **합성(synthetic) 데이터**.

왜 합성인가: 이 개발 환경은 제주데이터허브가 WAF로 차단되어(실측 403) 실데이터를
받을 수 없고, 대회 예시 xlsx는 시트당 1행·수치 마스킹(***)이라 시계열이 없다.
그래서 스키마·결측·요일효과·계절곡선을 재현한 합성 스냅샷을 동봉해
**평가자 환경에서 네트워크·키 없이 100% 재현**되게 한다.

정직성 원칙:
* 모든 파일의 meta.source = "synthetic-demo" 이고, 화면·리포트·기획서에 그대로 표시된다.
* 인증키를 받은 뒤 `python -m binteum fetch` 를 실행하면 data/snapshot/live/ 에
  실제 수집분이 저장되고, 로더가 그것을 우선 사용한다(코드 변경 없음).
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from .catalog import spots

SEED = 20261116
NOTE = ("합성 데모 데이터. 실제 측정값이 아니며 스키마·결측·요일효과·계절곡선을 재현해 "
        "파이프라인과 화면을 검증하기 위한 것입니다. 통계 인용 금지.")

OBSERVATORIES = (
    ("제주", 33.5141, 126.5297),
    ("성산", 33.3850, 126.8800),
    ("서귀포", 33.2461, 126.5653),
    ("고산", 33.2936, 126.1628),
)

# 관광지 인지도 사전(합성 prior). 값이 클수록 방문객이 많다고 가정한다.
POPULARITY = {
    "seongsan-ilchulbong": 1.00, "seopjikoji": 0.72, "udo": 0.78, "manjanggul": 0.80,
    "bijarim": 0.55, "gimnyeong-beach": 0.52, "hamdeok-beach": 0.86, "dongmun-market": 0.90,
    "jeju-mokgwana": 0.45, "yongduam": 0.70, "jeju-national-museum": 0.48, "sarabong": 0.35,
    "handam-beach": 0.84, "hyeopjae-beach": 0.88, "geumneung-beach": 0.60, "hallim-park": 0.70,
    "osulloc": 0.82, "sanbangsan": 0.68, "songaksan": 0.58, "moseulpo-harbor": 0.40,
    "jungmun-beach": 0.85, "jusangjeolli": 0.83, "yeomiji": 0.66, "cheonjiyeon": 0.80,
    "jeongbang": 0.55, "olle-market": 0.62, "lee-jungseop-street": 0.50, "soesokkak": 0.65,
    "camelliahill": 0.60, "sangumburi": 0.58, "saryeoni": 0.72, "seongeup": 0.60,
    "pyoseon-beach": 0.48, "keuneong": 0.28, "darangshi": 0.35, "yongnuni": 0.42,
    "saebyeol": 0.66, "geumo": 0.30, "aerospace-museum": 0.55, "provincial-art-museum": 0.40,
    "shinhwa-world": 0.75, "heukdwaeji-street": 0.68, "samyang-beach": 0.45,
    "iho-beach": 0.60, "dodubong": 0.42, "dolculture-park": 0.38, "aquaplanet": 0.74,
    "haenyeo-museum": 0.40, "sehwa-beach": 0.45, "ecoland": 0.62, "snoopy-garden": 0.64,
    "nexon-museum": 0.36, "oedolgae": 0.50, "chilsipri-beach": 0.38, "seowoo-bong": 0.32,
    "yongmeori": 0.58, "ttarabi": 0.26, "gimnyeong-maze": 0.34,
}

SEASON = {1: 0.72, 2: 0.70, 3: 0.82, 4: 0.95, 5: 1.00, 6: 0.98, 7: 1.12, 8: 1.15,
          9: 0.92, 10: 0.95, 11: 0.88, 12: 0.80}
WEEKDAY_FACTOR = {0: 1.00, 1: 1.00, 2: 1.02, 3: 1.03, 4: 1.15, 5: 1.32, 6: 1.28}


def popularity(spot_id: str, rng: random.Random) -> float:
    if spot_id in POPULARITY:
        return POPULARITY[spot_id]
    return round(rng.uniform(0.25, 0.6), 2)


def build(dest: Path | None = None, ref_day: date | None = None, seed: int = SEED,
          days: int = config.BASELINE_WEEKS * 7 + 1) -> dict:
    dest = Path(dest or config.SNAPSHOT_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    ref = ref_day or date.today()
    rng = random.Random(seed)
    catalogue = spots()

    emd_weights: dict[str, float] = {}
    emd_city: dict[str, str] = {}
    spot_pop = {}
    for spot in catalogue:
        pop = popularity(spot.id, rng)
        spot_pop[spot.id] = pop
        emd_weights[spot.emd] = emd_weights.get(spot.emd, 0.0) + pop
        emd_city.setdefault(spot.emd, spot.city)
    max_emd = max(emd_weights.values())
    emd_scale = {emd: 0.35 + 0.65 * value / max_emd for emd, value in emd_weights.items()}

    day_list = [ref - timedelta(days=days - 1 - i) for i in range(days)]
    written: dict[str, dict] = {}

    # ---------------------------------------------------------------- 583 유동인구
    flow_rows = []
    for emd, scale in emd_scale.items():
        base = 4200 + 26000 * scale
        for day in day_list:
            factor = WEEKDAY_FACTOR[day.weekday()] * SEASON[day.month]
            noise = math.exp(rng.gauss(0, 0.10))
            visit = int(base * factor * noise)
            resd = int(base * 0.62 * math.exp(rng.gauss(0, 0.05)))
            work = int(base * 0.30 * math.exp(rng.gauss(0, 0.06)))
            flow_rows.append({
                "baseDate": day.strftime("%Y%m%d"), "city": emd_city.get(emd, ""), "emd": emd,
                "gender": "전체", "ageGroup": "계",
                "resdPop": resd, "workPop": work, "visitPop": visit,
            })
    written["flow"] = _write(dest, "flow", flow_rows, {
        "hub_id": config.DATASET_IDS["flow"],
        "schema": "baseDate, city, emd, gender, ageGroup, resdPop, workPop, visitPop",
        "aggregation": "성·연령은 '전체/계'로 합산해 저장(파일 크기 절감, 스키마 유지)",
        "range": [day_list[0].strftime("%Y%m%d"), day_list[-1].strftime("%Y%m%d")],
    })

    # ---------------------------------------------------------------- 591 관광지 유입
    tour_rows = []
    months = [f"{year}{month:02d}" for year in (2022, 2023, 2024) for month in range(1, 13)]
    for spot in catalogue:
        pop = spot_pop[spot.id]
        base = 4000 + 260000 * pop
        trend = 1.0 + 0.03 * rng.gauss(0, 1)
        for month in months:
            m = int(month[4:])
            factor = SEASON[m] * trend * math.exp(rng.gauss(0, 0.07))
            visitors = int(base * factor / 30.0 * (1.0 if spot.category != "실내문화" else 0.9))
            tour_rows.append({"date": month, "name": spot.name,
                              "payType": "무료" if spot.cost_krw == 0 else "유료",
                              "visitors": visitors})
    written["tour"] = _write(dest, "tour", tour_rows, {
        "hub_id": config.DATASET_IDS["tour"],
        "schema": "date(YYYYMM), name, payType, visitors",
        "range": [months[0], months[-1]],
        "limitation": "591의 실제 최종 기준월은 2024-12(수집기간 종료). 월 단위이므로 "
                      "'오늘의 입장객'을 뜻하지 않는다.",
    })

    # ---------------------------------------------------------------- 614 노선별 버스
    route_names = sorted({r for spot in catalogue for r in spot.near_routes})
    route_base = {route: 900 + 2600 * (0.3 + 0.7 * rng.random()) for route in route_names}
    bus_rows = []
    for route in route_names:
        for day in day_list:
            factor = WEEKDAY_FACTOR[day.weekday()] * SEASON[day.month]
            boarding = int(route_base[route] * factor * math.exp(rng.gauss(0, 0.11)))
            bus_rows.append({"baseDate": day.strftime("%Y%m%d"), "routeName": route,
                             "routeSubName": "", "moveType": "승차", "priceType": "일반",
                             "payType": "교통카드", "userCount": boarding})
    written["bus"] = _write(dest, "bus", bus_rows, {
        "hub_id": config.DATASET_IDS["bus"],
        "schema": "baseDate, routeName, routeSubName, moveType, priceType, payType, userCount",
        "routes": len(route_names),
        "limitation": "614 API는 게시판에 502 신고가 있는 데이터. 결측 시 P_bus 가중치 자동 재정규화.",
    })

    # ---------------------------------------------------------------- 579 날씨 (+578 좌표)
    weather_rows = []
    for day in day_list:
        month_season = 13.5 - 9.0 * math.cos((int(day.strftime("%m")) - 8) / 12 * 2 * math.pi)
        for name, lat, lon in OBSERVATORIES:
            rain = 0.0
            wind = round(abs(rng.gauss(3.4, 1.4)), 1)
            # 기준일에는 악천후 1일을 넣어 실내/야외 가중 로직이 화면에 보이게 한다(합성).
            if day == ref:
                rain = 6.2 if name in ("제주", "성산") else 2.4
                wind = 11.5
            elif rng.random() < 0.12:
                rain = round(abs(rng.gauss(7.0, 4.0)), 1)
                wind = round(wind + 4.0, 1)
            avg = round(month_season + rng.gauss(0, 1.3), 1)
            weather_rows.append({
                "observatoryName": name, "baseDate": day.strftime("%Y%m%d"),
                "averageTemperature": avg,
                "lowestTemperature": round(avg - 3.2, 1),
                "highestTemperature": round(avg + 3.4, 1),
                "dailyRainfall": rain, "maximumWindSpeed": wind,
                "averageWindSpeed": round(wind * 0.45, 1),
                "latitude": lat, "longitude": lon,
            })
    written["weather"] = _write(dest, "weather", weather_rows, {
        "hub_id": config.DATASET_IDS["weather"],
        "schema": "observatoryName, baseDate, average/lowest/highestTemperature, "
                  "dailyRainfall, maximumWindSpeed, averageWindSpeed (+578 좌표 결합)",
        "observatories": [name for name, _, _ in OBSERVATORIES],
        "event": f"기준일 {ref.strftime('%Y-%m-%d')} 악천후(강수 6.2mm·최대풍속 11.5m/s)를 합성으로 배치",
    })

    # ---------------------------------------------------------------- 618 와이파이 AP
    wifi_rows = []
    categories = ("관광지", "해변", "시장", "터미널", "공항", "행정복지센터", "문화시설")
    for index, spot in enumerate(catalogue):
        for k in range(1):
            wifi_rows.append({
                "base_date": day_list[-1].strftime("%Y%m%d"),
                "mac_address": f"00:1A:{index:02X}:{rng.randrange(256):02X}:{rng.randrange(256):02X}:01",
                "ap_group_name": f"{spot.emd}-{index:02d}",
                "install_location_detail": f"{spot.name} 안내소",
                "category": "관광지" if spot.category != "시장" else "시장",
                "category_detail": spot.category,
                "address_dong": spot.emd,
                "address_detail": f"{spot.city} {spot.emd}",
                "latitude": round(spot.lat + rng.uniform(-0.002, 0.002), 6),
                "longitude": round(spot.lon + rng.uniform(-0.002, 0.002), 6),
            })
    for extra in (("제주국제공항", 33.5104, 126.4914), ("제주버스터미널", 33.4996, 126.5312)):
        wifi_rows.append({
            "base_date": day_list[-1].strftime("%Y%m%d"),
            "mac_address": f"00:1A:{rng.randrange(256):02X}:{rng.randrange(256):02X}:00:01",
            "ap_group_name": extra[0], "install_location_detail": f"{extra[0]} 대합실",
            "category": "공항" if "공항" in extra[0] else "터미널",
            "category_detail": categories[3], "address_dong": "",
            "address_detail": "제주특별자치도", "latitude": extra[1], "longitude": extra[2],
        })
    written["wifi"] = _write(dest, "wifi", wifi_rows, {
        "hub_id": config.DATASET_IDS["wifi"],
        "schema": "base_date, mac_address, ap_group_name, install_location_detail, category, "
                  "category_detail, address_dong, address_detail, latitude, longitude",
        "use": "대안 스팟 후보 풀·체류 거점 좌표(이번 MVP에서는 카탈로그 보조로만 사용)",
    })

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "synthetic-demo",
        "seed": seed,
        "reference_date": ref.strftime("%Y%m%d"),
        "note": NOTE,
        "datasets": {name: {"file": f"{name}.json", **info} for name, info in written.items()},
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return manifest


def _write(dest: Path, name: str, rows: list[dict], extra: dict) -> dict:
    meta = {"source": "synthetic-demo", "note": NOTE,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rows": len(rows), "path": f"data/snapshot/{name}.json", **extra}
    (dest / f"{name}.json").write_text(
        json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    return {k: v for k, v in meta.items() if k not in ("note", "generated_at", "path")}
