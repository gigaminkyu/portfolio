# 해커톤·공모전 출품 프로젝트

실제로 만들어서 제출한 공모전 작업물 3건의 코드·분석 스크립트·데이터·기획서를 모아 둔 폴더입니다.
각 폴더의 `README.md`에 개요·실행 방법·재현 절차·한계·공개 저장소에서 뺀 항목을 정리했습니다.

| 프로젝트 | 대회 | 한 줄 | 데모 |
|---|---|---|---|
| [빈틈(BinTeum)](binteum/) | 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 (2026-11-18 제출) | 읍면동 실측 유동인구로 "지금 한산한 곳"을 골라 남은 하루 동선 3안을 짜는 Multi-Agent (파이썬 표준 라이브러리만, 외부 패키지 0개) | [실행 결과 리포트](https://gigaminkyu.github.io/portfolio/binteum/) · `bash run.sh` |
| [쿨링콜(Cooling Call)](coolingcall/) | 제1회 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회 (2026-11-19 제출) | 대구 150개 행정동 폭염 위험지수와 안부 연락 문안을 매일 자동으로 뽑는 담당자용 운영 도구 | [대시보드](https://gigaminkyu.github.io/portfolio/coolingcall/) |
| [올팍 주차나침반](olpark-parking-compass/) | 한국체육산업개발(주) 2026 공공데이터 활용 경진대회 (마감 2026-12-01) | 올림픽공원 입출차 21만 건·공연 510건으로 예상 점유율과 게이트 분산을 안내하는 단일 파일 웹 데모 | [웹 데모](https://gigaminkyu.github.io/portfolio/olpark-parking-compass/) |

## 공통 원칙

- **숫자는 코드가 계산하고, AI는 문장만** 씁니다. 지수·순위·예측은 스크립트 산출물이고, LLM은 슬롯에 주입된 값만 문장으로 다듬습니다(불일치 시 폐기).
- **실측과 합성을 구분해 표기**합니다. 빈틈은 실측 수집분과 합성 스냅샷을 화면 배지·메타데이터에 나눠 남겼고, 쿨링콜·올팍은 원본 공공데이터를 그대로 내려받아 계산했습니다.
- **재현 가능성**을 남깁니다. 수집 → 정제 → 계산 → 화면 순서의 스크립트와 원본·산출물의 출처를 각 README에 적었습니다.

## 공개 저장소에서 제외한 것

공개 저장소에는 아래를 넣지 않았습니다. 각 프로젝트 README의 "저장소에 넣지 않은 것" 절에 항목별로 적어 두었습니다.

- 참가신청서·개인정보 동의서·서약서, 자필 서명 이미지와 서명완성 PDF
- 연락처·생년월일·주소·이메일 등 개인정보
- API 키·토큰, `.env`
- 제출 패키지 압축본, 대회 공고문 원본, 개인 메일 발신 기록

## 배포 위치

GitHub Pages는 이 저장소 `docs/`를 그대로 제공합니다(사이트 루트 = `docs/`).

- 쿨링콜: `docs/coolingcall/index.html` → <https://gigaminkyu.github.io/portfolio/coolingcall/>
- 올팍 주차나침반: `docs/olpark-parking-compass/index.html` → <https://gigaminkyu.github.io/portfolio/olpark-parking-compass/>
- 빈틈: `docs/binteum/index.html` → <https://gigaminkyu.github.io/portfolio/binteum/>

`docs/`는 원래 `build.py`가 `dist/`를 복사해 만드는 산출물입니다. 사이트를 다시 빌드해 `docs/`를 통째로 갈아끼우면 위 세 폴더가 사라지므로, 빌드 후에는 각 프로젝트의 소스에서 다시 복사해야 합니다. 복사 방법은 각 프로젝트 README에 적어 두었습니다.
