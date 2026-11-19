"""붙임4(AI 프롬프트 활용 내역서) · 붙임5(공공데이터 사용 내역서) 초안 생성."""
from pathlib import Path

from weasyprint import HTML

HERE = Path(__file__).resolve().parent
OUT = HERE.parent

CSS = """
@page { size:A4; margin:16mm 15mm; @bottom-center { content: counter(page) " / " counter(pages); font-size:8pt; color:#888; } }
body { font-family:"Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif; font-size:9.6pt; line-height:1.6; color:#1a1a1a; }
h1 { font-size:15pt; text-align:center; margin:0 0 4mm; letter-spacing:2px; }
table { width:100%; border-collapse:collapse; margin-bottom:4mm; }
th, td { border:0.7pt solid #444; padding:2.2mm 2.4mm; vertical-align:top; font-size:9.2pt; }
th { background:#f2efe9; font-weight:600; text-align:left; }
.blk { border:0.7pt solid #444; page-break-inside:avoid; }
.blk .hd { background:#f2efe9; font-weight:600; padding:2mm 2.4mm; border-bottom:0.7pt solid #444; }
.blk .bd { padding:2.4mm 2.6mm; }
.lab { font-weight:600; color:#7a2c02; }
pre { font-family:"Noto Sans KR",sans-serif; white-space:pre-wrap; margin:1mm 0 2mm; font-size:9pt;
      background:#faf8f3; border-left:2.5pt solid #c9bda6; padding:2mm 2.6mm; }
.note { font-size:8.4pt; color:#555; }
ul { margin:1mm 0 2mm; padding-left:4.4mm; }
li { margin-bottom:0.8mm; }
.url { font-family:"DejaVu Sans Mono",monospace; font-size:7.8pt; word-break:break-all; }
"""

ai = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<h1>AI 프롬프트 활용 내역서</h1>
<table>
<tr><th style="width:22%">접수번호</th><td>※ 미기재</td></tr>
<tr><th>주요 사용 AI</th><td>Pickle(피클) AI 비서 — 대화형 LLM 기반 기획·코드 작성·문서 작성 보조<br>
    Python 3.12 오픈소스 라이브러리(openpyxl, WeasyPrint 등) — 데이터 처리·문서 렌더링</td></tr>
<tr><th>활용 목적</th><td>☑ 데이터 수집·전처리 및 분석 코드 작성 &nbsp; ☑ 아이디어 구상 및 기획서 작성 &nbsp; ☑ 시각화 그래픽 및 이미지 생성 &nbsp; ☐ 기타</td></tr>
</table>

<div class="blk">
  <div class="hd">사례 1 — 대회 요강·제출 서식 구조 확인</div>
  <div class="bd">
    <p class="lab">[활용 목적]</p>
    <p>공고문·붙임자료 원문에서 접수 조건과 제출 서식 규격을 정확히 확정</p>
    <p class="lab">[입력 프롬프트]</p>
    <pre>2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회의 붙임자료 HWP에서 [붙임4] AI 프롬프트 활용 내역서,
[붙임5] 공공데이터 사용 내역서, [붙임6] 아이디어 제안서 서식의 칸 구조와 작성 조건을 표로 뽑아줘.
붙임5는 어떤 URL 표기가 요구되는지, 붙임6은 페이지 제한과 필수 항목이 무엇인지 원문 문장으로 확인해줘.</pre>
    <p class="lab">[활용 및 보완 내용]</p>
    <p>붙임자료 원문(6쪽)에서 서식을 추출해 ① 붙임4는 사례 3개(활용 목적/입력 프롬프트/활용·보완 내용)가 필수이며 미제출 시 심사 제외,
    ② 붙임5는 데이터명·제공기관·<b>정확한 접속 URL</b>을 요구하고 이것이 규격심사 통과 조건, ③ 붙임6은 본 양식을 포함해 총 10페이지 이내임을 확인했습니다.
    이 조건을 그대로 작업 기준으로 삼아 문서를 작성했습니다.</p>
  </div>
</div>

<div class="blk" style="margin-top:4mm">
  <div class="hd">사례 2 — 공공데이터 실제 수집·정제와 지수 계산 코드 작성</div>
  <div class="bd">
    <p class="lab">[활용 목적]</p>
    <p>데이터 수집·전처리 및 분석 코드 작성</p>
    <p class="lab">[입력 프롬프트]</p>
    <pre>기상청 ASOS 대구 기온, 대구 무더위쉼터 현황, 행정동별 고령인구를 실제로 내려받아 정제하고,
행정동 단위 폭염 위험지수를 계산하는 모듈을 파이썬으로 만들어줘.
수치는 코드로만 계산하고, AI가 숫자를 추정하거나 만들어내지 않게 해줘.
지수는 폭염 노출·고령 취약·대응 결손으로 나누고, 야간 시간대 시나리오도 따로 계산되게 해줘.</pre>
    <p class="lab">[활용 및 보완 내용]</p>
    <p>AI가 작성한 수집·정제 스크립트로 기상청 기상자료개방포털의 대구(지점 143) 일별 기온 4,018일치(2015~2025)를 받아
    폭염일수·열대야일수를 계산했고, 대구시 무더위쉼터 현황 1,195곳과 행정안전부 행정동별 인구를 행정동 단위로 결합했습니다.
    지수 산식(0.30·폭염 + 0.40·고령취약 + 0.30·대응결손)과 300석 기준은 <b>사람이 정한 규칙을 코드에 고정</b>한 것으로,
    결과 수치는 모두 스크립트 실행 결과를 그대로 인용했습니다. AI가 만들어낸 수치는 문서에 사용하지 않았습니다.</p>
  </div>
