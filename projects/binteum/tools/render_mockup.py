"""기획서용 화면 목업 렌더러 (Pillow).

이 스크립트가 그리는 이미지는 브라우저 스크린샷이 아니라 **목업**이다.
같은 팔레트·레이아웃·실제 실행 데이터(out/runs/*.json)를 사용해 그린다.
실제 화면은 out/reports/<run_id>.html 을 브라우저로 열면 그대로 보인다.

사용: python3 tools/render_mockup.py out/runs/run-xxx.json
출력: docs/images/01_입력과_3안.png, docs/images/02_근거와_지도.png
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "NotoSansKR.ttf"
OUT = ROOT / "docs" / "images"

INK = (27, 36, 48)
INK_SOFT = (74, 87, 104)
MUTED = (138, 151, 168)
SAND = (246, 243, 236)
CARD = (255, 255, 255)
LINE = (228, 223, 211)
TEAL = (15, 125, 118)
TEAL_SOFT = (227, 242, 240)
AMBER = (196, 127, 23)
AMBER_SOFT = (253, 241, 221)
RED = (180, 68, 47)
GREEN = (46, 125, 79)
GREEN_SOFT = (230, 242, 234)

ISLAND = [
    (126.530, 33.515), (126.580, 33.525), (126.620, 33.532), (126.670, 33.545),
    (126.720, 33.552), (126.760, 33.550), (126.800, 33.540), (126.850, 33.532),
    (126.890, 33.510), (126.930, 33.480), (126.945, 33.455), (126.930, 33.415),
    (126.890, 33.375), (126.850, 33.345), (126.820, 33.320), (126.780, 33.300),
    (126.730, 33.270), (126.680, 33.255), (126.630, 33.248), (126.580, 33.240),
    (126.545, 33.236), (126.500, 33.235), (126.450, 33.232), (126.410, 33.238),
    (126.360, 33.225), (126.320, 33.215), (126.280, 33.212), (126.245, 33.213),
    (126.210, 33.225), (126.175, 33.250), (126.165, 33.290), (126.155, 33.330),
    (126.170, 33.360), (126.195, 33.390), (126.225, 33.415), (126.255, 33.440),
    (126.290, 33.462), (126.330, 33.470), (126.380, 33.480), (126.430, 33.495),
    (126.470, 33.505), (126.500, 33.512),
]
BOUNDS = {"lon0": 126.14, "lon1": 126.96, "lat0": 33.10, "lat1": 33.57}
VIEW = dict(BOUNDS)


def fit_view(coords):
    if not coords or len(coords) < 2:
        return dict(BOUNDS)
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    pad = 0.035
    lon0, lon1 = min(lons) - pad, max(lons) + pad
    lat0, lat1 = min(lats) - pad * 0.75, max(lats) + pad * 0.75
    if lon1 - lon0 < 0.14:
        cx = (lon0 + lon1) / 2
        lon0, lon1 = cx - 0.07, cx + 0.07
    if lat1 - lat0 < 0.09:
        cy = (lat0 + lat1) / 2
        lat0, lat1 = cy - 0.045, cy + 0.045
    return {"lon0": lon0, "lon1": lon1, "lat0": lat0, "lat1": lat1}


def font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def rrect(draw, box, radius=12, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text(draw, xy, s, f, fill=INK, anchor="la"):
    draw.text(xy, s, font=f, fill=fill, anchor=anchor)


def project(lon, lat, box, view=None):
    view = view or VIEW
    x0, y0, x1, y1 = box
    x = x0 + (lon - view["lon0"]) / (view["lon1"] - view["lon0"]) * (x1 - x0)
    y = y0 + (view["lat1"] - lat) / (view["lat1"] - view["lat0"]) * (y1 - y0)
    return x, y


def ci_color(ci: int):
    if ci >= 70:
        return RED
    if ci >= 45:
        return AMBER
    return GREEN


def header(draw, w, payload, meta_note="동봉 데모 스냅샷"):
    draw.rectangle([0, 0, w, 64], fill=CARD)
    draw.line([0, 64, w, 64], fill=LINE)
    text(draw, (28, 20), "빈틈", font(26, 800), TEAL)
    text(draw, (98, 28), "BinTeum", font(12, 500), MUTED)
    draw.line([190, 18, 190, 46], fill=LINE)
    text(draw, (204, 26), "제주 여행의 빈 시간을 찾아주는 실측 혼잡 회피 Agent",
         font(13), INK_SOFT)
    pill_w = 132
    rrect(draw, [w - 28 - pill_w, 20, w - 28, 44], 12, AMBER_SOFT)
    text(draw, (w - 28 - pill_w / 2, 32), meta_note, font(11, 700), AMBER, anchor="mm")
    text(draw, (w - 176, 26), f"기준일 {payload['data'].get('today', '')} · 합성 데모 데이터",
         font(11), MUTED, anchor="ra")


def left_panel(draw, payload, box):
    x, y, w, h = box
    rrect(draw, [x, y, x + w, y + h], 16, CARD, LINE)
    inner = x + 20
    text(draw, (inner, y + 18), "지금 상황을 한 줄로", font(12, 700), INK_SOFT)
    q = payload["constraints"].get("raw_query") or "성산인데 애 데리고 6시까지 실내 위주로"
    rrect(draw, [inner, y + 38, x + w - 20, y + 38 + 74], 10, (252, 251, 248), LINE)
    line1, line2 = q[:26], q[26:52]
    text(draw, (inner + 10, y + 50), line1, font(13))
    if line2:
        text(draw, (inner + 10, y + 70), line2, font(13))

    def field(cx, cy, cw, label, value, value_color=INK):
        text(draw, (cx, cy), label, font(12, 700), INK_SOFT)
        rrect(draw, [cx, cy + 19, cx + cw, cy + 19 + 32], 10, (252, 251, 248), LINE)
        text(draw, (cx + 10, cy + 28), value, font(13), value_color)

    cy = y + 128
    c = payload["constraints"]
    field(inner, cy, (w - 50) / 2, "현재 위치(읍면동)", c.get("origin_emd", "-"))
    field(inner + (w - 50) / 2 + 10, cy, (w - 50) / 2, "정확한 지점",
          "성산일출봉" if c.get("origin_spot") else "선택 안 함")
    cy += 70
    field(inner, cy, (w - 50) / 2, "종료(귀가) 시각", c.get("end_time", ""))
    party = {"solo": "혼자", "couple": "커플·부부", "family_kid": "아이 동반",
             "with_parents": "부모님", "friends": "일행"}.get(c.get("party"), "혼자")
    field(inner + (w - 50) / 2 + 10, cy, (w - 50) / 2, "동행", party)
    cy += 70
    field(inner, cy, (w - 50) / 2, "이동수단",
          {"car": "렌터카", "bus": "버스", "walk": "도보"}.get(c.get("mobility"), "렌터카"))
    field(inner + (w - 50) / 2 + 10, cy, (w - 50) / 2, "예산(원, 선택)",
          f"{c['budget_krw']:,}" if c.get("budget_krw") else "입력 없음", MUTED)

    cy += 64
    box_size = 14
    draw.rectangle([inner, cy + 2, inner + box_size, cy + 2 + box_size], outline=LINE,
                   fill=TEAL if c.get("indoor_required") else None)
    if c.get("indoor_required"):
        text(draw, (inner + 3, cy - 1), "v", font(11, 800), (255, 255, 255))
    text(draw, (inner + 22, cy), "실내 위주로(비·강풍 대비)", font(13), INK_SOFT)

    cy += 34
    text(draw, (inner, cy), "테마", font(12, 700), MUTED)
    cx = inner + 40
    for theme in (c.get("themes") or ["가족", "실내"])[:4]:
        wpx = 22 + len(theme) * 12
        rrect(draw, [cx, cy - 3, cx + wpx, cy + 21], 12, TEAL)
        text(draw, (cx + wpx / 2, cy + 9), theme, font(11, 700), (255, 255, 255), anchor="mm")
        cx += wpx + 6

    by = y + h - 92
    rrect(draw, [inner, by, x + w - 20, by + 42], 12, TEAL)
    text(draw, ((inner + x + w - 20) / 2, by + 21), "빈틈 찾기", font(15, 800),
         (255, 255, 255), anchor="mm")
    text(draw, (x + w / 2, by + 58), "추천까지만 합니다. 예약·결제·외부 전송은 하지 않습니다.",
         font(10.5), MUTED, anchor="ma")


def stat_row(draw, payload, box):
    x, y, w, _ = box
    s = payload["summary"]
    items = [("추천 동선", f"{s.get('stops', 0)}곳"), ("평균 혼잡지수", f"{s.get('avg_ci', '-')}"),
             ("총 이동", f"{s.get('travel_min', 0)}분"),
             ("Critic 반려", f"{s.get('critic_rounds', 0)}회"),
             ("응답", f"{payload.get('elapsed_ms', 0)}ms")]
    cx = x
    for label, value in items:
        cw = 116
        rrect(draw, [cx, y, cx + cw, y + 62], 14, CARD, LINE)
        text(draw, (cx + 14, y + 12), label, font(10.5, 700), MUTED)
        text(draw, (cx + 14, y + 30), value, font(20, 800))
        cx += cw + 10
    c = payload["constraints"]
    bx = cx
    rrect(draw, [bx, y, x + w, y + 62], 14, CARD, LINE)
    text(draw, (bx + 14, y + 10), "해석된 제약 (Router)", font(10.5, 700), MUTED)
    chips = [f"현재 {c.get('origin_emd')}", f"{c.get('end_time')}까지",
             {"family_kid": "아이 동반", "couple": "커플", "with_parents": "부모님",
              "solo": "혼자"}.get(c.get("party"), ""), "렌터카",
             "실내 위주" if c.get("indoor_required") else ""]
    cx2 = bx + 14
    for chip in [ch for ch in chips if ch]:
        wpx = 16 + len(chip) * 11
        rrect(draw, [cx2, y + 32, cx2 + wpx, y + 54], 10, (243, 240, 232))
        text(draw, (cx2 + wpx / 2, y + 43), chip, font(10.5), INK_SOFT, anchor="mm")
        cx2 += wpx + 5


def plan_card(draw, plan, box, best: bool):
    x, y, w, h = box
    rrect(draw, [x, y, x + w, y + h], 16, CARD, TEAL if best else LINE, 2 if best else 1)
    text(draw, (x + 14, y + 14), plan["label"], font(14, 800))
    if best:
        rrect(draw, [x + w - 54, y + 13, x + w - 14, y + 33], 10, TEAL)
        text(draw, (x + w - 34, y + 23), "추천", font(9.5, 800), (255, 255, 255), anchor="mm")
    text(draw, (x + 14, y + 36), plan["headline"], font(11), INK_SOFT)
    draw.line([x, y + 58, x + w, y + 58], fill=LINE)

    cy = y + 66
    for stop in plan["stops"]:
        sh = 74
        rrect(draw, [x + 10, cy, x + w - 10, cy + sh], 12, (252, 251, 248), (239, 234, 224))
        text(draw, (x + 20, cy + 8), f"{stop['order']}. {stop['spot_name']}", font(12.5, 700))
        text(draw, (x + 20, cy + 27),
             f"{stop['arrive']}~{stop['depart']} · {stop['dwell_min']}분 · "
             f"이동 {stop['travel_min']}분({stop['travel_km']}km)", font(10), MUTED)
        color = ci_color(stop["ci"])
        text(draw, (x + w - 24, cy + 6), f"{stop['ci']}", font(17, 800), color, anchor="ra")
        text(draw, (x + w - 24, cy + 26), stop["ci_label"], font(9.5, 800), color, anchor="ra")
        bar_x0, bar_x1 = x + 20, x + w - 20
        draw.rectangle([bar_x0, cy + 46, bar_x1, cy + 50], fill=(236, 231, 219))
        draw.rectangle([bar_x0, cy + 46, bar_x0 + (bar_x1 - bar_x0) * stop["ci"] / 100, cy + 50],
                       fill=color)
        why = stop["why"][0] if stop["why"] else ""
        why = why[:52] + ("…" if len(why) > 52 else "")
        text(draw, (x + 20, cy + 55), "· " + why, font(9.5), INK_SOFT)
        cy += sh + 6

    total = plan["totals"]
    cy = y + h - 30
    text(draw, (x + 14, cy), f"이동 {total['travel_min']}분 · 비용 {total['cost_krw']:,}원 · "
                              f"평균 CI {total['avg_ci']}", font(10.5, 700), INK_SOFT)


def shot_overview(payload, path: Path):
    W, H = 1440, 940
    img = Image.new("RGB", (W, H), SAND)
    draw = ImageDraw.Draw(img)
    header(draw, W, payload)
    left_panel(draw, payload, (24, 84, 330, 600))
    stat_row(draw, payload, (374, 84, W - 374 - 24, 62))
    plans = payload["plans"]
    card_w = (W - 374 - 24 - 2 * 16) / 3
    for i, plan in enumerate(plans):
        plan_card(draw, plan, (374 + i * (card_w + 16), 170, card_w, 560),
                  plan["key"] == payload["summary"].get("best_plan"))
    text(draw, (24, 706), "근거 상세 — 데이터 ID · 기준일 · 수치", font(14, 700))
    table_y = 732
    rrect(draw, [24, table_y, W - 24, table_y + 178], 16, CARD, LINE)
    heads = ["#", "장소", "CI", "사용 항(백분위)", "제외 항", "기준일", "신뢰도"]
    colx = [44, 84, 320, 420, 700, 800, 920]
    for cx, head in zip(colx, heads):
        text(draw, (cx, table_y + 12), head, font(10.5, 700), MUTED)
    best = next((p for p in plans if p["key"] == payload["summary"].get("best_plan")), plans[0])
    ry = table_y + 34
    for stop in best["stops"][:4]:
        terms = stop["evidence"]["terms"]
        used = " · ".join(f"{k} {v*100:.0f}%" for k, v in terms.items() if v is not None)
        vals = [str(stop["order"]), stop["spot_name"], f"{stop['ci']} ({stop['ci_label']})",
                used[:44], ", ".join(stop["evidence"]["dropped_terms"]) or "없음",
                stop["evidence"]["base_date"], stop["evidence"]["confidence"]]
        for cx, value in zip(colx, vals):
            text(draw, (cx, ry), value, font(11))
        draw.line([44, ry + 20, W - 44, ry + 20], fill=LINE)
        ry += 28
    ds = payload["data"]["datasets"]
    text(draw, (44, table_y + 152),
         "데이터 출처: " + " · ".join(f"id={d['hub_id']} {d['dataset']}({d['mode']}, {d['rows']}행)"
                                  for d in ds), font(9.5), MUTED)
    img.save(path)


def shot_map(payload, path: Path):
    W, H = 1440, 900
    img = Image.new("RGB", (W, H), SAND)
    draw = ImageDraw.Draw(img)
    header(draw, W, payload)
    stat_row(draw, payload, (24, 84, W - 48, 62))

    map_box = [24, 170, 900, 640]
    rrect(draw, [map_box[0], map_box[1], map_box[2], map_box[3]], 16, CARD, LINE)
    text(draw, (44, 186), "동선 지도 — 안 A · 한산 우선", font(14, 700))
    text(draw, (44, 208), "개략 윤곽(좌표 기반 도식). 타일·지도 API에 의존하지 않아 오프라인에서도 표시됩니다.",
         font(10), MUTED)
    inner = (70, 240, 870, 620)
    draw.rectangle(inner, fill=(238, 244, 246))

    plans = payload["plans"]
    best = next((p for p in plans if p["key"] == payload["summary"].get("best_plan")), plans[0])
    coords = {}
    with (ROOT / "data" / "catalog" / "spots.csv").open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            if not row.get("id"):
                continue
            coords[row["id"]] = (float(row["lon"]), float(row["lat"]), row["name"], row["emd"])

    global VIEW
    route_coords = []
    origin = payload["constraints"].get("origin_spot")
    if origin in coords:
        route_coords.append((coords[origin][0], coords[origin][1]))
    for stop in best["stops"]:
        if stop["spot_id"] in coords:
            route_coords.append((coords[stop["spot_id"]][0], coords[stop["spot_id"]][1]))
    VIEW = fit_view(route_coords)
    poly = [project(lon, lat, inner) for lon, lat in ISLAND]
    draw.polygon(poly, fill=(233, 239, 236), outline=(196, 211, 203))

    points = []
    if origin in coords:
        points.append(project(coords[origin][0], coords[origin][1], inner))
    for stop in best["stops"]:
        if stop["spot_id"] in coords:
            lon, lat, name, _ = coords[stop["spot_id"]]
            points.append(project(lon, lat, inner))
    if len(points) > 1:
        draw.line(points, fill=TEAL, width=3)
    placed = []
    for idx, stop in enumerate(best["stops"], start=1):
        if stop["spot_id"] not in coords:
            continue
        lon, lat, name, _ = coords[stop["spot_id"]]
        px, py = project(lon, lat, inner)
        draw.ellipse([px - 11, py - 11, px + 11, py + 11], fill=CARD,
                     outline=AMBER if stop["indoor"] else TEAL, width=2)
        text(draw, (px, py), str(idx), font(9, 800), INK, anchor="mm")
        tw = len(name) * 10 + 6
        options = [
            (px + 15, py - 10, "la"), (px + 15, py + 8, "la"),
            (px - 15, py - 10, "ra"), (px - 15, py + 8, "ra"),
            (px, py - 20, "ma"), (px, py + 18, "ma"),
        ]
        best_opt, best_rect, best_cost = options[0], None, 1e9
        for lx, ly, anchor in options:
            if anchor == "la":
                rect = (lx, ly - 12, lx + tw, ly + 4)
            elif anchor == "ra":
                rect = (lx - tw, ly - 12, lx, ly + 4)
            else:
                rect = (lx - tw / 2, ly - 12, lx + tw / 2, ly + 4)
            overlap = sum(1 for r in placed
                          if not (rect[2] < r[0] or rect[0] > r[2] or rect[3] < r[1] or rect[1] > r[3]))
            outside = 1 if (rect[0] < inner[0] + 2 or rect[2] > inner[2] - 2
                            or rect[1] < inner[1] + 2 or rect[3] > inner[3] - 2) else 0
            cost = overlap * 10 + outside * 20
            if cost < best_cost:
                best_opt, best_rect, best_cost = (lx, ly, anchor), rect, cost
        placed.append(best_rect)
        draw.text((best_opt[0], best_opt[1]), name, font=font(10, 700), fill=(30, 41, 52),
                  anchor=best_opt[2], stroke_width=3, stroke_fill=(244, 248, 249))

    # 오른쪽: 왜 여기인가
    card = (916, 170, W - 24, 640)
    rrect(draw, [card[0], card[1], card[2], card[3]], 16, CARD, LINE)
    text(draw, (936, 186), "왜 여기인가 — 정류장별 근거", font(14, 700))
    cy = 216
    for stop in best["stops"][:3]:
        text(draw, (936, cy), f"{stop['order']}. {stop['spot_name']}  CI {stop['ci']}", font(12, 800))
        cy += 22
        for why in stop["why"][:3]:
            wrapped = why if len(why) <= 44 else why[:44] + "…"
            text(draw, (946, cy), "· " + wrapped, font(10), INK_SOFT)
            cy += 18
        cy += 10

    notes_box = [24, 660, W - 24, 860]
    rrect(draw, [notes_box[0], notes_box[1], notes_box[2], notes_box[3]], 16, CARD, LINE)
    text(draw, (44, 676), "한계·유의 (결과에 항상 함께 표시)", font(13, 700))
    cy = 702
    for note in payload["notes"][:4]:
        text(draw, (44, cy), "· " + note, font(11), INK_SOFT)
        cy += 20
    summary = payload["summary"]
    text(draw, (44, 806), f"Critic: 반려 {summary['critic_rounds']}회 · 통과 "
                          f"{'예' if summary['critic_passed'] else '아니오'} · "
                          f"LLM {payload['llm']['provider']}({payload['summary'].get('narrative_source', 'template')})",
         font(11, 700), TEAL)
    img.save(path)


def main() -> int:
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(
        (ROOT / "out" / "runs").glob("*.json"))[-1]
    payload = json.loads(Path(run).read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    shot_overview(payload, OUT / "01_메인화면_3안.png")
    shot_map(payload, OUT / "02_근거와_지도.png")
    print(f"저장: {OUT/'01_메인화면_3안.png'}")
    print(f"저장: {OUT/'02_근거와_지도.png'}  (원본 실행: {run})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
