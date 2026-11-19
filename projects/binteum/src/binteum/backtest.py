"""백테스트 — "이 지수를 믿을 근거"를 숫자로 남긴다.

  ① 가중치 민감도: P_visit 가중치를 ±0.1 흔들어도 추천 상위권이 유지되는가
  ② 계절 기준선 단독 예측력: 전년 동월 데이터만으로 다음 해 순위를 맞힐 수 있는가(Spearman)
  ③ 요일유형 효과: 주말 방문인구가 평일보다 실제로 높은가(전 읍면동)

주의: 스냅샷이 합성 데이터(synthetic-demo)인 경우 이 수치는 **방법의 검증**이지
실제 제주 관광의 통계가 아니다. 리포트에 데이터 모드를 함께 출력한다.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Iterable

from . import config
from .data import DataPortal
from .index import CrowdIndexer, renormalize, weekday_type


def ranks(values: list[float]) -> list[float]:
    """동순위는 평균 순위로 처리."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            result[order[k]] = average
        i = j + 1
    return result


def spearman(xs: Iterable[float], ys: Iterable[float]) -> float | None:
    xs, ys = list(xs), list(ys)
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def top_overlap(ranking_a: list[str], ranking_b: list[str], k: int = 5) -> float:
    if not ranking_a or not ranking_b:
        return 0.0
    a = set(ranking_a[:k])
    b = set(ranking_b[:k])
    return round(len(a & b) / k, 2)


def weights_sensitivity(scores: dict, day: str) -> dict:
    base = config.CI_WEIGHTS
    variants = {}
    for delta in (-0.10, 0.10):
        weights = dict(base)
        weights["visit"] = max(0.05, base["visit"] + delta)
        # 남는 가중치는 다른 항에 비례 배분
        rest = 1.0 - weights["visit"]
        rest_base = 1.0 - base["visit"]
        for key in ("tour", "bus", "weather"):
            weights[key] = round(base[key] * rest / rest_base, 4)
        values = {}
        for spot_id, score in scores.items():
            ci, _, _ = renormalize(score.terms, weights)
            values[spot_id] = ci
        variants[delta] = values

    base_values = {spot_id: score.ci for spot_id, score in scores.items()}
    base_rank = [k for k, _ in sorted(base_values.items(), key=lambda kv: kv[1])]
    table = []
    for delta, values in variants.items():
        ranking = [k for k, _ in sorted(values.items(), key=lambda kv: kv[1])]
        rho = spearman([base_values[k] for k in base_values], [values[k] for k in base_values])
        table.append({
            "perturbation": f"P_visit 가중치 {base['visit']:+.2f} → {base['visit'] + delta:.2f}",
            "spearman_vs_base": rho,
            "top5_overlap": top_overlap(base_rank, ranking, 5),
        })
    return {"day": day, "rows": table}


def seasonal_rank_power(portal: DataPortal) -> dict:
    """전년 동월(최대 2년) 순위 → 다음 해 실제 순위의 Spearman."""
    series: dict[str, dict[str, int]] = {}
    for row in portal.datasets.get("tour").rows if portal.datasets.get("tour") else []:
        series.setdefault(row["name"], {})[row["month"]] = row["visitors"]
    if not series:
        return {"rows": [], "mean": None, "note": "591 데이터 없음"}

    months = sorted({m for s in series.values() for m in s})
    years = sorted({int(m[:4]) for m in months})
    rows = []
    for year in years[2:]:
        for month in ("01", "04", "07", "10"):
            target = f"{year}{month}"
            actual, predicted, names = [], [], []
            for name, s in series.items():
                if target not in s:
                    continue
                history = [s[f"{y}{month}"] for y in range(year - 2, year) if f"{y}{month}" in s]
                if not history:
                    continue
                names.append(name)
                actual.append(s[target])
                predicted.append(max(history))
            rho = spearman(predicted, actual)
            if rho is not None:
                rows.append({"year": year, "month": month, "spots": len(names), "spearman": rho})
    mean = round(sum(r["spearman"] for r in rows) / len(rows), 3) if rows else None
    return {"rows": rows, "mean": mean,
            "note": "전년 동월 최대값으로 다음 해 동월 순위를 예측했을 때의 순위 상관"}


