"""쿨링콜 대시보드 생성기.

- data/processed/dong_index.csv, data/geo/daegu_dongs.geojson, data/processed/meta.json 을 읽어
  자체 완결형 HTML 한 장(dashboard/index.html)과, 화면 캡처용 정적 렌더(dashboard/print.html)를 만든다.
- 외부 라이브러리/CDN 없이 동작한다(오프라인 시연용).
- 수치는 전부 build_index.py가 계산한 값이며, 이 스크립트는 표시와 문안 템플릿만 담당한다.
"""
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"

def nkey(gu, name):
    return (gu, (name or "").replace("·", ".").replace(" ", ""))


ALIAS_TO_GEO = {
    ("달성군", "구지읍"): "구지면",
    ("달성군", "옥포읍"): "옥포면",
    ("달성군", "현풍읍"): "현풍면",
    ("동구", "안심3동"): "안심3·4동",
    ("동구", "안심4동"): "안심3·4동",
}
# 특보 단계는 2025년 실측 폭염강도(74.0)에 대한 배율로 적용한다.
# '경고'가 지수표 기본값(실측 그대로)과 일치한다.
STAGE_MULT = {"주의": 0.80, "경고": 1.00, "위험": 1.15}
W = (0.30, 0.40, 0.30)


def load():
    meta = json.loads((D / "processed" / "meta.json").read_text(encoding="utf-8"))
    dongs = list(csv.DictReader((D / "processed" / "dong_index.csv").open(encoding="utf-8-sig")))
    for d in dongs:
        for k in ("pop", "e65", "e75", "n_shelter", "n_cool", "cap_cool", "n_night", "cap_night", "n_weekend"):
            d[k] = int(d[k]) if d[k] not in ("", None) else 0
        for k in ("e65_rate", "cap_per_1000", "cap_night_per_1000", "vuln", "gap_day", "gap_night", "risk_day", "risk_night"):
            d[k] = float(d[k]) if d[k] not in ("", None) else 0.0
        d["rank_day"] = int(d["rank_day"])
        d["rank_night"] = int(d["rank_night"])
    geo = json.loads((D / "geo" / "daegu_dongs.geojson").read_text(encoding="utf-8"))
    return meta, dongs, geo


def haversine(a, b):
    R = 6371000
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def centroid(geom):
    xs, ys, wsum = 0.0, 0.0, 0.0
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        ring = poly[0]
        area = 0.0
        cx = cy = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i]
            x1, y1 = ring[i + 1]
            cross = x0 * y1 - x1 * y0
            area += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        area *= 0.5
        if area == 0:
            continue
        cx /= 6 * area
        cy /= 6 * area
        xs += cx * abs(area)
        ys += cy * abs(area)
        wsum += abs(area)
    if not wsum:
        return None
    return (xs / wsum, ys / wsum)


def palette(risk):
    # YlOrRd 5단계
    stops = [
        (60, "#fff5eb"),
        (68, "#fee6ce"),
        (75, "#fdc086"),
        (80, "#f16913"),
        (101, "#a63603"),
    ]
    for edge, color in stops:
        if risk < edge:
            return color
    return "#a63603"


