#!/usr/bin/env python3
"""기획서 초안(markdown) -> 인쇄용 A4 PDF (15페이지 고정 레이아웃).

각 `## pN.` 섹션이 정확히 한 페이지가 되도록 섹션별 본문 크기와 여유(airy) 레이아웃을
자동으로 고른다. 부록 A·B는 '목차' 페이지(p2)로 옮겨 15페이지 한도를 지킨다.

사용:
    python3 tools/build_pdf.py --fit --png   # 크기 재계산 + PDF + 페이지 PNG
    python3 tools/build_pdf.py               # 저장된 크기로 PDF만 재생성

빌드 의존성: weasyprint, markdown (도구 전용. 실행 코드는 표준 라이브러리만 사용)
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_MD = ROOT / "docs" / "기획서_초안.md"
OUT_PDF = ROOT / "dist" / "빈틈_기획서_v1.0.0.pdf"
OUT_HTML = ROOT / "dist" / "빈틈_기획서_v1.0.0.html"
SIZES_JSON = ROOT / "dist" / ".page_sizes.json"

FONT_KR = ROOT / "assets" / "fonts" / "NotoSansKR.ttf"
FONT_MONO = Path("/usr/share/fonts/pickle-hwp/NotoSansMonoCJKkr-Regular.otf")

PAGE_H_MM = 297.0
MARGIN_TOP_MM = 14.0
MARGIN_BOTTOM_MM = 15.0
CONTENT_BOTTOM_MM = PAGE_H_MM - MARGIN_BOTTOM_MM  # 282

SHORT = {
    "p2": "목차 · 읽는 법 · 제출물 대응",
    "p3": "1. 구현목표",
    "p4": "1. 구현목표",
    "p5": "2. 서비스 제안",
    "p6": "2. 서비스 제안",
    "p7": "2. 서비스 제안",
    "p8": "3. Agent 개발 구성",
    "p9": "3. Agent 개발 구성",
    "p10": "3. Agent 개발 구성",
    "p11": "3. Agent 개발 구성",
    "p12": "4. 데이터 활용 계획",
    "p13": "4. 데이터 활용 계획",
    "p14": "5. 개발·탑재 계획",
    "p15": "5. 개발·탑재 계획",
}

# 페이지별 레이아웃 미조정 (이미지 폭 등)
LAYOUT: dict[str, dict[str, str]] = {
    "p6": {"img": "84%"},
}

# 페이지 하단 보조 도식 (본문 주장의 요약 — 새 수치 없음)
EXTRA: dict[str, str] = {
    "p3": """
<table class="chain"><tbody><tr>
<td><span class="cn">01 문제</span><b>여행 중 재계획 비용</b>지금·이 사람의 남은 하루를 다시 짜는 일</td>
<td><span class="cn">02 데이터</span><b>읍면동 실측 유동인구</b>583(일 단위 자동 갱신) + 591·614·579</td>
<td><span class="cn">03 해법</span><b>남은 하루 동선 3안</b>제약을 조건으로, 근거 수치를 붙여서</td>
<td><span class="cn">04 구조</span><b>6단계 Agent + Critic</b>숫자는 코드, 문장은 LLM, 검증은 규칙</td>
</tr></tbody></table>
<p class="caption">문제 정의가 데이터·해법·구조를 결정하는 순서 — 이 기획서의 논리</p>
""",
    "p12": """
