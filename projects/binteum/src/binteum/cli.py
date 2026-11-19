"""빈틈 CLI.

    python -m binteum serve                 # 웹 UI(권장)
    python -m binteum demo                  # 샘플 시나리오 3종 실행(검증용)
    python -m binteum plan "성산인데 붐벼" --emd 성산읍 --end 18:00
    python -m binteum fetch                 # 허브 실데이터 수집 → snapshot/live/
    python -m binteum backtest              # 가중치 민감도·계절 예측력 검증
    python -m binteum doctor                # 환경·데이터 진단
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time
from pathlib import Path

from . import backtest, catalog, config, reporter, snapshot_build
from .data import DataPortal, MODE_KO
from .hub import HubClient
from .llm import LLMClient
from .pipeline import BinTeumPipeline
from .trace import Trace

SCENARIOS: dict[str, dict] = {
    "family": {
        "query": "성산에 있는데 지금 너무 붐벼. 애가 3살이라 오후엔 실내 위주로, 6시까지 숙소 복귀",
        "emd": "성산읍", "spot_id": "seongsan-ilchulbong", "end_time": "18:00",
        "party": "family_kid", "mobility": "car", "indoor": True,
        "themes": ["가족", "실내"], "budget": None,
    },
    "budget": {
        "query": "애월에 있는데 버스로 다닐 거고 예산 3만원, 9시까지 야경 보고 싶어",
        "emd": "애월읍", "spot_id": "handam-beach", "end_time": "21:00",
        "party": "couple", "mobility": "bus", "indoor": False,
        "themes": ["야경", "해변"], "budget": 30000,
    },
    "parents": {
        "query": "중문인데 부모님 모시고 있어요. 걷기 힘드셔서 이동 짧게, 5시까지",
        "emd": "중문동", "spot_id": "jungmun-beach", "end_time": "17:00",
        "party": "with_parents", "mobility": "car", "indoor": False,
        "themes": ["자연"], "budget": None,
    },
}


# ------------------------------------------------------------------ 출력 도우미
def _line(char: str = "─", width: int = 74) -> str:
    return char * width


def print_payload(payload: dict, verbose: bool = False) -> None:
    if payload.get("status") == "needs_input":
        print("? " + payload.get("message", "위치를 알려주세요"))
        return
    if not payload.get("ok"):
        print("! 실행 실패:", payload.get("status"))
        for note in payload.get("notes", []):
            print("  -", note)
        return

    c = payload["constraints"]
    data = payload["data"]
    print(_line())
    print(f"입력    : {c.get('raw_query') or '(구조화 입력)'}")
    print(f"제약    : {c.get('origin_emd')} · {c.get('end_time')}까지 · {c.get('party')} · "
          f"{c.get('mobility')}" + (" · 실내" if c.get("indoor_required") else ""))
    print(f"데이터  : {data['mode']} ({MODE_KO.get(data['mode'], data['mode'])}) · "
          f"기준일 {data.get('today')}")
    for d in data.get("datasets", []):
        print(f"          id={d['hub_id']} {d['dataset']:<8} {d['mode']:<9} {d['rows']:>6}행")
    print(_line())
    best = payload["summary"].get("best_plan")
    for plan in payload["plans"]:
        mark = "★" if plan["key"] == best else " "
        print(f"{mark} {plan['label']}  |  {plan['headline']}")
        for stop in plan["stops"]:
            print(f"    {stop['order']}. {stop['arrive']}~{stop['depart']} "
                  f"{stop['spot_name']:<16} CI {stop['ci']:>3} {stop['ci_label']:<3} "
                  f"이동 {stop['travel_min']:>3}분")
            if verbose:
                for why in stop["why"]:
                    print(f"        · {why}")
        print(f"    합계: 이동 {plan['totals']['travel_min']}분 · "
              f"비용 {plan['totals']['cost_krw']:,}원 · 평균 CI {plan['totals']['avg_ci']}")
        for warn in plan.get("warnings", []):
            print(f"    ⚠ {warn}")
    critic = payload.get("critic", {})
    passed = sum(1 for r in critic.values() if r["passed"])
    print(_line())
    print(f"Critic  : {passed}/{len(critic)} 통과 · 반려 라운드 "
          f"{payload['summary'].get('critic_rounds', 0)}")
    for note in payload.get("notes", [])[:3]:
        print(f"  · {note}")
    outputs = payload.get("outputs", {})
    if outputs:
        print(_line())
        print(f"저장    : {outputs.get('json')}")
        print(f"        : {outputs.get('html')}")
        print(f"        : {payload.get('trace_path')}")


# ------------------------------------------------------------------ 명령
def cmd_serve(args) -> int:
    from .web import serve
    serve(host=args.host, port=args.port, offline=args.offline)
    return 0


def cmd_plan(args) -> int:
    trace = Trace(echo=args.verbose)
    pipeline = BinTeumPipeline(offline=args.offline, trace=trace,
                               llm=LLMClient(trace=trace))
    payload = pipeline.run(args.query or "",
                           emd=args.emd or None, spot_id=args.spot or None,
                           end_time=args.end or None, party=args.party or None,
                           mobility=args.mobility or None, indoor=args.indoor,
                           budget=args.budget, themes=args.theme)
    print_payload(payload, verbose=args.verbose)
    return 0 if payload.get("ok") else 1


def cmd_demo(args) -> int:
    # 데모는 재현성을 위해 '오늘 10:00'을 기준 시각으로 고정한다(실행 시각에 따라 동선이 달라지므로).
    demo_now = (datetime.strptime(args.now, "%Y-%m-%d %H:%M") if getattr(args, "now", None)
                else datetime.combine(date.today(), time(10, 0)))
    results = {}
    print(f"기준 시각: {demo_now:%Y-%m-%d %H:%M} (재현성을 위해 고정, --now 로 변경 가능)")
    for name, scenario in SCENARIOS.items():
        print(f"\n{'=' * 74}\n[시나리오] {name} — {scenario['query']}\n{'=' * 74}")
        trace = Trace()
        pipeline = BinTeumPipeline(offline=args.offline, trace=trace,
                                   llm=LLMClient(trace=trace))
        payload = pipeline.run(scenario["query"],
                               now=demo_now,
                               emd=scenario["emd"], spot_id=scenario["spot_id"],
                               end_time=scenario["end_time"], party=scenario["party"],
                               mobility=scenario["mobility"], indoor=scenario["indoor"],
                               budget=scenario["budget"], themes=scenario["themes"])
        results[name] = payload
        print_payload(payload)

    summary_path = config.OUT_DIR / "demo_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(
        {name: {"ok": p.get("ok"), "run_id": p.get("run_id"),
                "best": p.get("summary", {}).get("best_plan"),
                "stops": p.get("summary", {}).get("stops"),
                "avg_ci": p.get("summary", {}).get("avg_ci"),
                "outputs": p.get("outputs")} for name, p in results.items()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for p in results.values() if p.get("ok"))
    print(f"\n{_line()}\n완료: {ok}/{len(results)} 시나리오 성공 · 요약 {summary_path}")
    return 0 if ok == len(results) else 1


def cmd_snapshot(args) -> int:
    ref = datetime.strptime(args.ref, "%Y%m%d").date() if args.ref else date.today()
    manifest = snapshot_build.build(ref_day=ref, seed=args.seed)
    print(json.dumps({k: manifest[k] for k in ("generated_at", "source", "seed", "reference_date")},
                     ensure_ascii=False, indent=2))
    for name, info in manifest["datasets"].items():
        print(f"  {name:<8} {info.get('rows'):>6}행  {info.get('file')}")
    return 0


def cmd_fetch(args) -> int:
    client = HubClient()
    if not client.has_key:
        print("! JEJU_DATA_HUB_KEY(또는 JEJU_HUB_KEY) 환경변수가 없습니다.")
        print("  제주데이터허브 로그인 → Open API 인증키 신청 → 발급 후 아래처럼 실행:")
        print("  export JEJU_DATA_HUB_KEY=발급받은키  &&  python -m binteum fetch")
        return 2
    trace = Trace(prefix="fetch")
    client.trace = trace
    today = date.today()
    ok = 0
    live_dir = config.LIVE_DIR
    live_dir.mkdir(parents=True, exist_ok=True)
    for name in config.DATASET_IDS:
        if name == "tour_foreign":
            continue
        result = client.fetch(name, DataPortal._query_params(name, today))
        status = f"{result.mode} {len(result.rows)}행"
        print(f"  {name:<8} id={config.DATASET_IDS[name]:<4} {status}"
              + (f"  ({result.error})" if result.error else ""))
        if result.ok:
            ok += 1
            payload = {"meta": {"source": "jeju-datahub-live",
                                "note": f"허브 Open API id={config.DATASET_IDS[name]} 직접 수집",
                                "collected_at": datetime.now().isoformat(timespec="seconds"),
                                "rows": len(result.rows),
                                "params": result.params},
                       "rows": result.rows}
            (live_dir / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    trace.close()
    print(f"\n수집 완료 {ok}/{len(config.DATASET_IDS) - 1} · 저장 위치 {live_dir}")
    print("이후 실행은 수집분을 우선 사용합니다(스냅샷 폴백 유지).")
    return 0 if ok else 1


def cmd_backtest(args) -> int:
    payload = backtest.run(offline=args.offline)
    paths = backtest.save(payload)
    print(backtest.render_markdown(payload))
    print(f"\n저장: {paths['md']}\n      {paths['json']}")
    return 0


def cmd_doctor(args) -> int:
    print(_line())
    print(f"{config.APP_NAME} v{config.VERSION} 환경 진단")
    print(_line())
    print(f"python      : {sys.version.split()[0]} ({sys.executable})")
    print(f"프로젝트     : {config.PROJECT_DIR}")
    print(f"LLM         : {config.llm_settings()['provider']}"
          f"{' (사용 가능)' if LLMClient().available else ' (템플릿 폴백)'}")
    key = config.hub_key()
    print(f"허브 키      : {'설정됨' if key else '없음 → 스냅샷 모드'}")
    print(f"카탈로그     : 관광지 {len(catalog.spots())}곳 · 읍면동 {len(catalog.emds())}개 · "
          f"노선 {len(catalog.routes())}개")
    portal = DataPortal(offline=not key)
    provenance = portal.load()
    print(f"데이터 모드   : {provenance.mode} · 기준일 {portal.reference_date}")
    for d in provenance.datasets:
        flag = "OK " if d.rows else "빈 "
        print(f"  {flag} id={d.hub_id:<4} {d.dataset:<8} {d.mode:<9} {d.rows:>6}행  "
              f"{d.base_date_max or '-'}")
    manifest = config.SNAPSHOT_DIR / "manifest.json"
    if manifest.exists():
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        print(f"스냅샷      : source={meta.get('source')} seed={meta.get('seed')} "
              f"generated={meta.get('generated_at')}")
        if meta.get("source") == "synthetic-demo":
            print("              ⚠ 합성 데모 데이터입니다(실측 아님). 화면·리포트에 그대로 표시됩니다.")
    print(_line())
    print("다음 단계: python -m binteum serve  →  http://127.0.0.1:8000")
    return 0


def cmd_info(args) -> int:
    print(f"카탈로그 {len(catalog.spots())}곳")
    for spot in catalog.spots():
        print(f"  {spot.id:<24} {spot.name:<18} {spot.emd:<8} "
              f"{'실내' if spot.indoor else '야외'}  {spot.open_time}~{spot.close_time}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="binteum", description=config.APP_TAGLINE)
    parser.add_argument("--version", action="version", version=f"binteum {config.VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="웹 UI 실행(표준 라이브러리만)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--offline", action="store_true", help="허브 실호출 없이 스냅샷만 사용")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("plan", help="CLI로 동선 1회 생성")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--emd")
    p.add_argument("--spot")
    p.add_argument("--end", help="종료 시각 HH:MM")
    p.add_argument("--party", choices=["solo", "couple", "family_kid", "with_parents", "friends"])
    p.add_argument("--mobility", choices=["car", "bus", "walk"])
    p.add_argument("--indoor", action="store_true")
    p.add_argument("--budget", type=int)
    p.add_argument("--theme", nargs="*")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("demo", help="샘플 시나리오 3종 실행")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--now", help="기준 시각 'YYYY-MM-DD HH:MM'(기본: 오늘 10:00 고정)")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("snapshot", help="데모 스냅샷 재생성")
    p.add_argument("--ref", help="기준일 YYYYMMDD(기본 오늘)")
    p.add_argument("--seed", type=int, default=snapshot_build.SEED)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("fetch", help="허브 Open API 실데이터 수집(키 필요)")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("backtest", help="백테스트 실행")
    p.add_argument("--offline", action="store_true", default=True)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("doctor", help="환경·데이터 진단")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("info", help="카탈로그 목록")
    p.set_defaults(func=cmd_info)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