</div>

<div class="blk" style="margin-top:4mm">
  <div class="hd">사례 3 — 시연 화면·안부 연락 문안 구조 설계</div>
  <div class="bd">
    <p class="lab">[활용 목적]</p>
    <p>시각화 그래픽 및 이미지 생성 / 기획서 작성</p>
    <p class="lab">[입력 프롬프트]</p>
    <pre>동별 위험지수를 지도·순위표·상세로 보여주는 시연용 대시보드를 만들어줘. 외부 라이브러리 없이 한 파일로 동작해야 하고,
특보 단계와 주간/야간을 바꾸면 지도·순위·문안이 함께 갱신되어야 해.
담당자용 안부 연락 문안은 AI가 쓰되 숫자는 계산값만 슬롯으로 들어가게 하고,
생성문에 슬롯에 없는 숫자가 나오면 폐기하는 검증 규칙을 설명해줘.</pre>
    <p class="lab">[활용 및 보완 내용]</p>
    <p>AI가 생성한 화면 설계를 바탕으로, 문안은 ① 단계·기온·폭염일수 ② 동별 고령인구·커버리지 ③ 야간 쉼터 유무 ④ 가장 가까운 쉼터
    네 슬롯으로 구조화했습니다. 제출용 시연은 외부 LLM 호출 없이 같은 슬롯 구조를 결정론적 템플릿으로 재현해,
    화면에 표시되는 모든 숫자가 계산값과 1:1로 대응하도록 했습니다. 지도 경계·색상 구간·레이아웃은 사람이 검토해 조정했습니다.</p>
  </div>
</div>

<p class="note" style="margin-top:3mm">※ 위 프롬프트는 실제 작업에 사용한 지시문을 요지 그대로 정리한 것입니다.
수치·순위·통계는 모두 공공데이터 원본에 대한 코드 계산 결과이며, 생성형 AI가 만들어낸 값이 아닙니다.</p>
</body></html>"""

data_form = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<h1>공공데이터 사용 내역서</h1>
<table>
<tr><th style="width:22%">접수번호</th><td>※ 미기재</td></tr>
<tr><th>활용 데이터 수</th><td>총 <b>( 3 )</b>개 데이터셋 활용 <span class="note">(지도 표시용 경계자료 1종은 보조자료로 별도 기재)</span></td></tr>
<tr><th>주요 제공기관</th><td>기상청(국가기후데이터센터) · 대구광역시(자연재난과) · 행정안전부</td></tr>
</table>

<table>
<tr><th style="width:5%">연번</th><th style="width:26%">공공데이터명</th><th style="width:17%">제공기관</th><th>데이터 출처 URL</th></tr>
<tr><td style="text-align:center">1</td>
    <td>기후통계분석 · 기온분석(대구 지점 143, 2015~2025 일별 최저·평균·최고기온)</td>
    <td>기상청 국가기후데이터센터<br>(기상자료개방포털)</td>
    <td class="url">https://data.kma.go.kr/stcs/grnd/grndTaList.do?pgmNo=70</td></tr>
<tr><td style="text-align:center">2</td>
    <td>무더위쉼터 현황(대구광역시, 2026년 기준 1,195곳 — 운영여부·냉방기·운영시간·수용인원·좌표)</td>
    <td>대구광역시 자연재난과</td>
    <td class="url">https://www.daegu.go.kr/safety/index.do?menu_id=00934211</td></tr>
<tr><td style="text-align:center">3</td>
    <td>주민등록 인구통계 — 행정동별 성별·연령별 인구(2026년 10월)</td>
    <td>행정안전부</td>
    <td class="url">https://jumin.mois.go.kr/ageStatMonth.do</td></tr>
<tr><td style="text-align:center">보조</td>
    <td>행정동 경계(지도 표시용, 통계청 기준 2018년 경계 공개 배포본)</td>
    <td>통계청(SGIS) 기준 자료</td>
    <td class="url">https://github.com/southkorea/southkorea-maps</td></tr>
</table>

<p class="note">
· 3종 데이터는 모두 <b>로그인·활용신청 없이 열람·내려받기 가능한 경로</b>에서 확보했으며, 2026-11-16 기준 접속을 확인했습니다.<br>
· 1번은 폭염일수(일최고 33℃ 이상)·열대야일수(일최저 25℃ 이상)·연 최고기온 산출에, 2번은 행정동별 냉방 쉼터 수·수용인원·야간 운영 여부 산출에,
  3번은 행정동별 65세 이상·75세 이상 인구 산출에 사용했습니다.<br>
· 4번(보조)은 위험지수를 지도에 표시할 때만 사용했고, 순위·지수 계산에는 사용하지 않았습니다.
</p>
</body></html>"""

(OUT / "붙임4_AI프롬프트활용내역서_정민규.pdf").write_bytes(
    HTML(string=ai).write_pdf() or b""
)
HTML(string=data_form).write_pdf(str(OUT / "붙임5_공공데이터사용내역서_정민규.pdf"))
print("ok")