<div class="wchart">
<div class="wrow"><span class="wname">583 읍면동 내국인 유동인구</span><span class="wtrack"><i class="w45"></i></span><span class="wval">0.45</span></div>
<div class="wrow"><span class="wname">591 관광지별 내국인 유입자수</span><span class="wtrack"><i class="w25"></i></span><span class="wval">0.25</span></div>
<div class="wrow"><span class="wname">614 일일 노선별 버스 이용자</span><span class="wtrack"><i class="w20"></i></span><span class="wval">0.20</span></div>
<div class="wrow"><span class="wname">579 일별 기상</span><span class="wtrack"><i class="w10"></i></span><span class="wval">0.10</span></div>
</div>
<p class="caption">혼잡지수(CI)에 대한 데이터별 기여 가중치 — 결측이면 0으로 두고 남은 가중치로 자동 재정규화한다(p7)</p>
""",
}

READING_GUIDE = """
<blockquote class="guide">
<p><strong>읽는 법</strong> — 각 <code>pN</code> 제목이 한 페이지의 시작입니다. p1은 요약, p2는 목차·제출물 대응,
p3~p7은 구현목표·서비스, p8~p11은 Agent 구조, p12~p13은 데이터, p14~p15는 개발·탑재·검증입니다.
연한 청록 박스는 “심사 관점 메모”로, 각 절이 어느 평가 항목을 겨냥했는지 적었습니다.</p>
<p>제출물은 <strong>실행 소스 코드 · 실행환경·매뉴얼 · 데이터 활용 명세 · 결과 설명자료</strong> 4종이며,
ZIP과의 대응은 부록 A에 정리했습니다. 모든 수치는 ZIP에 든 코드로 재현됩니다.</p>
</blockquote>
"""


# ---------------------------------------------------------------- markdown
@lru_cache(maxsize=1)
def sections() -> dict[str, str]:
    text = SRC_MD.read_text(encoding="utf-8")
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"^## p\d+\.", ln)]
    out: dict[str, str] = {}
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end])
        key = re.match(r"^## (p\d+)\.", block).group(1)
        out[key] = block

    body = out["p15"]
    m = re.search(r"^### 부록 A\..*", body, flags=re.M)
    appendix = ""
    if m:
        appendix = body[m.start():]
        out["p15"] = re.sub(r"\n+---\s*$", "", body[: m.start()].rstrip())
    # 부록 A·B는 '목차' 페이지(p2)에 함께 배치해 15페이지를 지킨다
    out["p2"] = out["p2"].rstrip() + "\n\n---\n\n" + appendix
    return out


def md_to_html(md: str) -> str:
    import markdown

    return markdown.markdown(
        md,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        output_format="html5",
    )


def max_cells(text: str) -> int:
    return max(
        (
            sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in ln)
            for ln in text.splitlines()
        ),
        default=0,
    )


def strip_tags(html: str) -> str:
    html = re.sub(r"<br\s*/?>", "\n", html)
    return re.sub(r"<[^>]+>", "", html)


def add_colgroups(html: str) -> str:
    """표마다 내용 폭에 맞는 열 너비(colgroup)를 붙여 균형을 맞춘다."""

    def repl(m: re.Match) -> str:
        table = m.group(0)
        rows = re.findall(r"<tr>(.*?)</tr>", table, flags=re.S)
        if not rows:
            return table
        widths: list[int] = []
        for row in rows:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S)
            for i, cell in enumerate(cells):
                w = min(max_cells(strip_tags(cell).strip()), 34)
                if i >= len(widths):
                    widths.append(w)
                else:
                    widths[i] = max(widths[i], w)
        if not widths:
            return table
        # 아주 짧은 열이 짜부라지지 않도록 sqrt 로 완만하게 만든 뒤 하한을 둔다
        weights = [max(w, 3) ** 0.7 for w in widths]
        total = sum(weights)
        pct = [max(w / total * 100, 7.5) for w in weights]
        scale = 100.0 / sum(pct)
        cols = "".join(f'<col style="width:{p * scale:.1f}%">' for p in pct)
        return f'<table class="fit"><colgroup>{cols}</colgroup>' + table[len("<table>") :]

    return re.sub(r"<table>.*?</table>", repl, html, flags=re.S)


def section_html(key: str, md: str, font_pt: float, *, cover: bool = False, airy: bool = False) -> str:
    md = re.sub(r"^## p\d+\.\s*", "## ", md, count=1, flags=re.M)
    inner = md_to_html(md)

    inner = re.sub(
        r"<h2>(.*?)</h2>",
        lambda m: f'<h2 data-kicker="{SHORT.get(key, "")}">{m.group(1)}</h2>',
        inner,
        count=1,
    )
    inner = inner.replace(
        "<p><strong>데이터 모드 고지", '<p class="notice"><strong>데이터 모드 고지'
    )
    inner = re.sub(r"<p><em>(그림 \d[^<]*)</em></p>", r'<p class="caption">\1</p>', inner)
    inner = inner.replace(
        "<p><strong>차별점 3줄</strong></p>", '<p class="lead-label">차별점 3줄</p>'
    )
    inner = add_colgroups(inner)

    if key in LAYOUT and LAYOUT[key].get("img"):
        inner = inner.replace("<img ", f'<img style="width:{LAYOUT[key]["img"]}" ', 1)

    def fit_pre(m: re.Match) -> str:
        code = m.group(1)
        cells = max_cells(strip_tags(code))
        avail_mm = 210 - 2 * 14 - 6  # 페이지 폭 - 좌우 여백 - pre 안쪽 여백
        limit = avail_mm / (cells * 0.1764) if cells else 99
        size = min(font_pt * 0.72, 7.55, limit)
        return f'<pre style="font-size:{size:.2f}pt"><code>{code}</code></pre>'

    inner = re.sub(r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>", fit_pre, inner, flags=re.S)

    if cover:
        return f'<section class="sheet cover" id="{key}">{inner}</section>'
    cls = "sheet airy" if airy else "sheet"
    return f'<section class="{cls}" id="{key}" style="font-size:{font_pt:.2f}pt">{inner}</section>'


# ---------------------------------------------------------------- css
CSS = """
@font-face {{ font-family: "BINT"; src: url("{kr}"); }}
@font-face {{ font-family: "BINTM"; src: url("{mono}"); }}

