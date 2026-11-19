"""Reporter — 결과를 사람이 읽는 형태로 정리한다(카드 문장·공유 텍스트·HTML 리포트).

수치는 전부 파이프라인이 계산한 값을 인용한다. LLM은 문장만 다듬고,
숫자 가드(모든 숫자가 근거 JSON에 존재)를 통과해야 채택된다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .catalog import emds as catalog_emds
from .catalog import spots as catalog_spots
from .llm import LLMClient, collect_numbers


# ------------------------------------------------------------------ 문장 보강
def enrich(payload: dict, llm: LLMClient | None = None, trace=None) -> dict:
    payload["share_text"] = share_text(payload)
    payload["summary"]["narrative"] = _template_narrative(payload)

    if llm is not None and llm.available and payload.get("plans"):
        plan = _best_plan(payload)
        if plan:
            prompt = _narrative_prompt(payload, plan)
            allowed = collect_numbers({
                "plans": payload["plans"], "constraints": payload["constraints"],
                "data": payload["data"],
            })
            result = llm.complete(prompt, allowed_numbers=allowed)
            if result.ok and result.text:
                payload["summary"]["narrative"] = result.text.strip()
                payload["summary"]["narrative_source"] = f"llm:{llm.provider}"
            else:
                payload["summary"]["narrative_source"] = "template"
                payload["summary"]["narrative_error"] = result.error
    return payload


def _best_plan(payload: dict) -> dict | None:
    best = payload.get("summary", {}).get("best_plan")
    for plan in payload.get("plans", []):
        if plan["key"] == best and plan.get("stops"):
            return plan
    for plan in payload.get("plans", []):
        if plan.get("stops"):
            return plan
    return None


def _narrative_prompt(payload: dict, plan: dict) -> str:
    facts = {
        "current_location": payload["constraints"].get("origin_emd"),
        "end_time": payload["constraints"].get("end_time"),
        "party": payload["constraints"].get("party"),
        "plan_label": plan["label"],
        "stops": [{"name": s["spot_name"], "ci": s["ci"], "label": s["ci_label"],
                   "arrive": s["arrive"], "travel_min": s["travel_min"],
                   "terms": s["evidence"].get("terms")} for s in plan["stops"]],
        "avg_ci": plan["totals"]["avg_ci"],
        "travel_min": plan["totals"]["travel_min"],
    }
    return ("아래 사실만으로 이 동선을 추천하는 이유를 3문장 이내로 쓰세요. "
            "숫자는 facts 안의 값만 그대로 인용하고, 없는 숫자는 쓰지 마세요.\n"
            + json.dumps(facts, ensure_ascii=False))


def _template_narrative(payload: dict) -> str:
    plan = _best_plan(payload)
    if not plan:
        return "조건을 만족하는 동선을 만들지 못했습니다."
    c = payload["constraints"]
    first = plan["stops"][0]
    parts = [
        f"{c.get('origin_emd') or '현재 위치'}에서 출발해 {len(plan['stops'])}곳을 도는 동선입니다.",
        f"첫 후보인 {first['spot_name']}의 혼잡지수는 {first['ci']}({first['ci_label']})이며, "
        f"읍면동 방문인구 백분위와 계절 기준선, 노선 수요를 가중 합산한 값입니다.",
        f"총 이동 {plan['totals']['travel_min']}분, 평균 CI {plan['totals']['avg_ci']}입니다.",
    ]
    if payload.get("data", {}).get("mode") in ("snapshot", "mixed"):
        parts.append("데이터 모드가 스냅샷이므로 화면의 기준일을 확인하세요.")
    return " ".join(parts)


# ------------------------------------------------------------------ 공유 텍스트
def share_text(payload: dict) -> str:
    c = payload.get("constraints", {})
    plan = _best_plan(payload)
    if not plan:
        return "[빈틈] 조건을 만족하는 동선을 만들지 못했습니다."
    lines = [f"[빈틈] {c.get('origin_emd', '')} · {c.get('end_time', '')} 까지 · {plan['label']}"]
    for stop in plan["stops"]:
        lines.append(f"{stop['order']}. {stop['arrive']} {stop['spot_name']} — "
                     f"CI {stop['ci']}({stop['ci_label']}), {stop['dwell_min']}분")
    lines.append(f"이동 {plan['totals']['travel_min']}분 · 평균 CI {plan['totals']['avg_ci']}")
    datasets = payload.get("data", {}).get("datasets", [])
    if datasets:
        lines.append("근거: " + ", ".join(f"허브 {d['hub_id']}({d['mode']})" for d in datasets))
    return "\n".join(lines)


# ------------------------------------------------------------------ 마크다운
def render_markdown(payload: dict) -> str:
    c = payload.get("constraints", {})
    out = [f"# 빈틈(BinTeum) 실행 결과 — {payload.get('run_id', '')}", ""]
    out.append(f"- 생성: {payload.get('generated_at', '')} / 응답 {payload.get('elapsed_ms', 0)}ms")
    out.append(f"- 입력: {c.get('raw_query') or '(구조화 입력)'}")
    out.append(f"- 제약: 위치 {c.get('origin_emd')}, 종료 {c.get('end_time')}, 동행 {c.get('party')}, "
               f"이동 {c.get('mobility')}, 실내 {c.get('indoor_required')}, 예산 {c.get('budget_krw')}")
    data = payload.get("data", {})
    out.append(f"- 데이터 모드: **{data.get('mode')}** (기준일 {data.get('today')})")
    for d in data.get("datasets", []):
        out.append(f"  - id={d['hub_id']} {d['dataset']}: {d['mode']}, {d['rows']}행, {d['source_note']}")
    out.append("")
    for plan in payload.get("plans", []):
        out.append(f"## {plan['label']}")
        out.append(f"{plan['headline']}")
        out.append("")
        out.append("| # | 시각 | 장소 | CI | 체류 | 이동 | 비용 |")
        out.append("|---|---|---|---|---|---|---|")
        for s in plan["stops"]:
            out.append(f"| {s['order']} | {s['arrive']}~{s['depart']} | {s['spot_name']} | "
                       f"{s['ci']} ({s['ci_label']}) | {s['dwell_min']}분 | {s['travel_min']}분 | "
                       f"{s['cost_krw']:,}원 |")
        out.append("")
        out.append(f"- 합계: 이동 {plan['totals']['travel_min']}분 · 거리 {plan['totals']['distance_km']}km · "
                   f"비용 {plan['totals']['cost_krw']:,}원 · 평균 CI {plan['totals']['avg_ci']}")
        out.append(f"- 근거: {plan['rationale']}")
        for w in plan.get("warnings", []):
            out.append(f"- ⚠ {w}")
        out.append("")
        out.append("<details><summary>정류장별 근거 문장</summary>")
        out.append("")
        for s in plan["stops"]:
            out.append(f"**{s['order']}. {s['spot_name']}**")
            for line in s["why"]:
                out.append(f"- {line}")
            out.append("")
        out.append("</details>")
        out.append("")
    critic = payload.get("critic", {})
    out.append("## Critic 검증")
    out.append("")
    for key, result in critic.items():
        state = "통과" if result["passed"] else "반려"
        out.append(f"- {key}: {state} (라운드 {result['rounds']})")
        for v in result["violations"]:
            out.append(f"  - {v['rule']} {v['spot_id']}: {v['message']}")
    out.append("")
    out.append("## 한계·유의")
    for note in payload.get("notes", []):
        out.append(f"- {note}")
    return "\n".join(out)


# ------------------------------------------------------------------ HTML
def render_html(payload: dict) -> str:
    """저장된 실행 결과를 그대로 여는 독립 HTML 리포트(서버·인터넷 불필요)."""
    index_html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (config.STATIC_DIR / "style.css").read_text(encoding="utf-8")
    js = (config.STATIC_DIR / "app.js").read_text(encoding="utf-8")

    meta = {
        "emds": catalog_emds(),
        "spots": [{"id": s.id, "name": s.name, "emd": s.emd, "lat": s.lat, "lon": s.lon,
                   "category": s.category, "indoor": s.indoor} for s in catalog_spots()],
        "data": payload.get("data"),
    }
    preset = json.dumps(payload, ensure_ascii=False, default=str).replace("</", "<\\/")
    meta_json = json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")

    banner = (
        '<div style="background:#fff8e6;border-bottom:1px solid #f0dfae;padding:8px 28px;'
        'font-size:12px;color:#8a6516">저장된 실행 결과 리포트(오프라인) — 입력 폼은 비활성입니다. '
        f'run_id {payload.get("run_id", "")}</div>'
    )
    html = index_html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
    html = html.replace("<body>", "<body>" + banner)
    html = html.replace(
        '<script src="app.js"></script>',
        f"<script>window.__BINTEUM_PRESET__={preset};window.__BINTEUM_META__={meta_json};</script>\n"
        f"<script>\n{js}\n</script>",
    )
    return html


def write_report_files(payload: dict) -> dict:
    config.ensure_dirs()
    run_id = payload.get("run_id") or "run"
    folder = config.OUT_DIR / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    html_path = folder / f"{run_id}.html"
    md_path = folder / f"{run_id}.md"
    html_path.write_text(render_html(payload), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"html": str(html_path), "md": str(md_path)}