def build_map(dongs, geo, mode="day"):
    by_key = {(d["gu"], d["dong"]): d for d in dongs}
    feats = []
    lon0, lon1, lat0, lat1 = 999, -999, 999, -999
    for f in geo["features"]:
        polys = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
        for poly in polys:
            for lon, lat in poly[0]:
                lon0, lon1 = min(lon0, lon), max(lon1, lon)
                lat0, lat1 = min(lat0, lat), max(lat1, lat)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    w = (lon1 - lon0) * k
    h = lat1 - lat0
    scale = 1000.0 / w
    Hh = h * scale

    def project(lon, lat):
        return ((lon - lon0) * k * scale, (lat1 - lat) * scale)

    matched = 0
    by_nkey = {nkey(d["gu"], d["dong"]): d for d in dongs}
    for f in geo["features"]:
        gu, name = f["properties"]["gu"], f["properties"]["name"]
        d = by_nkey.get(nkey(gu, name))
        if d is None:
            for (agu, adong), gname in ALIAS_TO_GEO.items():
                if gname == name and agu == gu:
                    d = by_key.get((agu, adong))
                    break
        risk = (d["risk_day"] if mode == "day" else d["risk_night"]) if d else None
        color = palette(risk) if risk is not None else "#e9e9e9"
        polys = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
        paths = []
        for poly in polys:
            ring = poly[0]
            pts = [project(lon, lat) for lon, lat in ring]
            dstr = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
            paths.append(dstr)
        cls = "dong" if d else "dong missing"
        label = f"{gu} {name}"
        tip = f"{label}"
        if d:
            matched += 1
            tip = f"{label} · 위험지수 {risk:.1f} · 65세 이상 {d['e65']:,}명 · 냉방 커버 {d['cap_per_1000']:.0f}석/1천명"
        feats.append(
            f'<path class="{cls}" d="{" ".join(paths)}" fill="{color}" data-key="{gu}|{name}" '
            f'data-gu="{gu}" data-dong="{name}" data-risk="{risk if risk is not None else ""}"><title>{tip}</title></path>'
        )
    wpx = 1000.0
    hpx = Hh
    disp_h = 545.0
    disp_w = disp_h * wpx / hpx
    svg = (
        f'<svg id="map" viewBox="0 0 1000 {Hh:.0f}" width="{disp_w:.0f}" height="{disp_h:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="대구 행정동별 폭염 위험지수 지도">'
        + "".join(feats)
        + "</svg>"
    )
    return svg, matched, Hh


def heat_of(meta, stage):
    return min(100.0, meta["heat"]["score"] * STAGE_MULT[stage])


def message(d, meta, stage="경고", night=False, nearest=None, median=None):
    heat = heat_of(meta, stage)
    risk = W[0] * heat + W[1] * d["vuln"] + W[2] * (d["gap_night"] if night else d["gap_day"])
    cap = d["cap_night_per_1000"] if night else d["cap_per_1000"]
    ratio = (cap / median * 100) if median else 0
    if night:
        if d["n_night"] == 0:
            night_line = "· 해가 진 뒤(20시 이후) 문을 여는 냉방 쉼터가 이 동네에 없습니다."
        elif d["n_night"] <= 2:
            night_line = f"· 해가 진 뒤(20시 이후) 문을 여는 냉방 쉼터가 이 동네에 {d['n_night']}곳뿐입니다."
        else:
            night_line = f"· 해가 진 뒤(20시 이후) 운영 냉방 쉼터가 {d['n_night']}곳 있습니다."
    else:
        night_line = f"· 야간(20시 이후) 운영 냉방 쉼터는 {d['n_night']}곳입니다."
    near = ""
    if nearest:
        near = f"· 가장 가까운 냉방 쉼터는 {nearest[0]}(동 중심에서 약 {nearest[1]:,.0f}m)입니다."
    return (
        f"[쿨링콜 · {d['gu']} {d['dong']}] 오늘 안부 연락 문안\n"
        f"· 지금 대구는 폭염 '{stage}' 단계입니다. 올여름 폭염일수 {meta['heat']['heat_days']}일, "
        f"열대야 {meta['heat']['tropical_nights']}일, 최고기온 {meta['heat']['max_ta']}℃.\n"
        f"· {d['dong']}은(는) 65세 이상 {d['e65']:,}명(주민의 {d['e65_rate']}%)이 사는 동네이고, "
        f"냉방 쉼터 수용인원은 고령자 1,000명당 {cap:.0f}석으로 대구 중앙값({median:.0f}석)의 {ratio:.0f}%입니다.\n"
        f"{night_line}\n"
        f"{near}\n"
        f"· 오늘 확인 부탁드립니다: ① 냉방기·선풍기 가동 ② 물·이온음료 ③ 오후 2~5시 외출 자제와 가까운 쉼터 안내."
    )


