#!/usr/bin/env bash
# 빈틈(BinTeum) 한 줄 실행 스크립트
#   ./run.sh                 → 웹 UI (http://127.0.0.1:8000)
#   ./run.sh --port 8080     → 포트 변경
#   ./run.sh --offline       → 허브 실호출 없이 스냅샷만 사용
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[오류] python3 를 찾을 수 없습니다. 파이썬 3.10 이상을 설치하세요."
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
  echo "[오류] 파이썬 3.10 이상이 필요합니다. 현재: $("$PY" -V 2>&1)"
  exit 1
fi

# .env 가 있으면 읽는다(KEY=VALUE 형식만 지원)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f data/snapshot/manifest.json ]; then
  echo "[안내] 스냅샷이 없어 새로 만듭니다(합성 데모 데이터)."
  "$PY" -m binteum snapshot
fi

exec "$PY" -m binteum serve "$@"