def weekend_effect(portal: DataPortal) -> dict:
    ratios = []
    for emd in portal.emd_list():
        series = portal.visit_series(emd)
        weekend = [v for d, v in series.items() if weekday_type(d) == "weekend"]
        weekday = [v for d, v in series.items() if weekday_type(d) == "weekday"]
        if not weekend or not weekday:
            continue
        ratios.append(sum(weekend) / len(weekend) / (sum(weekday) / len(weekday)))
    if not ratios:
        return {"emds": 0, "median_ratio": None}
    ratios.sort()
    median = ratios[len(ratios) // 2]
    return {"emds": len(ratios), "median_ratio": round(median, 3),
            "share_higher": round(sum(1 for r in ratios if r > 1) / len(ratios), 2)}


def run(offline: bool = True, day: date | None = None) -> dict:
    portal = DataPortal(offline=offline)
    provenance = portal.load(today=day or date.today())
    indexer = CrowdIndexer(portal)
    scores = indexer.score_all(portal.reference_date)
    payload = {
        "generated_at": date.today().isoformat(),
        "data_mode": provenance.mode,
        "reference_date": portal.reference_date,
        "datasets": [d.to_dict() for d in provenance.datasets],
        "weights_sensitivity": weights_sensitivity(scores, portal.reference_date),
        "seasonal_rank": seasonal_rank_power(portal),
        "weekend_effect": weekend_effect(portal),
        "weights": config.CI_WEIGHTS,
        "spots_scored": len(scores),
    }
    return payload


def render_markdown(payload: dict) -> str:
    out = ["# 빈틈 백테스트 결과", ""]
    out.append(f"- 생성일: {payload['generated_at']}")
    out.append(f"- 데이터 모드: **{payload['data_mode']}** · 기준일 {payload['reference_date']} · "
               f"채점 관광지 {payload['spots_scored']}곳")
    out.append(f"- 기본 가중치: {payload['weights']}")
    modes = {d["dataset"]: d["mode"] for d in payload.get("datasets", [])}
    real = [k for k, v in modes.items() if v in ("live", "cache", "collected")]
    demo = [k for k, v in modes.items() if v == "snapshot"]
    if payload["data_mode"] != "live":
        if real and demo:
            out.append(f"- ⚠ 실측 수집분({', '.join(real)})과 합성 데모 스냅샷({', '.join(demo)})이 "
                       "섞인 결과입니다. ①·③의 유동인구 항은 실측, ②의 591은 합성 스냅샷 기준입니다.")
        else:
            out.append("- ⚠ 스냅샷 데이터 기준 결과입니다. `meta.source`가 synthetic-demo이면 "
                       "합성 데이터이며, 아래 수치는 **방법 검증용**입니다.")
    out.append("")
    out.append("## ① 가중치 민감도 (P_visit ±0.10)")
    out.append("")
    out.append("| 흔들기 | Spearman(순위 상관) | 상위 5곳 일치율 |")
    out.append("|---|---|---|")
    for row in payload["weights_sensitivity"]["rows"]:
        out.append(f"| {row['perturbation']} | {row['spearman_vs_base']} | {row['top5_overlap']} |")
    out.append("")
    out.append("## ② 계절 기준선 단독 예측력 (591)")
    out.append("")
    out.append(f"- 평균 Spearman: **{payload['seasonal_rank']['mean']}** "
               f"({payload['seasonal_rank']['note']})")
    if payload["seasonal_rank"]["rows"]:
        out.append("")
        out.append("| 연도 | 월 | 관광지 수 | Spearman |")
        out.append("|---|---|---|---|")
        for row in payload["seasonal_rank"]["rows"]:
            out.append(f"| {row['year']} | {row['month']} | {row['spots']} | {row['spearman']} |")
    out.append("")
    out.append("## ③ 요일유형 효과 (583)")
    out.append("")
    we = payload["weekend_effect"]
    out.append(f"- 대상 읍면동 {we['emds']}개 · 주말/평일 방문인구 중앙 비율 "
               f"**{we['median_ratio']}** · 주말이 더 높은 읍면동 비율 {we['share_higher']}")
    return "\n".join(out)


def save(payload: dict) -> dict:
    folder = config.OUT_DIR / "backtest"
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / "backtest.json"
    md_path = folder / "backtest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}
