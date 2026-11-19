"""기상청 기상자료개방포털(data.kma.go.kr) 기후통계분석 '기온분석'(pgmNo=70) 공개 조회 엔드포인트에서
대구 지점(143) 일별 최저/평균/최고기온을 연 단위로 수집해 CSV로 저장한다.

- 로그인 없이 조회되는 공개 통계 화면과 동일한 요청(grndTaAjaxList.do)을 사용한다.
- 수집 구간: 2015-01-01 ~ 2025-12-31 (연 단위로 나눠 요청)
- 출력: data/kma_asos_daegu_daily.csv (date, avg_ta, max_ta, min_ta)
"""
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://data.kma.go.kr/stcs/grnd/grndTaAjaxList.do"
HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "kma_asos_daegu_daily.csv"

YEARS = range(2015, 2026)


def fetch(year: int) -> list[dict]:
    form = {
        "isSample": "N",
        "pgmNo": "70",
        "menuNo": "432",
        "serviceSe": "F00101",
        "stdrMg": "99999",
        "startDt": f"{year}0101",
        "endDt": f"{year}1231",
        "selectType": "1",
        "mddlClssCd": "SFC01",
        "dataFormCd": "F00501",
        "dataTypeCd": "standard",
        "startDay": f"{year}0101",
        "endDay": f"{year}1231",
        "stnId": "143",
        "areaId": "",
    }
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        URL,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "https://data.kma.go.kr/stcs/grnd/grndTaList.do?pgmNo=70",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read().decode("utf-8", "replace")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected response for {year}: {raw[:200]}")
    return data


def main() -> None:
    rows: dict[str, dict] = {}
    for y in YEARS:
        got = fetch(y)
        for d in got:
            rows[d["dt"]] = {
                "date": d["dt"],
                "avg_ta": d.get("avgTa"),
                "max_ta": d.get("maxTa"),
                "min_ta": d.get("minTa"),
            }
        print(y, len(got))
        time.sleep(0.5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "avg_ta", "max_ta", "min_ta"])
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    print("saved", OUT, len(rows), "days")


if __name__ == "__main__":
    main()
