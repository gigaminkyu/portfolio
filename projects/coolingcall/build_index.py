"""쿨링콜 ETL: 원천 3종을 행정동 단위로 결합하고 폭염 위험지수를 계산한다.

원천
1) data/kma_asos_daegu_daily.csv              기상청 기상자료개방포털, 대구(지점143) 일별 최저/평균/최고기온 2015~2025
2) data/raw/무더위쉼터현황표.xlsx               대구광역시 자연재난과, 무더위쉼터 현황(2026)
3) data/raw/행안부_대구_읍면동_연령별인구_2026-10.xlsx
                                              행정안전부 주민등록 인구통계, 행정동별 성별·연령별 인구(2026.10)

출력
- data/processed/dong_index.csv   동 단위 지표 + 위험지수
- data/processed/meta.json        시 단위 폭염 통계, 산출 파라미터
- dashboard/data.js               대시보드가 읽는 동일 결과(정적 JSON)
"""
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
D = HERE / "data"
OUT = D / "processed"

# ---- 지수 파라미터 (제안서에 그대로 기재) -------------------------------------
CAP_FULL_PER_1000 = 300.0   # 고령자 1,000명당 냉방쉼터 수용인원이 300석이면 대응 충분(1.0)
W_HEAT, W_VULN, W_GAP = 0.30, 0.40, 0.30
HEAT_DAY_TMAX = 33.0        # 폭염일: 일최고기온 33℃ 이상 (기상청 기준)
TROPICAL_NIGHT_TMIN = 25.0  # 열대야: 일최저기온 25℃ 이상


