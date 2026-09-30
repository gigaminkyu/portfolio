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

GitHub Pages는 main 브랜치의 docs/를 제공합니다. dist/를 docs/로 복사해 같은 저장소에 커밋하고 push합니다. 모든 자산은 상대경로로 저장소 하위경로를 지원합니다. Git 태그 ax-before-update-20260930은 이전 공개판으로의 복원 지점입니다. QA/검수 기록과 로컬 자료는 공개 저장소에 포함하지 않습니다.
