"""웹 UI 서버 — 표준 라이브러리만 사용(http.server). 추가 설치·빌드 없음.

평가자가 매뉴얼만 보고 3분 안에 실행할 수 있게 하기 위한 선택이다.
`python -m binteum serve` → 브라우저에서 http://127.0.0.1:8000 접속.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config, reporter
from .catalog import spots as catalog_spots
from .catalog import emds as catalog_emds
from .data import DataPortal
from .pipeline import BinTeumPipeline

STATIC = {"": "index.html", "/": "index.html", "/index.html": "index.html",
          "/app.js": "app.js", "/style.css": "style.css"}


class State:
    """프로세스 공용 상태(데이터 상태 캐시, 마지막 실행)."""

    def __init__(self, offline: bool = False):
        self.offline = offline
        self._meta: dict | None = None
        self._meta_at = 0.0
        self.last_payload: dict | None = None
        self.lock = threading.Lock()

    def meta(self) -> dict:
        with self.lock:
            fresh = time.time() - self._meta_at < 60
            if self._meta is not None and fresh:
                return self._meta
            portal = DataPortal(offline=self.offline)
            provenance = portal.load(today=datetime.now().date())
            self._meta = {
                "app": {"name": config.APP_NAME, "version": config.VERSION,
                        "tagline": config.APP_TAGLINE},
                "emds": catalog_emds(),
                "spots": [{"id": s.id, "name": s.name, "emd": s.emd, "category": s.category,
                           "lat": s.lat, "lon": s.lon, "indoor": s.indoor}
                          for s in catalog_spots()],
                "data": provenance.to_dict(),
                "defaults": {"end_time": "18:00", "party": "solo", "mobility": "car"},
            }
            self._meta_at = time.time()
            return self._meta


class Handler(BaseHTTPRequestHandler):
    server_version = f"BinTeum/{config.VERSION}"
    state: State = None          # type: ignore[assignment]

    # ---------------------------------------------------------------- 라우팅
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in STATIC:
            return self._serve_static(STATIC[path])
        if path == "/api/health":
            return self._json({"ok": True, "version": config.VERSION,
                               "time": datetime.now().isoformat(timespec="seconds")})
        if path == "/api/meta":
            return self._json(self.state.meta())
        if path == "/api/catalog":
            return self._json({"spots": self.state.meta()["spots"]})
        if path == "/api/last":
            return self._json(self.state.last_payload or {"ok": False, "message": "실행 이력 없음"})
        return self._json({"ok": False, "error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/plan":
            return self._json({"ok": False, "error": "not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json({"ok": False, "error": f"잘못된 요청 본문: {exc}"}, status=400)

        inputs = {}
        if body.get("emd"):
            inputs["emd"] = body["emd"]
        if body.get("spot_id"):
            inputs["spot_id"] = body["spot_id"]
        if body.get("end_time"):
            inputs["end_time"] = body["end_time"]
        if body.get("party"):
            inputs["party"] = body["party"]
        if body.get("mobility"):
            inputs["mobility"] = body["mobility"]
        if "indoor" in body:
            inputs["indoor"] = bool(body["indoor"])
        if body.get("budget"):
            inputs["budget"] = int(body["budget"])
        if body.get("themes"):
            inputs["themes"] = body["themes"]

        try:
            pipeline = BinTeumPipeline(offline=self.state.offline)
            payload = pipeline.run(body.get("query", ""), **inputs)
        except Exception as exc:  # noqa: BLE001 - 서버는 어떤 경우에도 JSON을 돌려준다
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)
        self.state.last_payload = payload
        return self._json(payload)

    # ---------------------------------------------------------------- 응답
    def _serve_static(self, name: str) -> None:
        path = config.STATIC_DIR / name
        if not path.exists():
            return self._json({"ok": False, "error": "missing static"}, status=404)
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if name.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        elif name.endswith((".css", ".js")):
            ctype = ctype.split(";")[0] + "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:   # 조용한 로그
        if "/api/" in (args[0] if args else ""):
            return
        print(f"[web] {self.address_string()} {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8000, offline: bool = False) -> None:
    config.ensure_dirs()
    Handler.state = State(offline=offline)
    meta = Handler.state.meta()
    mode = meta["data"]["mode"]
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("─" * 62)
    print(f"  {config.APP_NAME} v{config.VERSION} — {config.APP_TAGLINE}")
    print(f"  주소   : http://{host}:{port}")
    print(f"  데이터 : {mode} (기준일 {meta['data'].get('today')})")
    print(f"  카탈로그: 관광지 {len(meta['spots'])}곳 · 읍면동 {len(meta['emds'])}개")
    print(f"  중지   : Ctrl+C")
    print("─" * 62)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[web] 종료합니다.")
    finally:
        httpd.server_close()


if __name__ == "__main__":       # pragma: no cover
    serve()