def load_kma():
    rows = []
    with (D / "kma_asos_daegu_daily.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            def num(v):
                try:
                    return float(v) if v not in (None, "") else None
                except ValueError:
                    return None
            rows.append(
                {
                    "date": r["date"],
                    "avg": num(r["avg_ta"]),
                    "max": num(r["max_ta"]),
                    "min": num(r["min_ta"]),
                }
            )
    return rows


def heat_season_stats(rows):
    """연도별 폭염일수·열대야일수·연 최고기온."""
    by_year = defaultdict(lambda: {"heat_days": 0, "tropical_nights": 0, "max_ta": None})
    for r in rows:
        y = r["date"][:4]
        if r["max"] is not None and r["max"] >= HEAT_DAY_TMAX:
            by_year[y]["heat_days"] += 1
        if r["min"] is not None and r["min"] >= TROPICAL_NIGHT_TMIN:
            by_year[y]["tropical_nights"] += 1
        if r["max"] is not None:
            cur = by_year[y]["max_ta"]
            by_year[y]["max_ta"] = r["max"] if cur is None else max(cur, r["max"])
    return dict(sorted(by_year.items()))


def norm(value, series):
    lo, hi = min(series), max(series)
    if hi == lo:
        return 0.5
    return (value - lo) / (hi - lo)


# 대구시 쉼터자료와 행안부 인구자료의 행정동 표기 차이를 맞춘다.
DONG_ALIAS = {"구지면": "구지읍"}
BRANCH_PARENT = {"논공읍공단출장소": "논공읍", "다사읍서재출장소": "다사읍"}


def canon_dong(name: str) -> str:
    name = (name or "").strip()
    name = BRANCH_PARENT.get(name, name)
    return DONG_ALIAS.get(name, name)


def load_shelters():
    wb = openpyxl.load_workbook(D / "raw" / "무더위쉼터현황표.xlsx", data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[2]
    out = []
    for r in rows[4:]:
        if not r or r[0] in (None, "") or str(r[1]) not in ("대구광역시", "대구시"):
            continue
        gu = (r[2] or "").strip()
        dong = (r[6] or "").strip()
        if not gu or not dong:
            continue
        name = (r[3] or "").strip()

        def num(v):
            try:
                return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
            except ValueError:
                return 0.0

        fans, ac = num(r[25]), num(r[26])
        cap = num(r[12])
        op_status = (r[4] or "").strip()

        # 운영 종료시각(기본/연장/추가운영 중 가장 늦은 값)
        end_times = []
        for col in (16, 20, 24):
            v = r[col] if col < len(r) else None
            if v not in (None, ""):
                s = str(v).strip().zfill(4)
                if s.isdigit() and len(s) == 4:
                    end_times.append(int(s[:2]) * 60 + int(s[2:]))
        last_end = max(end_times) if end_times else None
        day_text = "".join(str(r[c]) for c in (14, 18, 22) if c < len(r) and r[c])
        weekend = ("토" in day_text) or ("일" in day_text)

        lat = num(r[37]) if len(r) > 37 else 0.0
        lon = num(r[36]) if len(r) > 36 else 0.0
        out.append(
            {
                "gu": gu,
                "dong": canon_dong(dong),
                "name": name,
                "op": op_status,
                "ac": ac,
                "fans": fans,
                "cap": cap,
                "last_end": last_end,
                "weekend": bool(weekend),
                "lat": lat if lat > 30 else None,
                "lon": lon if lon > 120 else None,
                "type": (r[9] or "").strip(),
            }
        )
    return out


def load_population():
    wb = openpyxl.load_workbook(D / "raw" / "행안부_대구_읍면동_연령별인구_2026-10.xlsx", data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[3]
    idx = {str(h).strip(): i for i, h in enumerate(header) if h}
    out = {}
    for r in rows[4:]:
        name = str(r[1] or "").strip()
        if not name.startswith("대구광역시"):
            continue
        parts = name.split()
        if len(parts) < 3:
            continue  # 구 단위 행 제외
        gu, dong = parts[1], canon_dong(" ".join(parts[2:]))

        def num(label):
            v = r[idx[label]]
            try:
                return float(str(v).replace(",", ""))
            except (ValueError, TypeError):
                return 0.0

        total = num("총 인구수")
        e65 = sum(
            num(c)
            for c in idx
            if c.endswith("세") and "~" in c and int(c.split("~")[0].replace("세", "")) >= 65 and "-" not in c[:2] or False
        )
        # 위 식은 컬럼명이 '65~69세' 형태이므로 아래에서 다시 계산한다.
        e65 = 0.0
        for c, i in idx.items():
            if "~" in c and c.endswith("세"):
                start = c.split("~")[0]
                if start.isdigit() and int(start) >= 65:
                    try:
                        e65 += float(str(r[i]).replace(",", ""))
                    except (TypeError, ValueError):
                        pass
            if c == "100세 이상":
                try:
                    e65 += float(str(r[i]).replace(",", ""))
                except (TypeError, ValueError):
                    pass
        e75 = 0.0
        for c, i in idx.items():
            if "~" in c and c.endswith("세"):
                start = c.split("~")[0]
                if start.isdigit() and int(start) >= 75:
                    try:
                        e75 += float(str(r[i]).replace(",", ""))
                    except (TypeError, ValueError):
                        pass
            if c == "100세 이상":
                try:
                    e75 += float(str(r[i]).replace(",", ""))
                except (TypeError, ValueError):
                    pass
        out[(gu, dong)] = {"total": total, "e65": e65, "e75": e75, "code": r[0]}
    return out


def pct_rank(values):
    """값 목록을 0~100 백분위 순위로 변환."""
    s = sorted(values)
    n = len(s)
    ranks = {}
    for v in set(s):
        # 평균 순위
        lo = s.index(v)
        hi = n - 1 - s[::-1].index(v)
        ranks[v] = (lo + hi) / 2 / (n - 1) * 100 if n > 1 else 50.0
    return {v: ranks[v] for v in values}


def main() -> None:
    kma = load_kma()
    yearly = heat_season_stats(kma)
    seasons = [v for y, v in yearly.items() if y != "2025"]
    cur = yearly["2025"]

    heat_norm = (
        0.5 * norm(cur["heat_days"], [v["heat_days"] for v in seasons] + [cur["heat_days"]])
        + 0.3 * norm(cur["tropical_nights"], [v["tropical_nights"] for v in seasons] + [cur["tropical_nights"]])
        + 0.2 * norm(cur["max_ta"], [v["max_ta"] for v in seasons] + [cur["max_ta"]])
    )
    heat_score = round(heat_norm * 100, 1)

    shelters = load_shelters()
    pop = load_population()

    agg = defaultdict(
        lambda: {
            "n": 0,
            "n_cool": 0,
            "cap_cool": 0.0,
            "cap_night": 0.0,
            "n_night": 0,
            "n_weekend": 0,
        }
    )
    for s in shelters:
        if s["op"] not in ("운영", ""):
            continue
        a = agg[(s["gu"], s["dong"])]
        a["n"] += 1
        cooling = s["ac"] > 0
        if cooling:
            a["n_cool"] += 1
            a["cap_cool"] += s["cap"]
            if s["last_end"] is not None and s["last_end"] >= 20 * 60:
                a["n_night"] += 1
                a["cap_night"] += s["cap"]
            if s["weekend"]:
                a["n_weekend"] += 1

    keys = sorted(set(pop) | set(agg))
    e65_series = [pop[k]["e65"] for k in keys if k in pop]
    rate_series = [pop[k]["e65"] / pop[k]["total"] for k in keys if k in pop and pop[k]["total"] > 0]
    e75_series = [pop[k]["e75"] / pop[k]["total"] for k in keys if k in pop and pop[k]["total"] > 0]

    rk_e65 = pct_rank(e65_series)
    rk_rate = pct_rank(rate_series)
    rk_e75 = pct_rank(e75_series)

    rows = []
    for k in keys:
        gu, dong = k
        p = pop.get(k)
        a = agg.get(k, {"n": 0, "n_cool": 0, "cap_cool": 0.0, "cap_night": 0.0, "n_night": 0, "n_weekend": 0})
        if p:
            vuln = 0.45 * rk_e65[p["e65"]] + 0.35 * rk_rate[p["e65"] / p["total"] if p["total"] else 0] + 0.20 * rk_e75[
                p["e75"] / p["total"] if p["total"] else 0
            ]
        else:
            vuln = 60.0  # 인구자료 없음(군위군 등) → 중립값
        cap_day = a["cap_cool"] / (p["e65"] / 1000) if p and p["e65"] else 0.0
        cap_night = a["cap_night"] / (p["e65"] / 1000) if p and p["e65"] else 0.0
        gap_day = 100 * (1 - min(cap_day / CAP_FULL_PER_1000, 1))
        gap_night = 100 * (1 - min(cap_night / CAP_FULL_PER_1000, 1))
        risk_day = W_HEAT * heat_score + W_VULN * vuln + W_GAP * gap_day
        risk_night = W_HEAT * heat_score + W_VULN * vuln + W_GAP * gap_night
        rows.append(
            {
                "gu": gu,
                "dong": dong,
                "pop": int(p["total"]) if p else None,
                "e65": int(p["e65"]) if p else None,
                "e75": int(p["e75"]) if p else None,
                "e65_rate": round(p["e65"] / p["total"] * 100, 1) if p and p["total"] else None,
                "n_shelter": a["n"],
                "n_cool": a["n_cool"],
                "cap_cool": int(a["cap_cool"]),
                "n_night": a["n_night"],
                "cap_night": int(a["cap_night"]),
                "n_weekend": a["n_weekend"],
                "cap_per_1000": round(cap_day, 1),
                "cap_night_per_1000": round(cap_night, 1),
                "vuln": round(vuln, 1),
                "gap_day": round(gap_day, 1),
                "gap_night": round(gap_night, 1),
                "risk_day": round(risk_day, 1),
                "risk_night": round(risk_night, 1),
            }
        )

    rows.sort(key=lambda r: -r["risk_day"])
    for i, r in enumerate(rows, 1):
        r["rank_day"] = i
    night_sorted = sorted(rows, key=lambda r: -r["risk_night"])
    for i, r in enumerate(night_sorted, 1):
        r["rank_night"] = i

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "dong_index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    meta = {
        "generated_from": {
            "kma": "기상청 기상자료개방포털 기후통계분석 기온분석(지점 143 대구), 2015-01-01~2025-12-31",
            "shelter": "대구광역시 자연재난과 무더위쉼터 현황표(2026)",
            "population": "행정안전부 주민등록 인구통계 행정동별 연령별 인구(2026년 10월)",
        },
        "heat": {
            "year": 2025,
            "heat_days": cur["heat_days"],
            "tropical_nights": cur["tropical_nights"],
            "max_ta": cur["max_ta"],
            "score": heat_score,
            "series": yearly,
        },
        "params": {
            "cap_full_per_1000": CAP_FULL_PER_1000,
            "weights": {"heat": W_HEAT, "vuln": W_VULN, "gap": W_GAP},
            "heat_day_tmax": HEAT_DAY_TMAX,
            "tropical_night_tmin": TROPICAL_NIGHT_TMIN,
        },
        "counts": {
            "shelters_raw": len(shelters),
            "shelters_used": sum(a["n"] for a in agg.values()),
            "dongs": len(rows),
            "dongs_with_pop": len(pop),
        },
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "dashboard").mkdir(exist_ok=True)
    (HERE / "dashboard" / "data.json").write_text(
        json.dumps({"meta": meta, "dongs": rows, "shelters": shelters}, ensure_ascii=False),
        encoding="utf-8",
    )

    print("dong rows:", len(rows))
    print("heat:", cur, "score", heat_score)
    print("shelters used:", meta["counts"]["shelters_used"], "of", len(shelters))
    unmatched = [(k[0], k[1]) for k in keys if k not in pop]
    print("dongs without population:", unmatched[:10], len(unmatched))
    for r in rows[:10]:
        print(
            f"{r['rank_day']:2d} {r['gu']} {r['dong']:<8} risk={r['risk_day']:.1f} vuln={r['vuln']:.0f} "
            f"gap={r['gap_day']:.0f} e65={r['e65']} rate={r['e65_rate']} cap/k={r['cap_per_1000']}"
        )


if __name__ == "__main__":
    main()
