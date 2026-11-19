# Mingyu Jeong — AX 포트폴리오

공개 사이트: https://gigaminkyu.github.io/portfolio/

데이터 확인 → 판단 → 안전한 실행과 복구 → 사용자 결과를 설명하는 한국어 정적 포트폴리오입니다. AI 코딩 도구를 활용했으며 합성 입출력과 실패 경로를 검증합니다. 실제 고객·기업 경력·매출 상승·절감시간을 성과로 주장하지 않습니다.

`content.json`은 문구, `index.template.html`은 구조, `style.css`는 디자인입니다. 프레임워크나 외부 폰트 없이 빌드합니다.

```sh
python3 -m unittest discover -s public-demo -v
python3 build.py
python3 -m http.server 8765 --directory dist --bind 127.0.0.1
```

[public-demo/README.md](public-demo/README.md)에 축소 재현의 명령·입출력·실패 복구·한계를 기록했습니다. 고객 교재와 비공개 운영 코드는 포함하지 않습니다.

## 해커톤·공모전 출품 프로젝트

실제로 제출한 공모전 작업물 3건의 코드·분석 스크립트·데이터·기획서를 [projects/](projects/)에 모았습니다. 각 폴더의 README에 실행·재현 절차와 한계, 공개 저장소에서 뺀 개인정보 항목을 적었습니다.

| 프로젝트 | 대회 | 데모 | 코드 |
|---|---|---|---|
| 빈틈(BinTeum) | 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 (2026-11-18 제출) | <https://gigaminkyu.github.io/portfolio/binteum/> | [projects/binteum](projects/binteum/) |
| 쿨링콜(Cooling Call) | 제1회 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회 (2026-11-19 제출) | <https://gigaminkyu.github.io/portfolio/coolingcall/> | [projects/coolingcall](projects/coolingcall/) |
| 올팍 주차나침반 | 한국체육산업개발(주) 2026 공공데이터 활용 경진대회 (마감 2026-12-01) | <https://gigaminkyu.github.io/portfolio/olpark-parking-compass/> | [projects/olpark-parking-compass](projects/olpark-parking-compass/) |

세 작업물 모두 숫자는 코드가 계산하고 LLM은 문장만 다듬는 구조이며, 실측과 합성을 구분해 표기합니다. 참가신청서·서명 이미지·연락처 등 개인정보와 API 키는 저장소에 넣지 않았습니다.

GitHub Pages는 main 브랜치의 docs/를 제공합니다. dist/를 docs/로 복사해 같은 저장소에 커밋하고 push합니다. 모든 자산은 상대경로로 저장소 하위경로를 지원합니다. Git 태그 ax-before-update-20260930은 이전 공개판으로의 복원 지점입니다. QA/검수 기록과 로컬 자료는 공개 저장소에 포함하지 않습니다.
