# -*- coding: utf-8 -*-
"""content.py 로 기획서 DOCX와 PDF(HTML 경유)를 만든다."""
import os, sys, html, json
sys.path.insert(0, os.path.dirname(__file__))
from content import BLOCKS, TITLE, SUBTITLE, HEAD, META

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT_DOCX = os.path.join(os.path.dirname(__file__), '03_기획서_올팍주차나침반_정민규.docx')
OUT_HTML = os.path.join(os.path.dirname(__file__), 'plan_print.html')

def img_abs(p):
    return os.path.join(BASE, p)

# ---------------------------------------------------------------- DOCX
def build_docx():
    from docx import Document
    from docx.shared import Pt, Mm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    NAVY = RGBColor(0x0E, 0x2A, 0x47)
    SUB = RGBColor(0x33, 0x47, 0x5B)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin = sec.bottom_margin = Mm(17)
    sec.left_margin = sec.right_margin = Mm(18)

    st = doc.styles['Normal']
    st.font.name = '맑은 고딕'
    st.font.size = Pt(10)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), '맑은 고딕')
    st.paragraph_format.line_spacing = 1.34
    st.paragraph_format.space_after = Pt(3)

    def add_runs(p, text, size=10, bold=False, color=None):
        r = p.add_run(text)
        r.font.size = Pt(size); r.bold = bold
        r.font.name = '맑은 고딕'
        r._element.rPr.rFonts.set(qn('w:eastAsia'), '맑은 고딕')
        if color: r.font.color.rgb = color
        return r

    def hr(p):
        pPr = p._p.get_or_add_pPr()
        pbdr = OxmlElement('w:pBdr'); bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), '8')
        bottom.set(qn('w:space'), '1'); bottom.set(qn('w:color'), '0E2A47')
        pbdr.append(bottom); pPr.append(pbdr)

    def shade(cell, hexcolor):
        tcPr = cell._tc.get_or_add_tcPr()
        sh = OxmlElement('w:shd'); sh.set(qn('w:val'), 'clear')
        sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), hexcolor)
        tcPr.append(sh)

    for kind, payload in BLOCKS:
        if kind == 'cover':
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(6)
            add_runs(p, HEAD, 11, False, SUB)
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(10)
            add_runs(p, TITLE, 26, True, NAVY)
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_runs(p, SUBTITLE, 12, False, SUB)
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(12)
            add_runs(p, META, 9, False, SUB)
            hr(p)
        elif kind == 'pagebreak':
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif kind == 'h1':
            p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(6)
            add_runs(p, payload, 15, True, NAVY)
        elif kind == 'h2':
            p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(3)
            add_runs(p, payload, 12, True, NAVY)
        elif kind == 'h3':
            p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(6); p.paragraph_format.space_after = Pt(2)
            add_runs(p, payload, 10.5, True, RGBColor(0x17, 0x3D, 0x63))
        elif kind == 'p':
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            add_runs(p, payload, 10)
        elif kind == 'formula':
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(4)
            add_runs(p, payload, 11.5, True, NAVY)
        elif kind == 'bullets':
            for it in payload:
                p = doc.add_paragraph(style='List Bullet')
                p.paragraph_format.left_indent = Mm(5)
                p.paragraph_format.first_line_indent = Mm(-3.5)
                p.paragraph_format.space_after = Pt(1.5)
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                add_runs(p, it, 9.6)
        elif kind == 'table':
            cols, rows, widths = payload['cols'], payload['rows'], payload.get('widths')
            t = doc.add_table(rows=1, cols=len(cols))
            t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, c in enumerate(t.rows[0].cells):
                c.text = ''
                pr = c.paragraphs[0]; pr.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_runs(pr, cols[i], 8.8, True, NAVY)
                shade(c, 'EDF2F9')
            for row in rows:
                cells = t.add_row().cells
                for i, v in enumerate(row):
                    cells[i].text = ''
                    pr = cells[i].paragraphs[0]
                    add_runs(pr, v, 8.6)
            if widths:
                for r in t.rows:
                    for i, w in enumerate(widths):
                        r.cells[i].width = Mm(w)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
        elif kind == 'image':
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(2)
            p.add_run().add_picture(img_abs(payload['path']), width=Mm(payload.get('width', 165)))
            cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(6)
            add_runs(cap, payload.get('caption', ''), 8.2, False, SUB)

    doc.save(OUT_DOCX)
    return OUT_DOCX

