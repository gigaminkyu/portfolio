# 빈틈(BinTeum) — 제주 여행의 빈 시간을 찾아주는 실측 혼잡 회피 Agent

> "지금 이 시각, 어디가 한산한가"를 **읍면동 실측 유동인구**로 계산하고,
> 아이·부모님·귀가시간 같은 제약을 지키면서 **남은 하루 동선을 3안으로 다시 짜주는** Multi-Agent.
> **제주 AI·빅데이터 활용 AI Agent 개발 챌린지** 출품작 (개인 참가 `gigaminkyu`, 2026-11-18 DAKER 최종 제출).

| 항목 | 내용 |
|---|---|
| 실행 환경 | 파이썬 3.10 이상, 외부 패키지 **0개**(표준 라이브러리만), 인터넷 불필요 |
| 실행 | `./run.sh` → 브라우저에서 `http://127.0.0.1:8000` |
| 테스트 | `python3 -m pytest -q` — 95개 (개발 의존성은 pytest 하나) |
| 실행 결과 미리보기 | [`samples/`](samples/) — 시나리오 3종의 독립 실행 HTML 리포트 |
| 대회 | 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 (마감 2026-11-20 10:00, 총상금 500만 원) |
| 제출 | 2026-11-18 22:26 DAKER 최종 제출(수정 불가 잠금) |

## 1. 무엇을 하는가

여행자는 "지금 성산이 붐비는데 애가 3살이라 오후엔 실내로, 6시까지 숙소 복귀"처럼 말합니다.
빈틈은 그 문장에서 제약을 뽑아 **지금 한산한 곳 기준으로 남은 하루 동선 3안**을 만들고,
각 후보마다 "왜 여기가 지금 한산한가"의 근거(유동인구·관광지·버스·날씨 가중치)를 함께 보여줍니다.

- 6단계 파이프라인: **Router**(문장 → 제약카드) → **Data**(허브 API/스냅샷) → **Index**(혼잡지수 CI) → **Planner**(동선 3안) → **Critic**(규칙 R1~R6 검증·반려 시 1회 재계획) → **Reporter**(카드·공유문구·HTML 리포트)
- LLM은 **문장 다듬기 계층에만** 붙고, 숫자 가드를 통과하지 못한 문장은 버리고 결정론적 템플릿으로 되돌립니다.
- 예약·결제·메시지 발송 기능은 코드에 없습니다(추천까지만).

## 2. 바로 실행하기

```bash
bash run.sh                 # 설치 단계 없음. 1분 내 기동
bash run.sh --offline       # 허브 호출 없이 동봉 스냅샷만 사용
bash run.sh --port 8080
```

서버 없이 결과만 보려면 [`samples/`](samples/)의 HTML을 브라우저로 열면 됩니다(외부 리소스 없는 단일 파일).
공개 사이트에도 같은 리포트를 올려 두었습니다: <https://gigaminkyu.github.io/portfolio/binteum/>
(사이트 빌드로 `docs/`를 갈아끼우면 사라지므로, 그때는 `samples/*.html`을 `docs/binteum/samples/`로 다시 복사하면 됩니다.)

```bash
python3 -m pytest -q                                   # 95 passed
PYTHONPATH=src python3 -m binteum doctor               # 환경·데이터·스냅샷 출처 진단
PYTHONPATH=src python3 -m binteum demo                 # 샘플 시나리오 3종 → out/
PYTHONPATH=src python3 -m binteum backtest             # 가중치 민감도·계절 예측력·요일효과
PYTHONPATH=src python3 -m binteum plan "성산인데 붐벼" --emd 성산읍 --end 18:00 --party family_kid --indoor
```

## 3. 데이터와 정직한 표기

| 파일 | 성격 | 근거 |
|---|---|---|
| `data/snapshot/live/flow.json` (허브 583) | **실측 수집분** | 제주데이터허브 Open API 직접 호출, 2026-06-24~08-19(57일) · 읍면동 43개 · 원본 39,216행 → 2,451행 합산 · 430회 호출 |
| `data/snapshot/{tour,bus,weather,wifi}.json` (591·614·579·618) | 합성 데모 스냅샷 | 해당 데이터셋이 프로젝트에 연결되어 있지 않아(403) 스키마·결측·요일효과를 재현한 합성 데이터 |

