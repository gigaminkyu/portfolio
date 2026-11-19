"""실행 trace — 모든 Tool 호출을 JSONL로 남긴다.

기획서 §p9의 Tool 표(입력·출력·타임아웃·캐시)와 §p15의 재현 절차가
이 로그 하나로 검증된다. run_id 단위로 out/traces/{run_id}.jsonl 에 쌓인다.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config


def new_run_id(prefix: str = "run") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"


class Trace:
    def __init__(self, run_id: str | None = None, path: Path | None = None,
                 echo: bool = False):
        config.ensure_dirs()
        self.run_id = run_id or new_run_id()
        self.path = Path(path or config.OUT_DIR / "traces" / f"{self.run_id}.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self.started = time.time()
        self._n = 0
        self.log("run_start", {"run_id": self.run_id})

    def log(self, event: str, data: dict[str, Any] | None = None) -> None:
        self._n += 1
        record = {
            "seq": self._n,
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "event": event,
            "data": data or {},
        }
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if self.echo:
            print(f"[trace] {event} {json.dumps(data or {}, ensure_ascii=False)[:400]}")

    def tool(self, name: str, ok: bool, ms: float, **info) -> None:
        self.log("tool_call", {"tool": name, "ok": ok, "ms": round(ms, 1), **info})

    def close(self, status: str = "ok") -> None:
        self.log("run_end", {"status": status, "ms": round((time.time() - self.started) * 1000)})

    def __enter__(self) -> "Trace":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close("error" if exc_type else "ok")
