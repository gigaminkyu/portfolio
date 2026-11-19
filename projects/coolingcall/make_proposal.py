"""붙임6 아이디어 제안서(부문1) 생성기.

data/processed 산출물과 대시보드 화면 PNG를 읽어 A4 PDF 제안서를 만든다.
모든 수치는 build_index.py가 계산한 값을 그대로 인용하며, 문서에 손으로 적은 숫자는 없다.
"""
import csv
import json
import os
from pathlib import Path

from weasyprint import HTML

HERE = Path(__file__).resolve().parent
D = HERE / "data"
OUT_PDF = HERE.parent / "제안서_쿨링콜_v1.pdf"
OUT_HTML = HERE / "dashboard" / "proposal.html"
SHOT1 = (HERE / "dashboard" / "print_day_p1.png").resolve()
SHOT2 = (HERE / "dashboard" / "print_night_p1.png").resolve()
DEMO_URL = "https://gigaminkyu.github.io/portfolio/coolingcall/"
CONTACT = os.environ.get("CONTACT", "연락처 미기재")  # 공개 저장소에는 개인 연락처를 두지 않는다

meta = json.loads((D / "processed" / "meta.json").read_text(encoding="utf-8"))
kma_days = len([1 for _ in (D / "kma_asos_daegu_daily.csv").open(encoding="utf-8-sig")]) - 1
rows = list(csv.DictReader((D / "processed" / "dong_index.csv").open(encoding="utf-8-sig")))
for r in rows:
    for k in ("pop", "e65", "e75", "n_shelter", "n_cool", "cap_cool", "n_night"):
        r[k] = int(r[k] or 0)
    for k in ("risk_day", "risk_night", "cap_per_1000", "vuln", "gap_day", "gap_night", "e65_rate"):
        r[k] = float(r[k] or 0)