화면 배지가 `실측 + 일부 스냅샷`과 기준일(2026-08-19)을 표시하고, 데이터셋별 출처는 결과 JSON의 `data.datasets[].mode`에 남습니다.
허브가 2026-08-19 이후 구간을 아직 적재하지 않아(2026-08-26 클라우드 이전) 그 이후는 실측이 아닙니다.

API 키는 저장소에 없습니다. 실데이터로 갱신하려면:

```bash
export JEJU_DATA_HUB_KEY=발급받은키
export JEJU_HUB_DATA_KEY_FLOW=583_데이터키
PYTHONPATH=src python3 -m binteum fetch     # data/snapshot/live/ 로 저장
```

## 4. 검증

| 파일 | 검증 내용 |
|---|---|
| `tests/test_index.py` | CI 재정규화·백분위·날씨항·시간대 추정·이동시간 |
| `tests/test_data.py` | 카탈로그, 필드 별칭, 스냅샷 우선순위, 결측 강등 |
| `tests/test_hub.py` | 200/502/403/타임아웃/캐시 4경로(가짜 전송 계층) |
| `tests/test_router.py` | 한국어 문장 → 제약카드 |
| `tests/test_planner_critic.py` | 제약 준수·귀가시각·근거 부착·반려 규칙 R1~R6 |
| `tests/test_pipeline.py` | 6단계 통합, 반려→재계획 1회, LLM 실패 폴백, 재현성 |
| `tests/test_web_backtest_snapshot.py` | 웹 API·백테스트·스냅샷 결정성 |

백테스트 요지: 가중치를 ±0.10 흔들어도 상위 순위 상관(Spearman) 0.964~0.969, 전년 동월 최대값으로 다음 해 순위를 예측한 계절 기준선 0.964.

## 5. 파일 구성

```
binteum/
├── run.sh / run.cmd / demo.sh      # 한 줄 실행
├── .env.example                    # 환경변수 예시(키 값은 없음)
├── pyproject.toml / requirements*.txt
├── src/binteum/
│   ├── cli.py  web.py              # CLI / 웹 서버(http.server)
│   ├── pipeline.py                 # 오케스트레이터
│   ├── router.py  data.py  hub.py  fields.py
│   ├── index.py                    # 혼잡지수 CI(순수 파이썬)
│   ├── planner.py  critic.py  reporter.py  llm.py
│   ├── backtest.py  snapshot_build.py  travel.py  catalog.py  models.py  config.py  trace.py
│   └── static/                     # index.html · style.css · app.js
├── data/catalog/spots.csv          # 관광지 63곳(좌표·영업시간·실내외·테마·노선)
├── data/snapshot/                  # 동봉 스냅샷 + manifest
├── samples/                        # 실행 결과 리포트 3종(HTML/MD)
├── tests/                          # pytest 95개
├── tools/                          # 기획서용 목업 렌더러, PDF 빌드 등
└── docs/                           # 기획서·데이터 활용 명세·결과 설명자료·사용자 매뉴얼·오류/제약
```

- `docs/기획서_v1.0.0.pdf` — 제출 기획서 15쪽
- `docs/데이터활용명세.md` — 데이터 5종의 필드·집계·한계
- `docs/오류_제약사항.md` — 알려진 제약과 대응

## 6. 공개 저장소에서 뺀 것

- 실제 허브 API 키, `.env`, 개인 연락처·생년월일 등 개인정보
- 제주데이터허브 프로젝트 데이터키(코드에서는 `JEJU_HUB_DATA_KEY_FLOW` 환경변수로 주입)
- 제출용 ZIP(`dist/`)과 PDF용 한글 폰트(13MB) — 필요하면 `tools/build_pdf.py`에 폰트 경로를 지정해 재생성
- `data/snapshot_backup_*/`, `out/` 실행 캐시 — 재현 시 새로 생성됩니다