# ---------------------------------------------------------------- HTML → PDF
CSS = """
@page { size: A4; margin: 17mm 18mm; }
* { box-sizing: border-box; }
body { font-family: 'Noto Sans CJK KR','Malgun Gothic',sans-serif; font-size: 10pt; line-height: 1.5;
       color:#16202B; margin:0; }
.cover { text-align:center; border-bottom:2px solid #0E2A47; padding-bottom:8px; margin-bottom:10px; }
.cover .h { font-size:11pt; color:#33475B; }
.cover .t { font-size:26pt; font-weight:800; color:#0E2A47; margin:8px 0 4px; }
.cover .s { font-size:12pt; color:#33475B; }
.cover .m { font-size:9pt; color:#5C6B7A; margin-top:8px; }
h1 { font-size:15pt; color:#0E2A47; margin:6px 0 8px; }
h2 { font-size:12pt; color:#0E2A47; margin:12px 0 4px; }
h3 { font-size:10.5pt; color:#173D63; margin:9px 0 3px; }
p { margin:0 0 5px; text-align:justify; }
ul { margin:2px 0 6px; padding-left:16px; }
li { margin-bottom:2.5px; font-size:9.6pt; text-align:justify; }
.formula { text-align:center; font-weight:700; color:#0E2A47; font-size:11.5pt; margin:6px 0; }
table { border-collapse:collapse; width:100%; margin:4px 0 8px; }
th,td { border:0.5pt solid #9AA7B4; padding:3px 4px; font-size:8.6pt; vertical-align:top; }
th { background:#EDF2F9; color:#0E2A47; text-align:center; font-size:8.8pt; }
figure { margin:6px 0 8px; text-align:center; page-break-inside:avoid; }
figure img { max-width:100%; }
figcaption { font-size:8.2pt; color:#5C6B7A; margin-top:2px; }
.pb { page-break-after:always; }
"""

def build_html():
    parts = ['<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>%s</style></head><body>' % CSS]
    for kind, payload in BLOCKS:
        if kind == 'cover':
            parts.append(f'<div class="cover"><div class="h">{html.escape(HEAD)}</div>'
                         f'<div class="t">{html.escape(TITLE)}</div>'
                         f'<div class="s">{html.escape(SUBTITLE)}</div>'
                         f'<div class="m">{html.escape(META)}</div></div>')
        elif kind == 'pagebreak':
            parts.append('<div class="pb"></div>')
        elif kind in ('h1', 'h2', 'h3'):
            parts.append(f'<{kind}>{html.escape(payload)}</{kind}>')
        elif kind == 'p':
            parts.append(f'<p>{html.escape(payload)}</p>')
        elif kind == 'formula':
            parts.append(f'<div class="formula">{html.escape(payload)}</div>')
        elif kind == 'bullets':
            parts.append('<ul>' + ''.join(f'<li>{html.escape(x)}</li>' for x in payload) + '</ul>')
        elif kind == 'table':
            th = ''.join(f'<th>{html.escape(c)}</th>' for c in payload['cols'])
            trs = ''.join('<tr>' + ''.join(f'<td>{html.escape(c)}</td>' for c in r) + '</tr>' for r in payload['rows'])
            parts.append(f'<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
        elif kind == 'image':
            src = 'file://' + img_abs(payload['path'])
            w = payload.get('width', 165)
            parts.append(f'<figure><img src="{src}" style="width:{w}mm">'
                         f'<figcaption>{html.escape(payload.get("caption",""))}</figcaption></figure>')
    parts.append('</body></html>')
    open(OUT_HTML, 'w').write('\n'.join(parts))
    return OUT_HTML

if __name__ == '__main__':
    print(build_docx())
    print(build_html())
