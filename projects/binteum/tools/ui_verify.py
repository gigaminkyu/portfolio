#!/usr/bin/env python3
"""빈틈 웹 UI 실물 클릭 검증 — 로컬 서버를 띄우고 헤드리스 Chromium으로 실제 조작한다.

1) 시나리오 버튼 → 폼 자동 채움 → '빈틈 찾기' 클릭 → 결과 렌더
2) 테마 칩 변경 후 재실행(같은 화면에서 다른 조건) → 결과 갱신
3) 읍면동·동행·실내를 직접 바꿔 재실행
4) 결과 JSON 내려받기 버튼 클릭(실제 파일)
5) 콘솔 오류·페이지 오류 0 확인, 실데이터(583/20260819) 반영 확인
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOT = Path("/workspace/downloads/dacon-binteum-verify-2026-11-18")
SHOT.mkdir(parents=True, exist_ok=True)
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"

log: list[str] = []


def note(msg: str) -> None:
    print(msg)
    log.append(msg)


def wait_server(timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise SystemExit("서버가 뜨지 않았습니다")


def main() -> int:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    server = subprocess.Popen(
        [sys.executable, "-m", "binteum", "serve", "--port", str(PORT)],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_server()
        note("서버 기동 OK: " + BASE)

        from playwright.sync_api import sync_playwright

        errors: list[str] = []
        downloads: list[str] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(viewport={"width": 1500, "height": 1050},
                                      accept_downloads=True, locale="ko-KR")
            page = ctx.new_page()
            page.on("console", lambda m: errors.append(f"console:{m.type}:{m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))

            page.goto(BASE, wait_until="networkidle")
            page.wait_for_function(
                "document.querySelector('#data-badge').textContent.indexOf('확인 중') === -1",
                timeout=20000)
            badge = page.inner_text("#data-badge").strip()
            date_line = page.inner_text("#data-date").strip()
            note(f"배지: {badge} / {date_line}")
            page.screenshot(path=str(SHOT / "01-landing.png"), full_page=True)

            # 1) 예시 시나리오(애월·버스·3만원·야경) → 빈틈 찾기
            page.click('button[data-scenario="budget"]')
            page.click("#run")
            page.wait_for_selector(".summary", timeout=30000)
            summary = page.inner_text(".summary")
            note("시나리오1 요약: " + re.sub(r"\s+", " ", summary)[:220])
            page.screenshot(path=str(SHOT / "02-scenario-budget.png"), full_page=True)

            # 2) 테마 칩(시장) + 읍면동 직접 선택 후 재실행
            page.click('button.chip[data-theme="시장"]')
            page.select_option("#emd", "성산읍")
            page.click("#run")
            page.wait_for_timeout(1200)
            page.wait_for_selector(".summary", timeout=30000)
            note("시나리오2(성산읍+시장 테마) 제목: " + page.inner_text(".summary .constraints").split("\n")[1][:120])
            page.screenshot(path=str(SHOT / "03-scenario-seongsan-market.png"), full_page=True)

            # 3) 읍면동·동행·실내 직접 변경(부모님·중문·실내)
            page.select_option("#emd", "중문동")
            page.select_option("#party", "with_parents")
            page.select_option("#mobility", "car")
            page.fill("#budget", "")
            page.fill("#end_time", "17:00")
            page.check("#indoor")
            page.click("#run")
            page.wait_for_timeout(1200)
            page.wait_for_selector(".detail table", timeout=30000)
            detail = page.inner_text(".detail table")
            note("상세 표 첫 3행: " + " | ".join(
                " ".join(l.split()) for l in detail.split("\n")[:3]))

            # 실데이터 반영 확인
            page_text = page.inner_text("#results")
            has_583 = "583" in page_text
            has_date = "20260819" in page_text or "2026-08-19" in page_text
            note(f"화면에 583 표기: {has_583} / 기준일 20260819 표기: {has_date}")
            page.screenshot(path=str(SHOT / "04-parents-indoor.png"), full_page=True)

            # 지도·근거 영역까지 보이도록 상세 스크롤 캡처
            page.locator(".map").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.screenshot(path=str(SHOT / "05-map-detail.png"))

            # 4) 결과 JSON 내려받기(실제 파일)
            with page.expect_download(timeout=15000) as dl:
                page.click("text=결과 JSON 내려받기")
            d = dl.value
            target = SHOT / "ui-result-download.json"
            d.save_as(str(target))
            downloads.append(str(target))
            payload = json.loads(Path(target).read_text(encoding="utf-8"))
            note("내려받은 JSON: mode=%s today=%s plans=%d" % (
                payload.get("data", {}).get("mode"),
                payload.get("data", {}).get("today"),
                len(payload.get("plans", []))))
            modes = {d["dataset"]: d["mode"] for d in payload.get("data", {}).get("datasets", [])}
            note("데이터셋 모드: " + json.dumps(modes, ensure_ascii=False))

            # 5) 빈 입력 제출 → 안내 문구(오류 아님)
            page.select_option("#emd", "")
            page.click("#run")
            page.wait_for_timeout(800)
            note("빈 읍면동 제출 시 안내: " + page.inner_text("#results").split("\n")[0][:60])

            browser.close()

        note(f"콘솔/페이지 오류: {len(errors)}건" + ((" → " + "; ".join(errors[:3])) if errors else ""))
        (SHOT / "verification.txt").write_text("\n".join(log), encoding="utf-8")
        print("SHOT_DIR", SHOT)
        return 0 if not errors else 1
    finally:
        server.terminate()
        try:
            out = server.communicate(timeout=8)[0]
        except Exception:
            server.kill()
            out = ""
        (SHOT / "server.log").write_text(out or "", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