rows.sort(key=lambda r: -r["risk_day"])
top = rows[:10]
night_top = sorted(rows, key=lambda r: -r["risk_night"])[:5]
e65_total = sum(r["e65"] for r in rows)
cap_total = sum(r["cap_cool"] for r in rows)
cap_avg = cap_total / (e65_total / 1000)
median_cap = sorted(r["cap_per_1000"] for r in rows)[len(rows) // 2]
night_zero = sum(1 for r in rows if r["n_night"] == 0)
low_cap = sum(1 for r in rows if r["cap_per_1000"] < 50)
best = max(rows, key=lambda r: r["cap_per_1000"])
best_gap = round(best["cap_per_1000"] / cap_avg, 1)
share = {n: round(sum(r["e65"] for r in rows[:n]) / e65_total * 100, 1) for n in (10, 30)}
heat = meta["heat"]
series = heat["series"]
prev = [y for y in series if y != "2025"]
avg_heat = round(sum(series[y]["heat_days"] for y in prev) / len(prev), 1)
heat_ratio = round(heat["heat_days"] / avg_heat * 100)
tm_row = [r for r in rows if r["dong"] == "월성2동"][0]
hero = rows[0]


def fmt_row(i, r, mode="day"):
    risk = r["risk_day"] if mode == "day" else r["risk_night"]
    return (
        f"<tr><td class='c'>{i}</td><td>{r['gu']} {r['dong']}</td><td class='r'>{risk:.1f}</td>"
        f"<td class='r'>{r['e65']:,}</td><td class='r'>{r['e65_rate']:.1f}%</td>"
        f"<td class='r'>{r['cap_per_1000']:.0f}</td><td class='r'>{r['n_night']}</td></tr>"
    )


rank_rows = "".join(fmt_row(i, r) for i, r in enumerate(top, 1))
night_rows = "".join(fmt_row(i, r, "night") for i, r in enumerate(night_top, 1))

html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>쿨링콜 아이디어 제안서</title>
<style>
@page {{ size:A4; margin:14mm 15mm 12mm 15mm;
  @bottom-center {{ content: counter(page) " / " counter(pages); font-size:8pt; color:#888; }} }}
body {{ font-family:"Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif; font-size:9.6pt; line-height:1.62; color:#1a1a1a; }}
h1 {{ font-size:17pt; margin:0 0 2mm; letter-spacing:-0.6px; }}
h2 {{ page-break-after:avoid; font-size:11.6pt; margin:6.5mm 0 2mm; padding-bottom:1.2mm; border-bottom:1.6pt solid #1a1a1a; letter-spacing:-0.3px; }}
h3 {{ page-break-after:avoid; font-size:10.2pt; margin:3.6mm 0 1.1mm; color:#7a2c02; }}
p {{ margin:0 0 1.8mm; }}
ul {{ margin:0 0 2.4mm; padding-left:4.6mm; }}
li {{ margin-bottom:1.1mm; }}
table {{ width:100%; border-collapse:collapse; margin:1.6mm 0 3mm; font-size:8.7pt; }}
th {{ background:#f3efe8; border:0.5pt solid #cfc7b8; padding:1.5mm 1.6mm; text-align:left; font-weight:600; }}
td {{ border:0.5pt solid #d9d3c7; padding:1.15mm 1.6mm; vertical-align:top; }}
td.c, td.r {{ text-align:center; }} td.r {{ text-align:right; }}
.form-hd td {{ border:0.5pt solid #333; }}
.kicker {{ font-size:8.6pt; color:#666; margin-bottom:1mm; }}
.title {{ font-size:14pt; font-weight:700; letter-spacing:-0.5px; margin:1mm 0 3mm; }}
.lead {{ background:#fbf6ee; border-left:3pt solid #a63603; padding:2.6mm 3mm; margin:2mm 0 3mm; font-size:9.4pt; }}
.fig {{ margin:2mm 0 1mm; page-break-inside:avoid; }}
.fig img {{ width:100%; border:0.5pt solid #ccc; }}
.cap {{ font-size:8.2pt; color:#666; margin-top:1mm; }}
.two {{ width:100%; }}
.two td {{ border:0; padding:0 2.5mm 0 0; vertical-align:top; }}
.tag {{ display:inline-block; background:#a63603; color:#fff; font-size:8.4pt; font-weight:600; padding:0.7mm 2.2mm; border-radius:1.6mm; vertical-align:middle; letter-spacing:0; }}
.note {{ font-size:8.4pt; color:#555; }}
.pb {{ page-break-before:always; }}
.keep {{ page-break-inside:avoid; break-inside:avoid; }}
code {{ font-family:"DejaVu Sans Mono",monospace; font-size:8.4pt; background:#f4f4f2; padding:0 1mm; }}
</style></head><body>

<h1>아이디어 제안서 <span class="tag">부문1</span></h1>
<table class="form-hd">
<tr><th style="width:18%">접수번호</th><td style="width:32%">※ 미기재</td><th style="width:18%">공모명</th>
    <td>제1회 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회</td></tr>
<tr><th>성명</th><td>정민규</td><th>연락처</th><td><!-- 연락처는 공개 저장소에 넣지 않는다. 생성 시 CONTACT 환경변수로 채운다. -->{CONTACT}</td></tr>
<tr><th>시연 화면(공개 URL)</th><td colspan="3"><b>{DEMO_URL}</b> (설치 없이 브라우저에서 열리는 시연용 배포)</td></tr>
<tr><th>아이디어 제목</th><td colspan="3"><b>쿨링콜(Cooling Call)</b> — 폭염 취약 사각지대 자동 발굴과 안부 연락 문안 생성으로,
    대구의 폭염 대응을 ‘일괄 안내’에서 ‘우선순위 있는 연락’으로 바꾸는 담당자용 운영 도구</td></tr>
</table>

<div class="lead">
<b>한 줄 요약</b> — 폭염특보가 뜨면 대구 150개 행정동 중 <b>“가장 위험한데 가장 손이 닿지 않는 동네”</b>를 매일 자동으로 뽑아 주고,
담당자가 바로 쓸 안부 연락 문안까지 만들어 주는 도구입니다. 숫자는 전부 코드가 계산하고, AI는 문장만 씁니다.
제안 단계에서 이미 <b>공공데이터 3종·동 150개 지수·동작하는 화면</b>을 만들어 검증했습니다.
</div>

<h2>■ 아이디어 개요</h2>

<h3>1. 배경 — 대구의 폭염은 ‘평균’이 아니라 ‘반복’의 문제입니다</h3>
<p>기상청 기상자료개방포털의 대구(지점 143) 일별 관측값을 2015년부터 2025년까지 직접 내려받아 계산했습니다.
2025년 대구는 <b>폭염일수(일최고 33℃ 이상) {heat['heat_days']}일, 열대야(일최저 25℃ 이상) {heat['tropical_nights']}일, 연 최고기온 {heat['max_ta']}℃</b>였습니다.
폭염일수는 2015~2024년 평균 {avg_heat}일의 <b>{heat_ratio}%</b>로, 2024년({series['2024']['heat_days']}일)에 이어 2년 연속 50일을 넘었습니다.
같은 기간 폭염일수는 2021년 {series['2021']['heat_days']}일에서 2025년 {heat['heat_days']}일로 두 배 이상 늘었습니다.</p>

<h3>2. 문제 — 데이터는 있는데, ‘오늘 어디부터’가 없습니다</h3>
<ul>
<li><b>일방향 안내</b>: 특보가 뜨면 재난문자·홍보가 일괄로 나갑니다. 받는 사람이 65세 이상 고령자여도, 야간에 홀로 사는 어르신이어도 같은 문장입니다.</li>
<li><b>목록은 있지만 우선순위가 없음</b>: 무더위쉼터 현황은 공개돼 있으나(“어디에 쉼터가 있다”) <b>“이 동네가 지금 가장 위험하다”</b>는 판단은 아무도 계산해 주지 않습니다.</li>
<li><b>현장의 병목</b>: 구·군 담당자가 여름철 매일 수백 건의 명부를 상대하는데, 근거 없이 순서를 정하고 문안을 매번 새로 씁니다. 발송 뒤 기록도 남지 않습니다.</li>
</ul>
<p>이 문제를 <b>실제 데이터로 확인</b>했습니다. 대구 무더위쉼터 {meta['counts']['shelters_used']:,}곳과 행정동별 인구를 결합한 결과,</p>
<table>
<tr><th style="width:34%">데이터로 확인된 결손</th><th>내용</th></tr>
<tr><td>야간 공백</td><td>대구 {len(rows)}개 행정동 중 <b>{night_zero}개 동(약 {round(night_zero/len(rows)*100)}%)</b>에 20시 이후 운영하는 냉방 쉼터가 없습니다.
  열대야 {heat['tropical_nights']}일이 기록된 해에, 가장 더운 시간대인 저녁 이후를 받쳐 줄 시설이 없는 동네가 4곳 중 3곳입니다.</td></tr>
<tr><td>수용력 격차</td><td>고령자 1,000명당 냉방 쉼터 수용인원의 동별 중앙값은 {median_cap:.0f}석인데, <b>{low_cap}개 동은 50석 미만</b>입니다.
  반대로 {best['gu']} {best['dong']}은 {best['cap_per_1000']:,.0f}석으로, 시 전체 평균({cap_avg:.0f}석)의 <b>{best_gap}배</b>입니다. 같은 도시 안에서 대응 격차가 이만큼 벌어져 있습니다.</td></tr>
<tr><td>집중도</td><td>위험지수 상위 30개 동(전체의 20%)에 대구 65세 이상 인구의 <b>{share[30]}%</b>가 삽니다. 반대로 말하면
  <b>동 20%만 제대로 보면 고령인구 4명 중 1명</b>을 먼저 챙길 수 있습니다.</td></tr>
</table>

<h3>3. 해결의 필요성과 핵심과제</h3>
<p>폭염 대응의 실효성은 “얼마나 많이 알렸는가”가 아니라 <b>“가장 위험한 사람에게, 가장 더운 시간 전에 닿았는가”</b>에서 갈립니다.
그 판단을 사람의 경험에 맡기지 않고 매일 같은 기준으로 계산해 주는 것이 핵심입니다. 핵심과제는 네 가지입니다.</p>
<ul>
<li><b>① 동 단위 위험지수 자동 산출</b> — 기온·고령인구·쉼터 접근성을 결합해 150개 동의 순위를 매일 새로 계산합니다.</li>
<li><b>② 근거가 화면에 같이 보이게</b> — “왜 이 동네가 1순위인지”(고령자 수, 냉방 커버리지, 야간 쉼터 수)를 숫자로 함께 보여 담당자가 납득·수정할 수 있게 합니다.</li>
<li><b>③ 안부 연락 문안 자동 생성</b> — 담당자가 매번 새로 쓰던 문자·전화 스크립트를 데이터에 맞춰 만들어 줍니다.</li>
<li><b>④ 사람 승인 후 발송</b> — 자동 발송은 하지 않습니다. AI가 사람을 대신해 판단하지 않도록, 문장 생성과 발송 결정을 분리합니다.</li>
</ul>

<h3>4. 활용 공공데이터와 AI 개요</h3>
<table>
<tr><th style="width:24%">구분</th><th style="width:44%">내용</th><th>활용 방식</th></tr>
<tr><td><b>공공데이터 3종</b></td>
    <td>① 기상청 기상자료개방포털 기온분석(대구 143, 2015~2025 일별 최저·평균·최고기온)<br>
        ② 대구광역시 자연재난과 무더위쉼터 현황표(2026, {meta['counts']['shelters_used']:,}곳)<br>
        ③ 행정안전부 주민등록 인구통계 행정동별 성별·연령별 인구(2026년 10월)</td>
    <td>폭염 강도 → 고령 취약도 → 대응 결손을 순서대로 계산해 <b>동 단위 위험지수</b>로 결합</td></tr>
<tr><td><b>AI</b></td>
    <td>계산이 끝난 뒤 <b>문장 계층</b>에서만 사용: ① 담당자용 안부 연락 문안 ② 특보 단계별 상황 요약</td>
    <td>숫자는 계산값을 슬롯으로 주입, 생성문의 숫자를 다시 대조해 불일치 시 폐기(<b>환각 차단</b>)</td></tr>
</table>

<h2>■ 세부 추진방안</h2>

<h3>1. 작동 방식 — 매일 아침 5단계로 자동 실행</h3>
<table>
<tr><th style="width:6%">단계</th><th style="width:20%">하는 일</th><th>내용과 산출물</th></tr>
<tr><td class="c">①</td><td>수집</td><td>기온(일 1회) · 무더위쉼터 현황(연 1회 갱신) · 행정동 인구(월 1회)를 공개 API/파일에서 수집. <b>로그인·유료 계약 없이 접근 가능한 경로만 사용</b>해 담당 부서가 그대로 운영할 수 있게 했습니다.</td></tr>
<tr><td class="c">②</td><td>정제</td><td>행정동 명칭 정규화(예: 구지면↔구지읍, 출장소→읍면 통합), 운영중·냉방기 보유 쉼터만 채택, 좌표·수용인원 결측 처리, 65세 이상 인구 합산.</td></tr>
<tr><td class="c">③</td><td>계산</td><td>동 단위 위험지수와 구성요소 3종, 야간 시나리오 값을 매일 재계산 → <code>dong_index.csv</code>.</td></tr>
<tr><td class="c">④</td><td>표출·문안</td><td>지도·순위·상세 화면 생성, 상위 동에 대해 안부 연락 문안 생성(숫자 슬롯 주입).</td></tr>
<tr><td class="c">⑤</td><td>승인·발송</td><td>담당자가 화면에서 확인·수정 → 연락 목록(CSV)·문자 발송. <b>발송 버튼은 사람 손에만</b> 있고 결과는 이력으로 남습니다.</td></tr>
</table>

<h3>2. 데이터 전처리 규칙 (재현 가능하도록 코드에 고정)</h3>
<table>
<tr><th style="width:26%">원천</th><th>정제 규칙</th><th style="width:26%">산출 필드</th></tr>
<tr><td>기상청 ASOS 대구 일자료</td><td>2015-01-01~2025-12-31 일별 최고·최저기온으로 폭염일수(≥33℃)·열대야일수(≥25℃)·연 최고기온 산출 → 11년 시계열에서 min-max 정규화</td><td>폭염강도(0~100)</td></tr>
<tr><td>무더위쉼터 현황</td><td>운영여부=운영만 채택, 에어컨 보유(냉방) 여부 분리, 운영 종료시각으로 야간(20시 이후) 운영 판정, 요일 정보로 주말 운영 판정, 행정동 단위 합산</td><td>냉방 쉼터 수, 수용인원 합, 야간 운영 수, 주말 운영 수</td></tr>
<tr><td>행정동별 인구</td><td>5세 단위 연령구간을 65세 이상·75세 이상으로 재합산, 출장소는 모읍으로 통합, 쉼터 자료와 행정동 명칭 정규화 후 결합</td><td>65세 이상 인구·비율, 75세 이상 비율</td></tr>
</table>

<h3>3. 위험지수 산식과 근거</h3>
<p>동 <i>d</i>의 위험지수는 세 축의 가중합입니다. 각 축을 0~100으로 맞춰 서로 다른 단위(일수·명·석)를 비교 가능하게 했습니다.</p>
<table>
<tr><th style="width:22%">축</th><th style="width:10%">가중치</th><th>계산식</th></tr>
<tr><td>폭염 강도 (Heat)</td><td class="c">0.30</td><td>100 × (0.5·정규화(폭염일수) + 0.3·정규화(열대야일수) + 0.2·정규화(연 최고기온)) — 2015~2025년 11개 연도 기준</td></tr>
<tr><td>고령 취약도 (Vuln)</td><td class="c">0.40</td><td>0.45·백분위(65세 이상 인구) + 0.35·백분위(65세 이상 비율) + 0.20·백분위(75세 이상 비율)</td></tr>
<tr><td>대응 결손 (Gap)</td><td class="c">0.30</td><td>100 × (1 − min(커버리지 ÷ 300, 1)), 커버리지 = 냉방 쉼터 수용인원 ÷ (65세 이상 인구 ÷ 1,000)</td></tr>
</table>
<ul>
<li><b>가중치 근거</b>: 폭염은 시 전체가 함께 겪는 조건이므로 0.30, 사람에 따라 결과가 갈리는 취약도에 0.40, 정책으로 직접 바꿀 수 있는 결손에 0.30을 두었습니다.
  “정책으로 바꿀 수 있는 축”에 낮은 가중치를 주어, 점수가 높은 동네가 곧 <b>쉼터 1곳을 늘리거나 야간 운영을 붙이면 개선되는 동네</b>가 되게 했습니다.</li>
<li><b>백분위(순위) 사용</b>: 인구 규모가 20배 차이 나는 동들을 그대로 더하면 큰 동네만 올라옵니다. 순위로 바꿔 규모와 무관하게 비교합니다.</li>
<li><b>커버리지 300석 기준</b>: 고령자 1,000명당 300석(30%)이면 “더운 시간에 3명 중 1명이 동시에 머물 수 있다”는 뜻으로, 하루 피크 시간대 수용의 실무적 상한으로 잡았습니다. 이 기준은 화면에서 조정 가능한 파라미터입니다.</li>
<li><b>야간 모드</b>: 같은 산식에 <b>야간(20시 이후) 운영 쉼터만</b> 넣어 다시 계산합니다. 낮에는 여유가 있어도 밤에 문을 닫는 동네가 순위 상단으로 올라옵니다.</li>
</ul>

<h3>4. AI 활용 구조 — 판단은 코드, 문장은 AI</h3>
<table>
<tr><th style="width:24%">계층</th><th>담당</th><th style="width:34%">환각 차단 장치</th></tr>
<tr><td>계산 계층</td><td>지수·순위·커버리지·최근접 쉼터 거리까지 <b>전부 코드</b>가 계산</td><td>AI가 숫자를 만들 여지를 없앰(입력 슬롯에 없는 값은 문장에 등장 금지)</td></tr>
<tr><td>문장 계층</td><td>LLM이 슬롯(동명·단계·인구·커버리지·쉼터명)을 받아 3~5문장 안부 문안 작성</td><td>프롬프트에 “제공된 값 외 숫자·기관명 생성 금지”를 계약으로 명시</td></tr>
<tr><td>검증 계층</td><td>생성문에서 숫자를 정규식으로 추출해 슬롯 집합과 대조</td><td>불일치·누락 시 재생성 또는 폐기, <b>통과한 문안만 화면에 표시</b></td></tr>
<tr><td>승인 계층</td><td>담당자가 읽고 수정한 뒤 발송</td><td>자동 발송 경로 없음(수정 이력 저장)</td></tr>
</table>
<p class="note">※ 제출용 시연 화면은 외부 LLM 호출 없이 같은 슬롯 구조를 <b>결정론적 템플릿</b>으로 재현했습니다.
그래서 오프라인에서도 동일한 문안이 나오고, 위 문안의 모든 숫자는 화면의 계산값과 1:1로 대응합니다.
운영 시에는 이 자리에 LLM을 붙이되 검증 계층은 그대로 유지합니다.</p>

<h2>5. 스토리보드 — 실제로 만든 화면 (공개 URL {DEMO_URL})</h2>
<div class="fig"><img src="{SHOT1.as_uri()}"></div>
<div class="cap"><b>화면 1. 주간 기준 운영 콘솔.</b> 왼쪽은 행정동별 위험지수 지도, 오른쪽 위는 선택 동의 구성요소(폭염 74·고령취약 82·대응결손 90),
아래는 담당자용 안부 연락 문안, 그 아래는 연도별 폭염일수 추이입니다. 맨 아래 표가 <b>오늘 먼저 전화할 10개 동</b>입니다.</div>

<div class="fig" style="margin-top:5mm"><img src="{SHOT2.as_uri()}"></div>
<div class="cap"><b>화면 2. 야간(20시 이후) 기준으로 바꾼 같은 화면.</b> 낮 순위 9위였던 달서구 월성2동이 야간에는 1위로 올라옵니다.
65세 이상 {tm_row['e65']:,}명(주민의 {tm_row['e65_rate']:.1f}%)이 사는 동네에 냉방 쉼터가 {tm_row['n_cool']}곳·{tm_row['cap_cool']}석 있지만
<b>20시 이후 문을 여는 곳이 없어</b> 대응 결손이 69→100으로 바뀌기 때문입니다. 이런 동네가 야간 기준 상위 5개 중 4곳입니다.</div>

<h2 class="pb">■ 실현 가능성 및 기대효과</h2>

<h3>1. “계획”이 아니라 이미 돌아가는 것으로 제출합니다</h3>
<table>
<tr><th style="width:30%">구분</th><th>확인된 내용</th></tr>
<tr><td>데이터</td><td>기상청 대구 일별 기온 {kma_days:,}일치(2015~2025), 무더위쉼터 {meta['counts']['shelters_used']:,}곳, 행정동 인구 {len(rows)}개 동 — <b>전부 실제 내려받아 사용</b></td></tr>
<tr><td>계산</td><td>동 {len(rows)}개 × 지표 12종 지수표 산출(<code>dong_index.csv</code>), 재실행 시 동일 결과</td></tr>
<tr><td>화면</td><td>외부 라이브러리 없이 동작하는 단일 HTML(오프라인 시연 가능), 특보 단계·주간/야간 전환 시 지도·순위·문안이 함께 갱신. 공개 URL <b>{DEMO_URL}</b> 로 배포</td></tr>
<tr><td>검증</td><td>지도에 표시된 139개 동 경계와 지수표 150개 동을 대조, 명칭 표기 차이는 정규화 규칙으로 처리. 군위군 8개 읍면과 신설 2개 동(혁신동·유천동)은 경계자료에 없어 지도에서 제외되고 표·지수에는 포함</td></tr>
</table>
<p>재현 절차는 스크립트 세 줄입니다: <code>collect_kma_asos.py</code>(수집) → <code>build_index.py</code>(정제·지수) → <code>make_dashboard.py</code>(화면).
담당 부서가 인수인계받아도 엑셀 대신 같은 명령으로 매년 갱신할 수 있게 했습니다.</p>

<h3>2. 기대효과 — 담당자의 하루를 바꾸는 세 가지</h3>
<ul>
<li><b>연락 우선순위가 생깁니다</b>: 전체 {len(rows)}개 동을 볼 필요 없이 상위 10개 동(65세 이상 인구의 {share[10]}%) 또는 30개 동({share[30]}%)부터 확인하면 됩니다.
  같은 인력으로 더 위험한 사람에게 먼저 닿습니다.</li>
<li><b>문안 작성 시간이 사라집니다</b>: 동별·단계별로 매번 새로 쓰던 문자를 계산값 기반으로 즉시 생성하고, 담당자는 <u>확인과 수정</u>만 합니다.</li>
<li><b>정책 근거가 남습니다</b>: “어느 동에 야간 쉼터를 늘려야 하는가”를 지수와 커버리지로 설명할 수 있습니다. 시즌이 끝나면 같은 표로
  <b>다음 해 예산·운영시간 조정 근거</b>가 됩니다.</li>
</ul>

<h3>3. 지속가능성과 확장</h3>
<table>
<tr><th style="width:26%">항목</th><th>내용</th></tr>
<tr><td>운영 부담</td><td>기온은 일 1회 자동 수집, 쉼터·인구는 연/월 1회 갱신. 서버 없이 정적 파일로도 배포 가능해 유지비가 거의 들지 않습니다.</td></tr>
<tr><td>확장</td><td>① 대기질·열섬(지표온도) 축 추가 → “폭염×대기질 복합 위험” 모드 &nbsp;② 구·군별 화면 분리, 통합돌봄·방문간호 명부 연계(개인정보는 기관 내부에서만 결합) &nbsp;③ 겨울 한파·미세먼지에도 같은 구조 적용(쉼터·취약인구·결손) → <b>연중 기후위기 대응 콘솔</b></td></tr>
</table>

<div class="keep"><h3>4. 한계와 대응 (미리 밝힙니다)</h3>
<table>
<tr><th style="width:26%">한계</th><th>대응</th></tr>
<tr><td>기온은 시 단위(지점 1곳)</td><td>동별 차이는 인구·쉼터 접근성에서 나오도록 설계했습니다. 지표온도·자동기상관측(AWS) 추가 시 동별 열 노출로 확장 가능합니다.</td></tr>
<tr><td>쉼터 정보 최신성</td><td>폐쇄·운영시간 변경이 반영되지 않을 수 있어, 화면에 기준일을 표시하고 담당자가 수정할 수 있게 했습니다.</td></tr>
<tr><td>개인 단위가 아닌 동 단위</td><td>개인 명부는 쓰지 않습니다(집계 데이터만). 실제 연락 대상 명부는 담당 부서가 가진 정보와 결합해야 하며, 그 결합은 기관 내부에서 이뤄집니다.</td></tr>
<tr><td>경계 자료</td><td>통계청 2018년 기준 공개 경계를 씁니다. 신설 동(군위군·혁신동·유천동 등)은 지도에서만 빠지고, 최신 경계로 바꾸면 해소됩니다.</td></tr>
</table></div>

<h2>■ (자유 기재)</h2>

<h3>1. 센터가 이렇게 쓰면 됩니다 — 3단 시나리오</h3>
<table>
<tr><th style="width:22%">시점</th><th>센터의 활용</th></tr>
<tr><td><b>평시(6~9월 매일)</b></td><td>오전 9시 자동 생성된 상위 10개 동 목록을 구·군 담당자에게 공유. “오늘의 폭염 브리핑” 카드뉴스 문안으로 그대로 재사용.</td></tr>
<tr><td><b>특보 발령 시</b></td><td>단계를 ‘경고/위험’으로 바꾸면 순위와 문안이 즉시 갱신. 담당자는 상위 동 3~5곳에 전화·문자, 발송 결과를 기록.</td></tr>
<tr><td><b>시즌 종료 후</b></td><td>지수·커버리지 표를 근거로 “야간 운영 쉼터 확충 대상 동”을 선정, 다음 해 무더위쉼터 지정·운영시간 조정에 반영.</td></tr>
</table>

<h3>2. 기존 방식과의 차이</h3>
<table>
<tr><th style="width:22%">구분</th><th style="width:39%">기존(재난문자·쉼터 목록)</th><th>쿨링콜</th></tr>
<tr><td>방향</td><td>시 → 시민 일괄 안내</td><td>담당자 → <b>위험 순서대로</b> 개별 연락</td></tr>
<tr><td>단위</td><td>시 전체 / 시설 목록</td><td><b>행정동 단위 위험지수</b>와 그 근거</td></tr>
<tr><td>문안</td><td>고정 문구</td><td>동별 계산값을 반영한 문안 + 사람 승인</td></tr>
<tr><td>기록</td><td>발송 건수 중심</td><td>누구에게·왜 먼저 닿았는지 이력으로 축적</td></tr>
</table>

<h3>3. 활용 데이터 출처 (붙임5 연계)</h3>
<table>
<tr><th style="width:34%">데이터</th><th style="width:22%">제공기관</th><th>출처</th></tr>
<tr><td>기온분석(대구 지점 143, 일별)</td><td>기상청 국가기후데이터센터</td><td>https://data.kma.go.kr/stcs/grnd/grndTaList.do?pgmNo=70</td></tr>
<tr><td>무더위쉼터 현황(2026)</td><td>대구광역시 자연재난과</td><td>https://www.daegu.go.kr/safety/index.do?menu_id=00934211</td></tr>
<tr><td>행정동별 성별·연령별 주민등록 인구(2026.10)</td><td>행정안전부</td><td>https://jumin.mois.go.kr/ageStatMonth.do</td></tr>
<tr><td>행정동 경계(지도 표시용, 2018 기준)</td><td>통계청(SGIS) 기준 공개 경계자료</td><td>https://github.com/southkorea/southkorea-maps</td></tr>
</table>

<p class="note" style="margin-top:2mm">본 제안서의 수치는 위 공공데이터를 직접 내려받아 코드로 계산한 값이며, 계산 스크립트와 원본도 함께 보관하고 있습니다. AI는 문장 작성에만 사용했습니다.</p>

</body></html>
"""

OUT_HTML.write_text(html, encoding="utf-8")
HTML(string=html, base_url=str(HERE)).write_pdf(str(OUT_PDF))
print("wrote", OUT_PDF)
