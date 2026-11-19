#!/usr/bin/env bash
# 검증용: 샘플 시나리오 3종 + 백테스트 + 테스트를 한 번에 실행하고 로그를 남긴다.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p out
{
  echo "=== 1/3 환경 진단 ==="
  python3 -m binteum doctor
  echo
  echo "=== 2/3 샘플 시나리오 3종 ==="
  python3 -m binteum demo --offline
  echo
  echo "=== 3/3 백테스트 ==="
  python3 -m binteum backtest
} 2>&1 | tee out/verification.log
echo
echo "로그: out/verification.log"
echo "리포트: out/reports/*.html (브라우저로 열면 서버 없이 그대로 렌더링됩니다)"