def heat_trend_svg(meta, width=430, height=150):
    series = meta["heat"]["series"]
    years = list(series.keys())
    hd = [series[y]["heat_days"] for y in years]
    tn = [series[y]["tropical_nights"] for y in years]
    vmax = max(max(hd), max(tn)) * 1.15
    n = len(years)
    gap = width / n
    bw = gap * 0.30
    parts = []
    for i, y in enumerate(years):
        x = i * gap + gap * 0.12
        h1 = hd[i] / vmax * (height - 28)
        h2 = tn[i] / vmax * (height - 28)
        color = "#a63603" if y == "2025" else "#fdc086"
        color2 = "#1f6fb2" if y == "2025" else "#bcd7ea"
        parts.append(
            f'<rect x="{x:.0f}" y="{height-20-h1:.0f}" width="{bw:.0f}" height="{h1:.0f}" fill="{color}"></rect>'
            f'<rect x="{x+bw+1:.0f}" y="{height-20-h2:.0f}" width="{bw:.0f}" height="{h2:.0f}" fill="{color2}"></rect>'
            f'<text x="{x+bw:.0f}" y="{height-6:.0f}" font-size="9" fill="#6b6b6b" text-anchor="middle">{y[2:]}</text>'
        )
        if y in ("2015", "2018", "2022", "2024", "2025"):
            parts.append(
                f'<text x="{x+bw:.0f}" y="{height-24-max(h1,h2):.0f}" font-size="9.5" fill="#333" text-anchor="middle">'
                f'{hd[i]}</text>'
            )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts)
        + "</svg>"
    )