@page {{
  size: A4;
  margin: {mt}mm 14mm {mb}mm 14mm;
  @top-left {{
    content: "빈틈(BinTeum) · 제주 AI·빅데이터 활용 AI Agent 개발 챌린지";
    font-family: "BINT"; font-size: 7pt; color: #9aa8b0;
  }}
  @top-right {{
    content: string(kicker); font-family: "BINT"; font-size: 7pt; color: #0f6f63;
  }}
  @bottom-left {{
    content: "정민규 · gigaminkyu · 2026-11-16";
    font-family: "BINT"; font-size: 7pt; color: #9aa8b0;
  }}
  @bottom-right {{
    content: counter(page) " / " counter(pages);
    font-family: "BINT"; font-size: 7.5pt; color: #5b6b78;
  }}
}}
@page :first {{
  margin: 0;
  @top-left {{ content: none; }} @top-right {{ content: none; }}
  @bottom-left {{ content: none; }} @bottom-right {{ content: none; }}
}}

html {{ font-family: "BINT"; color: #16232b; line-height: 1.52; word-break: keep-all; overflow-wrap: break-word; }}
body {{ margin: 0; font-size: 9.5pt; }}

.sheet {{ break-before: page; }}
.sheet:first-of-type {{ break-before: auto; }}

h2 {{
  string-set: kicker attr(data-kicker);
  font-size: 1.68em; line-height: 1.22; margin: 0 0 3.2mm 0; padding: 0 0 2.1mm 0;
  color: #0d3b34; border-bottom: 0.9mm solid #0f6f63; letter-spacing: -0.02em;
}}
h3 {{
  font-size: 1.14em; margin: 3.2mm 0 1.5mm 0; color: #0f6f63;
  padding-left: 2.4mm; border-left: 1.1mm solid #7fd1c1; line-height: 1.34;
}}
p {{ margin: 0 0 1.9em 0; }}
strong {{ color: #0b2b26; }}
ul, ol {{ margin: 0 0 1.9em 0; padding-left: 5.2mm; }}
li {{ margin: 0 0 0.75em 0; }}
a {{ color: #0f6f63; text-decoration: none; }}
hr {{ display: none; }}

table {{
  width: 100%; border-collapse: collapse; margin: 1.5mm 0 2.6mm 0;
  font-size: 0.855em; line-height: 1.36;
}}
table.fit {{ table-layout: fixed; }}
thead {{ display: table-header-group; }}
th {{
  background: #e7f2f0; color: #0d3b34; text-align: left; font-weight: 700;
  border: 0.25mm solid #bcd4cf; padding: 1.4mm 1.7mm;
}}
td {{ border: 0.25mm solid #cfded9; padding: 1.3mm 1.7mm; vertical-align: top; }}
tbody tr:nth-child(even) td {{ background: #f7fbfa; }}

blockquote {{
  margin: 2mm 0 2.5mm 0; padding: 2.2mm 3mm; background: #eef7f5;
  border-left: 1mm solid #0f6f63; font-size: 0.93em; color: #1d3a36; break-inside: avoid;
}}
blockquote p {{ margin: 0 0 1em 0; }}
blockquote p:last-child {{ margin: 0; }}
blockquote.guide {{ background: #f4f7f6; border-left: 1mm solid #9db5b0; color: #33484a; }}

pre {{
  font-family: "BINTM"; font-size: 7.2pt; line-height: 1.42;
  background: #0f2229; color: #d6e8e4; padding: 2.6mm 3mm; margin: 1.5mm 0 2.5mm 0;
  border-radius: 1.2mm; white-space: pre; overflow: hidden; break-inside: avoid;
}}
code {{
  font-family: "BINTM"; font-size: 0.9em; background: #e8efee;
  padding: 0.2mm 0.7mm; border-radius: 0.6mm; color: #0b3b34;
}}
pre code {{ background: none; color: inherit; font-size: inherit; padding: 0; }}

img {{ max-width: 100%; display: block; margin: 1mm auto 1.3mm; }}
p.caption {{ font-size: 0.8em; color: #6b7a82; text-align: center; margin: -0.3mm 0 2.2mm; }}
p.notice {{
  font-size: 0.86em; background: #fdf6e9; border: 0.25mm solid #e8d3a8;
  padding: 2mm 2.6mm; border-radius: 1mm; color: #5a4212;
}}
p.lead-label {{ font-size: 0.94em; letter-spacing: 0.06em; color: #0f6f63; margin: 2mm 0 1em; }}

.airy {{ line-height: 1.86; }}
.airy p {{ margin-bottom: 2.7em; }}
.airy ul, .airy ol {{ margin-bottom: 2.6em; }}
.airy li {{ margin-bottom: 1.15em; }}
.airy h3 {{ margin: 5mm 0 2.2mm 0; }}
.airy table {{ margin: 2.2mm 0 3.6mm 0; font-size: 0.875em; }}
.airy td, .airy th {{ padding: 2mm 1.9mm; }}
.airy blockquote {{ margin: 2.8mm 0 3.4mm 0; padding: 2.8mm 3.4mm; }}

/* ---------- 보조 도식 ---------- */
table.chain {{ table-layout: fixed; margin: 3mm 0 1mm; }}
table.chain td {{
  border: none; border-top: 0.8mm solid #7fd1c1; background: #f7fbfa !important;
  padding: 2.2mm 2.4mm; font-size: 0.78em; color: #4a5f63; width: 25%;
}}
table.chain td + td {{ border-left: 2.4mm solid #ffffff; }}
table.chain b {{ display: block; font-size: 1.12em; color: #0d3b34; margin: 0.6mm 0 0.8mm; }}
table.chain .cn {{ font-size: 0.86em; letter-spacing: 0.08em; color: #0f6f63; font-weight: 700; }}

.wchart {{ margin: 3mm 0 1mm; }}
.wrow {{
  display: flex; align-items: center; margin: 0 0 1.6mm 0;
  font-size: 0.86em; color: #33484a;
}}
.wname {{ width: 46%; color: #0d3b34; }}
.wtrack {{ flex: 1; height: 3.2mm; background: #e7f2f0; border-radius: 0.6mm; margin: 0 2mm; }}
.wtrack i {{ display: block; height: 3.2mm; background: #0f6f63; border-radius: 0.6mm; }}
.w45 {{ width: 45%; }} .w25 {{ width: 25%; }} .w20 {{ width: 20%; }} .w10 {{ width: 10%; }}
.wval {{ width: 9mm; text-align: right; color: #0f6f63; font-weight: 700; }}

/* ---------- 표지 ---------- */
.sheet.cover {{ padding: 14mm 16mm 10mm 16mm; height: 297mm; box-sizing: border-box; }}
.cover h2 {{ display: none; }}
.cover .eyebrow {{
  font-size: 8pt; letter-spacing: 0.16em; color: #0f6f63; font-weight: 700;
  margin: 0 0 3mm 0; padding-bottom: 2mm; border-bottom: 0.25mm solid #cfe3df;
}}
.cover h3:nth-of-type(1) {{
  font-size: 33pt; color: #0d3b34; border: none; padding: 0; margin: 4mm 0 1.5mm;
  letter-spacing: -0.035em; line-height: 1.05;
}}
.cover h3:nth-of-type(2) {{
  font-size: 13pt; color: #0f6f63; border: none; padding: 0; margin: 0 0 4.5mm;
  letter-spacing: -0.01em;
}}
.cover blockquote {{
  background: none; border-left: none; padding: 0; margin: 0 0 4mm;
  font-size: 9.8pt; color: #37514d;
}}
.cover blockquote strong {{ color: #0d3b34; }}
.cover table {{ margin: 0 0 4.2mm; }}
.cover thead th {{
  background: #eff8f6; border: 0.25mm solid #cfe3df; font-size: 16pt;
  color: #0d3b34; text-align: left; padding: 2.2mm 3mm 0.8mm; border-bottom: none;
}}
.cover tbody td {{
  border: 0.25mm solid #cfe3df; background: #ffffff !important; color: #5b6b78;
  font-size: 7.6pt; padding: 0 3mm 2.2mm; border-top: none;
}}
.cover p.lead-label {{ margin: 0 0 1.6mm; font-size: 8.4pt; }}
.cover ol {{ font-size: 8.7pt; margin-bottom: 3.4mm; }}
.cover ol li {{ margin-bottom: 1.1mm; }}
.cover img {{
  width: 100% !important; border: 0.3mm solid #d7e2df; border-radius: 1.2mm; margin-top: 1.4mm;
}}
.cover p.caption {{ font-size: 7.2pt; margin: -0.4mm 0 2.4mm; }}
.cover blockquote:last-of-type {{
  font-size: 7.9pt; color: #4b5f66; background: #f4f8f7; border-left: 0.8mm solid #b9cfca;
  padding: 1.8mm 2.6mm; margin: 0 0 2.4mm;
}}
.cover p.notice {{ font-size: 7.4pt; }}
"""


# ---------------------------------------------------------------- assembly
@lru_cache(maxsize=1)
def page_head() -> str:
    css = CSS.format(kr=FONT_KR.as_uri(), mono=FONT_MONO.as_uri(),
                     mt=MARGIN_TOP_MM, mb=MARGIN_BOTTOM_MM)
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<title>빈틈(BinTeum) — 제주 여행의 빈 시간을 찾아주는 실측 혼잡 회피 Agent · 기획서</title>"
        "<meta name='author' content='정민규 (gigaminkyu)'>"
        "<meta name='description' content='제주 AI·빅데이터 활용 AI Agent 개발 챌린지 제출 기획서 (15p)'>"
        f"<style>{css}</style></head><body>"
    )


def norm(cfg) -> dict:
    return cfg if isinstance(cfg, dict) else {"size": float(cfg), "airy": False}


def cover_html() -> str:
    cover = section_html("p1", sections()["p1"], 9.6, cover=True)
    return cover.replace(
        "<h3>빈틈(BinTeum)</h3>",
        '<p class="eyebrow">제주 AI·빅데이터 활용 AI Agent 개발 챌린지 · 2026</p>\n'
        "<h3>빈틈(BinTeum)</h3>",
        1,
    )


def page_html(key: str, cfg) -> str:
    if key == "p1":
        return cover_html()
    c = norm(cfg)
    inner = section_html(key, sections()[key], c.get("size", 10.2), airy=c.get("airy", False))
    if key == "p2":
        inner = inner.replace("</h2>", "</h2>" + READING_GUIDE, 1)
    if key in EXTRA:
        inner = inner.replace("</section>", EXTRA[key] + "</section>")
    return inner


KEYS = ["p1"] + [f"p{n}" for n in range(2, 16)]


def build_page(key: str, cfg) -> str:
    return page_head() + page_html(key, cfg) + "</body></html>"


def build_all(sizes: dict) -> str:
    return page_head() + "".join(page_html(k, sizes.get(k, 10.2)) for k in KEYS) + "</body></html>"


def render(html: str):
    from weasyprint import HTML

    return HTML(string=html, base_url=str(ROOT / "docs")).render()


def page_metrics(pdf_path: Path, index: int = 0) -> tuple[int, float]:
    """(페이지 수, index 페이지의 내용이 끝나는 y(mm))"""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        n = len(doc)
        page = doc[index]
        bottom = 0.0
        for block in page.get_text("blocks"):
            y1 = block[3] * 0.3528
            if 10 < y1 < CONTENT_BOTTOM_MM - 2:
                bottom = max(bottom, y1)
        for info in page.get_image_info():
            y1 = info["bbox"][3] * 0.3528
            if 10 < y1 < CONTENT_BOTTOM_MM - 2:
                bottom = max(bottom, y1)
        return n, bottom


FILLER = '<section class="sheet" id="filler"><p>x</p></section>'


def autofit(resume: bool = False) -> dict[str, dict]:
    """섹션별로 1페이지에 들어가는 조합(여유 레이아웃 우선, 그다음 큰 글자)을 찾는다."""
    candidates = [10.6, 10.45, 10.3, 10.15, 10.0, 9.85, 9.7, 9.55]
    sizes: dict[str, dict] = {"p1": {"size": 9.6, "airy": False}}
    if resume and SIZES_JSON.exists():
        sizes.update(json.loads(SIZES_JSON.read_text()))
    tmp = ROOT / "dist" / ".fit.pdf"

    def fits(key: str, size: float, airy: bool) -> tuple[bool, float]:
        html = page_head() + FILLER + page_html(key, {"size": size, "airy": airy}) + "</body></html>"
        render(html).write_pdf(tmp)
        pages, bottom = page_metrics(tmp, index=1)
        return (pages == 2 and bottom <= CONTENT_BOTTOM_MM - 3.5), bottom / CONTENT_BOTTOM_MM

    for k in KEYS[1:]:
        if resume and k in sizes:
            print(f"  {k}: (kept) {sizes[k]['size']:.2f}pt airy={sizes[k]['airy']}", flush=True)
            continue
        best = None
        for size in candidates:
            for airy in (True, False):
                ok, fill = fits(k, size, airy)
                if ok:
                    best = {"size": size, "airy": airy, "fill": round(fill, 3)}
                    break
            if best:
                break
        sizes[k] = best or {"size": candidates[-1], "airy": False, "fill": 1.0}
        SIZES_JSON.write_text(json.dumps(sizes, indent=1))
        print(f"  {k}: {sizes[k]['size']:.2f}pt airy={sizes[k]['airy']} "
              f"fill={sizes[k]['fill']:.0%}", flush=True)
    tmp.unlink(missing_ok=True)
    return sizes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true", help="페이지별 레이아웃 자동 계산")
    ap.add_argument("--resume", action="store_true", help="--fit 시 이미 계산된 페이지는 건너뛴다")
    ap.add_argument("--png", action="store_true", help="페이지별 PNG 미리보기")
    args = ap.parse_args()

    sizes: dict = {}
    if SIZES_JSON.exists():
        sizes = json.loads(SIZES_JSON.read_text())
    if args.fit:
        print("fitting page layouts ...")
        sizes = autofit(resume=args.resume)
        SIZES_JSON.write_text(json.dumps(sizes, indent=1))

    html = build_all(sizes)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    doc = render(html)
    print(f"pages: {len(doc.pages)}")
    doc.write_pdf(OUT_PDF)
    print(f"wrote {OUT_PDF} ({OUT_PDF.stat().st_size / 1024:.1f} KB)")

    if args.png:
        import pymupdf

        png_dir = ROOT / "dist" / "preview"
        png_dir.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(OUT_PDF) as pdf:
            for i, page in enumerate(pdf, 1):
                page.get_pixmap(dpi=110).save(png_dir / f"page{i:02d}.png")
        print(f"png -> {png_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
