# 올팍 주차나침반 — 올림픽공원 주차 혼잡 예측·게이트 분산 안내

> 2024년 7월 입출차 **215,528건**과 공연 일정 **510건**을 분석해, 선택한 날짜·시각의
> **예상 점유율·재실 대수**와 **어느 게이트로 들어가야 덜 막히는지**를 보여주는 무인 운영 웹 데모입니다.
> **한국체육산업개발(주) 2026 공공데이터 활용 경진대회** 출품 작업물 (마감 2026-12-01 18:00).

**웹 데모(공개)**: <https://gigaminkyu.github.io/portfolio/olpark-parking-compass/>
날짜·시각 딥링크: `?d=2026-11-28&h=18`

## 1. 핵심 수치 (모두 실측 기반)

| 항목 | 값 |
|---|---|
| 일평균 입차 | 6,953대 (최다 8,615대 · 2024-07-12 / 최소 4,984대 · 07-07) |
| 최대 재실 | 2,228대 = 정원 2,200대의 **101%** (2024-07-21 16:40) |
| 공연 효과 | KSPO DOME 공연 시작 2시간 전 3시간 창 입차 1,748대 vs 1,244대 (**+41%**) |
| 체류 | 중위 74분, 24시간 이상 장기 주차 0.14% |
| 예측 자체검증 | MAPE **5.5%**, ±15% 적중 97% |
| 기관 기존 서비스와 차이 | 기존 「주차장 예상 이용률」은 주말 한정·전 시간대 동일 % → 여기는 날짜·시각·공연·날씨·게이트별 |

## 2. 웹 데모

- `web/index.html` — **파일 하나로 동작**(외부 라이브러리·서버 불필요). 브라우저로 열면 바로 실행됩니다.
- 화면: 날짜 카드 46일 · 시각 슬라이더 · KPI 4개 · 24시간 점유율 곡선 · 게이트 3곳 분산 안내 · 당일 공연 목록
- 데이터: `web/data.json` — 아래 분석 산출물을 웹용으로 묶은 것
- 화면 캡처: `web/demo_1_main.png`(11/21 17시), `web/demo_2_congestion.png`(11/28 18시), `web/demo_3_mobile*.png`(모바일)

## 3. 데이터

| 파일 | 내용 | 출처 |
|---|---|---|
| `data/inout_202407.csv` | 2024년 7월 입출차 215,528행(cp949) | data.go.kr 15138735 파일데이터 |
| `data/monthly.csv`, `data/monthly.bin` | 2023~2025 월별 주차대수 | data.go.kr 15131671 |
| `data/events/*.json` | 2023-01~2027-01 월별 공연 목록(510건) | 기관 홈페이지 공연/행사 일정 |
| `data/weather_2024summer.json` | 시간별 기온·강수 | Open-Meteo(ERA5) — 기상청 키 발급 전 대체 |
| `figs/fig1~7` | 일별·시간대·히트맵·산점도·날씨·월별·구조도 | 분석 스크립트 산출 |

> 개인정보가 없는 데이터입니다. 입출차 원본은 `입차일자, 입차일시, 출차일시` 세 열뿐이며 차량번호·개인 식별자는 포함되어 있지 않습니다.

## 4. 재현 순서

```bash
python3 analysis/01_clean.py      # 정제 → data/entries.pkl, data/events.pkl
python3 analysis/02_analysis.py   # 일별·점유율·회귀 → data/stats.json, data/daily.csv
python3 analysis/03_hourly.py     # 시간대 프로파일 → data/hourly_stats.json
python3 analysis/04_figs.py       # 그림 1~6 → figs/
python3 analysis/05_model.py      # 데모용 데이터 → web/data.json
python3 analysis/06_tm.py         # 공연 시간 파서(모듈)
python3 analysis/07_arch.py       # 구조도 → figs/fig7_arch.png
```

기획서 재생성: `python3 docs/build_docs.py` (content.py 수정 후 DOCX·`plan_print.html`) → `docs/build_pdf.sh` (Chromium 인쇄 → `기획서_미리보기.pdf`, A4 11쪽).

`data/entries.pkl`·`data/events.pkl`은 01_clean.py가 만드는 중간 산출물이라 저장소에 넣지 않았습니다.

## 5. 파일 구성

```
olpark-parking-compass/
├── analysis/        01_clean → 02_analysis → 03_hourly → 04_figs → 05_model (+06_tm, 07_arch)
├── data/            입출차 원본 · 월별 주차대수 · 공연 일정 · 날씨 · 분석 산출물
├── figs/            그림 1~7
├── web/             index.html(단일 파일 데모) · data.json · 화면 캡처
└── docs/            기획서 생성 스크립트(content.py, build_docs.py, build_pdf.sh) · 기획서 미리보기 PDF(11쪽)
```

## 6. 저장소에 넣지 않은 것

- 참가신청서·개인정보 동의서와 **자필 서명 이미지/서명완성 PDF**(제출용 개인 서류)
- 주최 측에 보낸 문의 메일 본문(개인 이메일 발신 기록)
- 연락처·생년월일·주소 등 개인정보, 제출용 DOCX(기획서 생성 스크립트로 재생성 가능)
- `data/entries.pkl`, `data/events.pkl` — 01_clean.py로 재생성