def main():
    meta, dongs, geo = load()
    median = sorted(d["cap_per_1000"] for d in dongs)[len(dongs) // 2]
    by_key = {(d["gu"], d["dong"]): d for d in dongs}

    # 동 중심(경계 무게중심)에서 가장 가까운 냉방 쉼터
    shelters = json.loads((D / "processed" / "meta.json").read_text(encoding="utf-8"))  # placeholder
    shelters = json.loads((HERE / "dashboard" / "data.json").read_text(encoding="utf-8"))["shelters"]
    cool = [s for s in shelters if s["op"] in ("운영", "") and s["ac"] > 0 and s["lat"] and s["lon"]]
    by_nkey = {nkey(d["gu"], d["dong"]): d for d in dongs}
    nearest_of = {}
    for f in geo["features"]:
        gu, name = f["properties"]["gu"], f["properties"]["name"]
        key = None
        d = by_key.get((gu, name)) or by_nkey.get(nkey(gu, name))
        if d:
            key = (d["gu"], d["dong"])
        else:
            for (agu, adong), gname in ALIAS_TO_GEO.items():
                if gname == name and agu == gu:
                    key = (agu, adong)
                    break
        if not key:
            continue
        c = centroid(f["geometry"])
        if not c:
            continue
        cand = [(haversine(c, (s["lon"], s["lat"])), s) for s in cool if s["gu"] == key[0]]
        if not cand:
            continue
        dist, s = min(cand, key=lambda x: x[0])
        nearest_of[key] = (s["name"], dist)

    top = sorted(dongs, key=lambda d: -d["risk_day"])[:10]
    top_night = sorted(dongs, key=lambda d: -d["risk_night"])[:10]
    night_zero = sum(1 for d in dongs if d["n_night"] == 0)
    e65_total = sum(d["e65"] for d in dongs)
    cap_total = sum(d["cap_cool"] for d in dongs)
    cap_avg = cap_total / (e65_total / 1000)

    series = meta["heat"]["series"]
    prev_years = [y for y in series if y != "2025"]
    avg_heat = round(sum(series[y]["heat_days"] for y in prev_years) / len(prev_years), 1)
    heat_ratio = round(meta["heat"]["heat_days"] / avg_heat * 100)
    trend_svg = heat_trend_svg(meta)

    svg_day, matched, map_h = build_map(dongs, geo, "day")
    svg_night, _, _ = build_map(dongs, geo, "night")

    heroes = {
        "day": max(dongs, key=lambda d: d["risk_day"]),
        "night": max(dongs, key=lambda d: d["risk_night"]),
    }
    hero = heroes["day"]
    hero_msg = message(hero, meta, "위험", False, nearest_of.get((hero["gu"], hero["dong"])), median)

    payload = {
        "meta": meta,
        "dongs": dongs,
        "median": median,
        "nearest": {f"{k[0]}|{k[1]}": v for k, v in nearest_of.items()},
    }

    def rows_html(rows, mode):
        out = []
        for d in rows:
            risk = d["risk_day"] if mode == "day" else d["risk_night"]
            gap = d["gap_day"] if mode == "day" else d["gap_night"]
            cls = "risk4" if risk >= 80 else "risk3" if risk >= 75 else "risk2" if risk >= 68 else "risk1"
            out.append(
                f"<tr data-key=\"{d['gu']}|{d['dong']}\"><td class=\"num\">{d['rank_day'] if mode=='day' else d['rank_night']}</td>"
                f"<td>{d['gu']} {d['dong']}</td>"
                f"<td class=\"num {cls}\">{risk:.1f}</td>"
                f"<td class=\"num\">{d['e65']:,}</td>"
                f"<td class=\"num\">{d['e65_rate']}%</td>"
                f"<td class=\"num\">{d['cap_per_1000']:.0f}</td>"
                f"<td class=\"num\">{d['n_night']}</td>"
                f"<td class=\"num\">{gap:.0f}</td></tr>"
            )
        return "".join(out)

    MODES = [("day", "index.html"), ("day", "print_day.html"), ("night", "print_night.html")]
    for mode, fname in MODES:
        hero = heroes[mode]
        svg = svg_day if mode == "day" else svg_night
        rows = rows_html(top if mode == "day" else top_night, mode)
        msg_hero = message(hero, meta, "경고", mode == "night", nearest_of.get((hero["gu"], hero["dong"])), median)
        html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>쿨링콜 · 대구 폭염 사각지대 대응 콘솔 (시연용)</title>
<style>
:root {{ --ink:#1b1b1b; --muted:#6b6b6b; --line:#e3e3e3; --bg:#f7f7f5; --accent:#a63603; --cool:#1f6fb2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font-family:"Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif; font-size:13px; line-height:1.5; }}
@page {{ size: 1240px 1500px; margin: 0; }}
.wrap {{ width:1200px; margin:0 auto; padding:18px 20px 30px; }}
.ctrl-static {{ font-size:12px; color:#444; margin:0 0 8px; }}
.ctrl-static b {{ color:#a63603; }}
header.top {{ display:block; border-bottom:2px solid var(--ink); padding-bottom:10px; margin-bottom:16px; }}
header.top h1 {{ font-size:22px; margin:0; letter-spacing:-0.5px; }}
header.top .sub {{ color:var(--muted); font-size:12px; margin-top:4px; }}
.badge {{ display:inline-block; background:var(--accent); color:#fff; font-size:11px; padding:2px 8px; border-radius:10px; vertical-align:middle; margin-left:8px; }}
.kpis {{ width:100%; border-collapse:separate; border-spacing:10px 0; margin:0 -10px 16px; }}
.kpis td {{ width:25%; background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px 14px; vertical-align:top; }}
.kpis .label {{ color:var(--muted); font-size:11px; }}
.kpis .value {{ font-size:26px; font-weight:700; letter-spacing:-1px; }}
.kpis .value small {{ font-size:12px; font-weight:400; color:var(--muted); }}
.cols {{ width:100%; border-collapse:separate; border-spacing:12px 0; margin:0 -12px 16px; }}
.cols > tbody > tr > td {{ vertical-align:top; }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.card h2 {{ font-size:14px; margin:0 0 8px; }}
.card h2 span {{ color:var(--muted); font-weight:400; font-size:11px; margin-left:6px; }}
#map {{ display:block; margin:0 auto; }}
.dong {{ stroke:#fff; stroke-width:0.6; }}
.dong.missing {{ fill:#e9e9e9; stroke:#cfcfcf; }}
.dong.hl {{ stroke:#111; stroke-width:1.8; }}
.legend {{ margin-top:8px; font-size:11px; color:var(--muted); }}
.legend i {{ display:inline-block; width:18px; height:10px; margin-right:3px; vertical-align:middle; border:1px solid #ddd; }}
table.rank {{ width:100%; border-collapse:collapse; font-size:12px; }}
table.rank th {{ text-align:left; color:var(--muted); font-weight:500; font-size:11px; border-bottom:1px solid var(--line); padding:6px 4px; }}
table.rank td {{ border-bottom:1px solid #f1f1f1; padding:5px 4px; }}
table.rank td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.risk4 {{ color:#a63603; font-weight:700; }} .risk3 {{ color:#e6550d; }} .risk2 {{ color:#b8860b; }} .risk1 {{ color:#666; }}
.bars {{ margin-top:6px; }}
.bar {{ font-size:11.5px; margin-bottom:5px; }}
.bar b {{ display:inline-block; width:104px; font-weight:500; }}
.bar .track {{ display:inline-block; width:150px; height:9px; background:#f0f0f0; border-radius:5px; vertical-align:middle; overflow:hidden; }}
.bar .fill {{ display:block; height:9px; background:linear-gradient(90deg,#fdc086,#a63603); }}
pre.msg {{ white-space:pre-wrap; font-family:"Noto Sans KR",sans-serif; font-size:12.5px; background:#fbfaf7;
  border:1px dashed #d8d2c4; border-radius:8px; padding:12px; margin:8px 0 0; }}
footer {{ margin-top:18px; color:var(--muted); font-size:11px; border-top:1px solid var(--line); padding-top:10px; }}
.ctrl {{ margin:0 0 10px; font-size:12px; }}
select {{ font-size:12px; padding:3px 6px; border:1px solid var(--line); border-radius:6px; background:#fff; }}
.tag {{ display:inline-block; font-size:11px; color:var(--cool); border:1px solid #cfe0ee; background:#f2f8fc; border-radius:10px; padding:1px 7px; margin-left:6px; }}
</style></head>
<body><div class="wrap">
<header class="top">
  <h1>쿨링콜 <span class="badge">부문1 시연용 프로토타입</span></h1>
  <div class="sub">대구광역시 폭염 취약 사각지대 자동 발굴 · 안부 연락 문안 생성 ·
    기준일 2026-11-16 · 데이터: 기상청 기상자료개방포털(대구 지점 143, 2015~2025) / 대구광역시 무더위쉼터 현황(2026) / 행정안전부 주민등록 인구통계(2026.10)</div>
</header>

<table class="kpis"><tr>
  <td><div class="label">오늘 최우선 연락 동네</div><div class="value">{hero['gu']} {hero['dong']}</div>
      <div class="label">위험지수 {(hero['risk_day'] if mode == 'day' else hero['risk_night']):.1f} · 65세 이상 {hero['e65']:,}명</div></td>
  <td><div class="label">야간(20시 이후) 냉방쉼터가 없는 동</div><div class="value">{night_zero}<small> / {len(dongs)}개 동</small></div>
      <div class="label">열대야 {meta['heat']['tropical_nights']}일(2025) 기준</div></td>
  <td><div class="label">65세 이상 인구</div><div class="value">{e65_total:,}<small> 명</small></div>
      <div class="label">대구 전체 인구의 13.1%</div></td>
  <td><div class="label">고령자 1,000명당 냉방쉼터 수용인원</div><div class="value">{cap_avg:.0f}<small> 석 (중앙값 {median:.0f}석)</small></div>
      <div class="label">냉방 쉼터 {sum(d['n_cool'] for d in dongs):,}곳 · 총 {cap_total:,}석</div></td>
</tr></table>

<table class="cols"><tr>
<td style="width:50%">
  <div class="card">
    <h2>행정동별 폭염 위험지수 <span>클릭하면 오른쪽에 해당 동 상세·문안이 표시됩니다</span></h2>
    <div class="ctrl">폭염특보 단계
      <select id="stage"><option>주의</option><option selected>경고</option><option>위험</option></select>
      &nbsp;시간대 <select id="mode"><option value="day" selected>주간(주민센터·경로당 중심)</option><option value="night">야간(20시 이후)</option></select>
    </div>
    <div id="mapwrap">{svg}</div>
    <div class="legend">
      <i style="background:#fff5eb"></i>60 미만 <i style="background:#fee6ce"></i>60–68 <i style="background:#fdc086"></i>68–75
      <i style="background:#f16913"></i>75–80 <i style="background:#a63603"></i>80 이상
      &nbsp;· 지도는 2018년 기준 경계가 있는 139개 동을 그립니다. 군위군 8개 읍면과 2021년 이후 신설된 혁신동·유천동은 경계자료에 없어 지도에는 없지만, 아래 순위표와 지수표에는 포함됩니다.
    </div>
  </div>
</td>
<td style="width:50%">
  <div class="card" style="margin-bottom:12px">
    <h2 id="seltitle">{hero['gu']} {hero['dong']} <span>선택 동 상세</span></h2>
    <div class="bars" id="selbars">
      <div class="bar"><b>폭염 강도</b><span class="track"><span class="fill" style="width:{meta['heat']['score']:.0f}%"></span></span> {meta['heat']['score']:.0f}</div>
      <div class="bar"><b>고령 취약도</b><span class="track"><span class="fill" style="width:{hero['vuln']:.0f}%"></span></span> {hero['vuln']:.0f}</div>
      <div class="bar"><b>대응 결손</b><span class="track"><span class="fill" style="width:{(hero['gap_day'] if mode == 'day' else hero['gap_night']):.0f}%"></span></span> {(hero['gap_day'] if mode == 'day' else hero['gap_night']):.0f}</div>
    </div>
    <div class="bars" style="margin-top:10px;color:#444">
      <div class="bar">65세 이상 <b style="width:auto">{hero['e65']:,}명</b> (주민의 {hero['e65_rate']}%)</div>
      <div class="bar">냉방 쉼터 <b style="width:auto">{hero['n_cool']}곳 / {hero['cap_cool']:,}석</b> (고령자 1천명당 {hero['cap_per_1000']:.0f}석)</div>
      <div class="bar">야간 운영 <b style="width:auto">{hero['n_night']}곳</b> · 주말 운영 {hero['n_weekend']}곳</div>
    </div>
  </div>
  <div class="card">
    <h2>담당자용 안부 연락 문안 <span class="tag">수치는 계산값 슬롯 주입</span></h2>
    <pre class="msg" id="msg">{msg_hero}</pre>
    <div style="color:#6b6b6b;font-size:11px;margin-top:6px">
      문장은 AI가 쓰고, 숫자·쉼터 정보는 이 화면의 계산값만 채웁니다(임의 생성 금지). 발송은 담당자 승인 후에만 이뤄집니다.
    </div>
  </div>
  <div class="card" style="margin-top:12px">
    <h2>왜 지금인가 <span>기상청 ASOS 대구(143) 연도별 폭염일수</span></h2>
    {trend_svg}
    <div style="font-size:11.5px;color:#444;margin-top:4px">
      <i style="display:inline-block;width:9px;height:9px;background:#fdc086;border:1px solid #eee"></i> 폭염일수(일최고 33℃ 이상)
      <i style="display:inline-block;width:9px;height:9px;background:#bcd7ea;margin-left:8px;border:1px solid #eee"></i> 열대야(일최저 25℃ 이상)
      · 2025년 폭염일수 <b>{meta['heat']['heat_days']}일</b>은 2015~2024년 평균({avg_heat}일)의 {heat_ratio}%입니다.
    </div>
  </div>
</td>
</tr></table>

<div class="card">
  <h2>우선 연락 대상 순위 <span>{("야간(20시 이후)" if mode == "night" else "주간")} 기준 상위 10개 동 · 지수 구성요소(폭염 30% · 고령취약 40% · 대응결손 30%)</span></h2>
  <table class="rank">
    <thead><tr><th>순위</th><th>행정동</th><th style="text-align:right">위험지수</th><th style="text-align:right">65세 이상</th>
    <th style="text-align:right">고령비율</th><th style="text-align:right">커버(석/1천명)</th><th style="text-align:right">야간 쉼터</th><th style="text-align:right">대응결손</th></tr></thead>
    <tbody id="ranktable">{rows}</tbody>
  </table>
</div>

<footer>
  데이터·산출근거: 기상청 기상자료개방포털 「기후통계분석 · 기온분석」(대구 지점 143, 2015-01-01~2025-12-31 일별 최저/평균/최고기온) ·
  대구광역시 자연재난과 「무더위쉼터 현황표」(2026) · 행정안전부 「행정동별 성별·연령별 주민등록 인구」(2026년 10월).
  위험지수 = 0.30×폭염강도 + 0.40×고령취약도 + 0.30×대응결손. 계산은 모두 코드로 수행하며, AI는 문장 작성만 담당합니다.
  행정동 경계는 통계청 2018 기준 공개 경계자료(보조자료, 지도 표시용).
</footer>
</div>
<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const W = [0.30, 0.40, 0.30];
const STAGE_MULT = {{"주의":0.80,"경고":1.00,"위험":1.15}};
const HEAT = DATA.meta.heat.score;
const heatOf = s => Math.min(100, HEAT * STAGE_MULT[s]);
const fmt = n => n.toLocaleString('ko-KR');
const byKey = {{}};
DATA.dongs.forEach(d => byKey[d.gu+'|'+d.dong] = d);
let selected = "{hero['gu']}|{hero['dong']}";

function riskOf(d, stage, mode) {{
  const gap = mode === 'night' ? d.gap_night : d.gap_day;
  return W[0]*heatOf(stage) + W[1]*d.vuln + W[2]*gap;
}}
function colorOf(r) {{
  if (r < 60) return '#fff5eb'; if (r < 68) return '#fee6ce'; if (r < 75) return '#fdc086';
  if (r < 80) return '#f16913'; return '#a63603';
}}
function renderMap(stage, mode) {{
  document.querySelectorAll('#map path.dong').forEach(p => {{
    const d = byKey[p.dataset.gu+'|'+p.dataset.dong];
    if (!d) return;
    p.setAttribute('fill', colorOf(riskOf(d, stage, mode)));
    p.classList.toggle('hl', p.dataset.gu+'|'+p.dataset.dong === selected);
  }});
}}
function renderTable(stage, mode) {{
  const rows = DATA.dongs.slice().sort((a,b) => riskOf(b,stage,mode) - riskOf(a,stage,mode)).slice(0,10);
  const tb = document.getElementById('ranktable');
  tb.innerHTML = rows.map((d,i) => {{
    const r = riskOf(d,stage,mode), gap = mode==='night' ? d.gap_night : d.gap_day;
    const cls = r>=80?'risk4':r>=75?'risk3':r>=68?'risk2':'risk1';
    return `<tr data-key="${{d.gu}}|${{d.dong}}"><td class="num">${{i+1}}</td><td>${{d.gu}} ${{d.dong}}</td>`
      + `<td class="num ${{cls}}">${{r.toFixed(1)}}</td><td class="num">${{fmt(d.e65)}}</td>`
      + `<td class="num">${{d.e65_rate}}%</td><td class="num">${{d.cap_per_1000.toFixed(0)}}</td>`
      + `<td class="num">${{d.n_night}}</td><td class="num">${{gap.toFixed(0)}}</td></tr>`;
  }}).join('');
}}
function msgFor(d, stage, mode) {{
  const h = DATA.meta.heat, med = DATA.median;
  const near = DATA.nearest[d.gu+'|'+d.dong];
  const gap = mode==='night' ? d.gap_night : d.gap_day;
  const cap = mode === 'night' ? d.cap_night_per_1000 : d.cap_per_1000;
  const ratio = med ? Math.round(cap/med*100) : 0;
  const nl = mode==='night'
    ? (d.n_night === 0 ? '· 해가 진 뒤(20시 이후) 문을 여는 냉방 쉼터가 이 동네에 없습니다.'
       : d.n_night <= 2 ? `· 해가 진 뒤(20시 이후) 문을 여는 냉방 쉼터가 이 동네에 ${{d.n_night}}곳뿐입니다.`
       : `· 해가 진 뒤(20시 이후) 운영 냉방 쉼터가 ${{d.n_night}}곳 있습니다.`)
    : `· 야간(20시 이후) 운영 냉방 쉼터는 ${{d.n_night}}곳입니다.`;
  const nearLine = near ? `· 가장 가까운 냉방 쉼터는 ${{near[0]}}(동 중심에서 약 ${{Math.round(near[1]).toLocaleString('ko-KR')}}m)입니다.` : '';
  return `[쿨링콜 · ${{d.gu}} ${{d.dong}}] 오늘 안부 연락 문안\\n`
    + `· 지금 대구는 폭염 '${{stage}}' 단계입니다. 올여름 폭염일수 ${{h.heat_days}}일, 열대야 ${{h.tropical_nights}}일, 최고기온 ${{h.max_ta}}℃.\\n`
    + `· ${{d.dong}}은(는) 65세 이상 ${{fmt(d.e65)}}명(주민의 ${{d.e65_rate}}%)이 사는 동네이고, 냉방 쉼터 수용인원은 고령자 1,000명당 ${{d.cap_per_1000.toFixed(0)}}석으로 대구 중앙값(${{med.toFixed(0)}}석)의 ${{ratio}}%입니다.\\n`
    + nl + '\\n' + nearLine + '\\n'
    + `· 오늘 확인 부탁드립니다: ① 냉방기·선풍기 가동 ② 물·이온음료 ③ 오후 2~5시 외출 자제와 가까운 쉼터 안내.`;
}}
function renderDetail(stage, mode) {{
  const d = byKey[selected];
  const r = riskOf(d, stage, mode);
  document.getElementById('seltitle').innerHTML = `${{d.gu}} ${{d.dong}} <span>선택 동 상세 · 위험지수 ${{r.toFixed(1)}}</span>`;
  document.getElementById('selbars').innerHTML =
      `<div class="bar"><b>폭염 강도</b><span class="track"><span class="fill" style="width:${{heatOf(stage)}}%"></span></span> ${{heatOf(stage).toFixed(0)}}</div>`
    + `<div class="bar"><b>고령 취약도</b><span class="track"><span class="fill" style="width:${{d.vuln}}%"></span></span> ${{d.vuln.toFixed(0)}}</div>`
    + `<div class="bar"><b>대응 결손</b><span class="track"><span class="fill" style="width:${{(mode==='night'?d.gap_night:d.gap_day)}}%"></span></span> ${{(mode==='night'?d.gap_night:d.gap_day).toFixed(0)}}</div>`;
  document.getElementById('msg').textContent = msgFor(d, stage, mode);
}}
function refresh() {{
  const stage = document.getElementById('stage').value, mode = document.getElementById('mode').value;
  renderMap(stage, mode); renderTable(stage, mode); renderDetail(stage, mode);
}}
document.getElementById('stage').addEventListener('change', refresh);
document.getElementById('mode').addEventListener('change', refresh);
const ALIAS = {{"달성군|구지면":"달성군|구지읍","달성군|옥포면":"달성군|옥포읍","달성군|현풍면":"달성군|현풍읍",
  "동구|안심3·4동":"동구|안심3동"}};
document.addEventListener('click', e => {{
  const el = e.target.closest('[data-key]');
  if (!el) return;
  let k = el.dataset.key || (el.dataset.gu+'|'+el.dataset.dong);
  k = ALIAS[k] || k;
  if (byKey[k]) {{ selected = k; refresh(); }}
}});
refresh();
</script>
</body></html>
"""
        if fname.startswith("print"):
            import re as _re
            label = "야간(20시 이후)" if mode == "night" else "주간(주민센터·경로당 중심)"
            html = _re.sub(
                r'<div class="ctrl">.*?</div>',
                f'<div class="ctrl-static">폭염특보 <b>경고</b> 단계(2025년 실측 폭염강도 {meta['heat']['score']}) · 시간대 <b>{label}</b> 기준으로 계산한 화면입니다. '
                f'(배포본에서는 특보 단계·시간대를 바꾸면 지도·순위·문안이 함께 다시 계산됩니다.)</div>',
                html,
                flags=_re.S,
            )
        outdir = HERE / "dashboard"
        outdir.mkdir(exist_ok=True)
        (outdir / fname).write_text(html, encoding="utf-8")
        print("wrote", fname, len(html), "bytes (mode", mode + ")")
    print("matched map dongs:", matched, "of", len(geo["features"]))
    print("map height", round(map_h), "night-zero dongs:", night_zero, "cap_avg", round(cap_avg, 1))


if __name__ == "__main__":
    main()
