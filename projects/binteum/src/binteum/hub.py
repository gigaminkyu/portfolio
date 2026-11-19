"""제주데이터허브 Open API 클라이언트 (이중 모드의 '실시간' 쪽).

실제 엔드포인트 (2026-11-18 실호출로 확인)
    https://open.jejudatahub.net/api/proxy/{데이터키}/{프로젝트키}
        ?startDate=YYYYMMDD&endDate=YYYYMMDD[&emd=읍면동][&gender=..][&ageGroup=..][&limit=100]

- 인증은 **경로**에 들어간다(프로젝트키). `jejudatahub.net/api/data/view?id=583`은
  메타데이터만 돌려주므로 데이터 조회에 쓰면 안 된다.
- 응답은 `{"totCnt":N,"hasMore":bool,"data":[...]}` 이고 **한 번에 최대 100행**이다.
  `offset`/`page`/`pageNo` 등 페이지 파라미터는 서버가 무시하므로(실측),
  100행을 넘는 구간은 **날짜 구간을 반으로 쪼개** 반복 호출해 합친다.
- 프로젝트에 연결되지 않은 데이터셋은 403 `Forbidden`을 돌려준다. 그래서 데이터키가
  없는 데이터셋은 호출하지 않고 곧바로 사유를 돌려준다.

원칙
1. 인증키는 환경변수에서만 읽고, 로그·산출물·ZIP에 절대 남기지 않는다.
2. 호출 실패(403 WAF / 502 / 타임아웃)는 예외로 터뜨리지 않고 결과 객체로 돌려준다.
   상위(Data Agent)가 스냅샷 폴백을 결정할 수 있어야 하기 때문이다.
3. 응답은 로컬 캐시에 남겨, 같은 파라미터 재호출 시 네트워크 없이 재현된다.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from . import config


@dataclass
class HttpResponse:
    status: int
    body: str = ""
    error: str = ""


class Transport(Protocol):
    def get(self, url: str, params: dict[str, Any], timeout: float) -> HttpResponse: ...


class UrllibTransport:
    """표준 라이브러리만 쓰는 HTTP 전송 계층(추가 설치 불필요)."""

    def __init__(self, user_agent: str = f"BinTeum/{config.VERSION}"):
        self.user_agent = user_agent

    def get(self, url: str, params: dict[str, Any], timeout: float) -> HttpResponse:
        query = urllib.parse.urlencode(params, doseq=True)
        full = f"{url}?{query}" if query else url
        request = urllib.request.Request(full, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return HttpResponse(status=response.status,
                                    body=response.read().decode(charset, "replace"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            return HttpResponse(status=exc.code, body=body, error=f"HTTP {exc.code}")
        except urllib.error.URLError as exc:
            return HttpResponse(status=0, error=f"URLError: {exc.reason}")
        except Exception as exc:  # noqa: BLE001 - 네트워크 예외는 모두 폴백 대상
            return HttpResponse(status=0, error=f"{type(exc).__name__}: {exc}")


@dataclass
class FetchResult:
    dataset: str
    hub_id: int
    rows: list[dict] = field(default_factory=list)
    mode: str = "error"          # live | cache | error | missing_key | not_connected
    error: str = ""
    status: int = 0
    fetched_at: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    requests: int = 0            # 실제 HTTP 요청 수(분할 수집 시 2 이상)
    truncated: bool = False      # hasMore인데 더 쪼갤 수 없어 일부만 받은 경우

    @property
    def ok(self) -> bool:
        return bool(self.rows) and self.mode in ("live", "cache")

    def to_dict(self) -> dict:
        return {"dataset": self.dataset, "hub_id": self.hub_id, "rows": len(self.rows),
                "mode": self.mode, "error": self.error, "status": self.status,
                "fetched_at": self.fetched_at, "requests": self.requests,
                "truncated": self.truncated}


class HubClient:
    def __init__(self, key: str | None = None, base_url: str | None = None,
                 transport: Transport | None = None, cache_dir: Path | None = None,
                 trace=None, retries: int | None = None, sleep=time.sleep):
        self.key = key if key is not None else config.hub_key()
        self.base_url = (base_url or config.HUB_PROXY_BASE).rstrip("/")
        self.transport = transport or UrllibTransport()
        self.cache_dir = Path(cache_dir or config.CACHE_DIR / "hub")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.trace = trace
        self.retries = config.HUB_RETRIES if retries is None else retries
        self._sleep = sleep

    # ---------------------------------------------------------------- 공개 API
    @property
    def has_key(self) -> bool:
        return bool(self.key)

    def endpoint(self, dataset: str) -> str:
        """데이터셋의 실제 호출 URL. 프로젝트에 연결되지 않았으면 빈 문자열."""
        data_key = config.DATASET_DATA_KEYS.get(dataset, "")
        if not data_key or not self.key:
            return ""
        return f"{self.base_url}/{data_key}/{self.key}"

    def fetch(self, dataset: str, params: dict[str, Any] | None = None,
              use_cache: bool = True) -> FetchResult:
        hub_id = config.DATASET_IDS.get(dataset)
        if hub_id is None:
            return FetchResult(dataset=dataset, hub_id=0, mode="error",
                               error=f"알 수 없는 데이터셋: {dataset}")
        params = dict(params or {})
        if not self.key:
            return FetchResult(dataset=dataset, hub_id=hub_id, mode="missing_key",
                               error="JEJU_DATA_HUB_KEY 미설정", params=params)
        url = self.endpoint(dataset)
        if not url:
            return FetchResult(
                dataset=dataset, hub_id=hub_id, mode="not_connected", params=params,
                error=("이 프로젝트에 연결된 데이터키가 없습니다 "
                       f"(id={hub_id}). 제주데이터허브 마이페이지 → 프로젝트 → 데이터 추가 후 "
                       "config.DATASET_DATA_KEYS 에 데이터키를 등록하세요."))

        cache_path = self._cache_path(hub_id, params)
        if use_cache and cache_path.exists():
            cached = self._read_cache(cache_path)
            if cached:
                self._trace("hub_cache_hit", dataset=dataset, hub_id=hub_id, rows=len(cached))
                return FetchResult(dataset=dataset, hub_id=hub_id, rows=cached,
                                   mode="cache", fetched_at=self._cache_time(cache_path),
                                   params=params)

        rows, errors, requests, truncated = self._collect(url, params, depth=0)
        status = 200 if rows else (errors and 0 or 0)
        if rows:
            self._write_cache(cache_path, rows)
            return FetchResult(dataset=dataset, hub_id=hub_id, rows=rows, mode="live",
                               status=status, requests=requests, truncated=truncated,
                               fetched_at=datetime.now().isoformat(timespec="seconds"),
                               params=params)
        return FetchResult(dataset=dataset, hub_id=hub_id, mode="error",
                           error="; ".join(errors) or "빈 응답", params=params,
                           requests=requests)

    def probe(self) -> dict[str, Any]:
        """키 유효성·연결 여부를 1회 호출로 진단한다(`cli doctor`)."""
        result = self.fetch("flow", {"startDate": "20260801", "endDate": "20260801"},
                            use_cache=False)
        return {"has_key": self.has_key, "mode": result.mode, "status": result.status,
                "rows": len(result.rows), "error": result.error,
                "requests": result.requests}

    # ---------------------------------------------------------------- 수집(분할)
    def _collect(self, url: str, params: dict[str, Any], depth: int
                 ) -> tuple[list[dict], list[str], int, bool]:
        """100행 상한에 걸리면 날짜 구간을 반으로 쪼개 재귀 수집한다."""
        payload, error, requests = self._request(url, params)
        if payload is None:
            return [], [error], requests, False
        rows = _rows_from_payload(payload)
        has_more = bool(payload.get("hasMore")) if isinstance(payload, dict) else False
        if not has_more:
            return rows, [], requests, False

        start, end = params.get("startDate"), params.get("endDate")
        if not (start and end) or start == end or depth >= config.HUB_SPLIT_DEPTH:
            self._trace("hub_truncated", start=start, end=end, rows=len(rows), depth=depth)
            return rows, [], requests, True

        left, right = _split_range(str(start), str(end))
        if not right:
            return rows, [], requests, True
        lrows, lerr, lreq, ltr = self._collect(url, {**params, "startDate": left,
                                                     "endDate": _day_before(right)}, depth + 1)
        rrows, rerr, rreq, rtr = self._collect(url, {**params, "startDate": right,
                                                     "endDate": end}, depth + 1)
        return (lrows + rrows, lerr + rerr, requests + lreq + rreq, ltr or rtr)

    def _request(self, url: str, params: dict[str, Any]) -> tuple[dict | None, str, int]:
        query = {**params}
        if "limit" not in query:
            query["limit"] = config.HUB_PAGE_LIMIT
        errors: list[str] = []
        status_seen = 0
        for attempt in range(self.retries + 1):
            started = time.time()
            try:
                response = self.transport.get(url, query, config.HUB_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 - 어떤 전송 예외든 폴백으로 넘긴다
                response = HttpResponse(status=0, error=f"{type(exc).__name__}: {exc}")
            ms = (time.time() - started) * 1000
            status_seen = response.status
            payload = _parse_payload(response)
            self._trace("hub_http", url=_mask(url), status=response.status,
                        rows=len(_rows_from_payload(payload)) if payload else 0,
                        ms=round(ms, 1), attempt=attempt + 1, error=response.error,
                        params={k: v for k, v in query.items() if k != "key"})
            if payload is not None:
                return payload, "", attempt + 1
            errors.append(response.error or f"status={status_seen} 응답 해석 실패")
            if response.status in (400, 401, 403):   # 키 오류·WAF·프로젝트 미연결
                break
            if attempt < self.retries:
                self._sleep(min(2.0, 0.4 * (attempt + 1)))
        return None, "; ".join(errors) or "빈 응답", len(errors)

    # ---------------------------------------------------------------- 내부
    def _cache_path(self, hub_id: int, params: dict[str, Any]) -> Path:
        raw = json.dumps([hub_id, sorted(params.items())], ensure_ascii=False, default=str)
        digest = hashlib.sha1(raw.encode()).hexdigest()[:16]
        return self.cache_dir / f"{hub_id}_{digest}.json"

    def _read_cache(self, path: Path) -> list[dict] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        rows = payload.get("rows")
        return rows if isinstance(rows, list) and rows else None

    @staticmethod
    def _cache_time(path: Path) -> str:
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("fetched_at", "")
        except Exception:
            return ""

    def _write_cache(self, path: Path, rows: list[dict]) -> None:
        payload = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "rows": rows}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _trace(self, event: str, **data) -> None:
        if self.trace:
            self.trace.log(event, data)


def _split_range(start: str, end: str) -> tuple[str, str]:
    """'YYYYMMDD' 구간을 절반으로 나눈다. (왼쪽 끝, 오른쪽 시작)"""
    try:
        s = datetime.strptime(start, "%Y%m%d").date()
        e = datetime.strptime(end, "%Y%m%d").date()
    except ValueError:
        return start, ""
    if (e - s).days < 1:
        return start, ""
    mid = s + timedelta(days=(e - s).days // 2)
    return mid.strftime("%Y%m%d"), (mid + timedelta(days=1)).strftime("%Y%m%d")


def _day_before(day: str) -> str:
    try:
        return (datetime.strptime(day, "%Y%m%d").date() - timedelta(days=1)).strftime("%Y%m%d")
    except ValueError:
        return day


def _mask(url: str) -> str:
    """로그에 프로젝트키가 남지 않도록 경로 마지막 조각을 가린다."""
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        parts[-1] = "***"
    return "/".join(parts)


def _parse_payload(response: HttpResponse) -> dict | None:
    """200 응답의 JSON 본문을 dict로. 차단 페이지·HTML·비JSON은 None."""
    if response.status and not (200 <= response.status < 300):
        return None
    body = (response.body or "").strip()
    if not body or body.startswith("<"):
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else {"data": payload}


def _rows_from_payload(payload: Any) -> list[dict]:
    """허브 응답 3형태(배열 / {data:[]} / {items:[]} / {response:{body:{items:[]}}})를 모두 처리."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "rows", "list", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
            if isinstance(value, dict):
                nested = _rows_from_payload(value)
                if nested:
                    return nested
        # 공공데이터포털형 response.body.items.item
        response = payload.get("response")
        if isinstance(response, dict):
            return _rows_from_payload(response)
        body = payload.get("body")
        if isinstance(body, dict):
            return _rows_from_payload(body)
    return []
