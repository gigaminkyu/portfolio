#!/usr/bin/env bash
# 제출용 ZIP 생성 — 실행 코드·데이터·문서·테스트·샘플 산출물을 한 번에 묶는다.
#   ./tools/package_zip.sh  →  dist/빈틈_BinTeum_v1.0.0.zip
#
# 포함하지 않는 것
#   · var/            : 로컬 HTTP 캐시(API 응답 캐시)
#   · __pycache__, .pytest_cache
#   · assets/fonts/   : 기획서 목업용 폰트(실행 경로 아님, 10MB)
#   · 대회 배포 xlsx 원본 2종 : 이 폴더 밖에 있음(재배포 금지 규정)
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - "$@" <<'PY'
import os
import sys
import zipfile
from pathlib import Path

NAME = "빈틈_BinTeum_v1.0.0"
FOLDER = "BinTeum_v1.0.0"   # ZIP 내부 폴더명은 ASCII(압축 해제 도구 간 인코딩 문제 방지)
ROOT = Path.cwd()
DIST = ROOT / "dist"
ZIP = DIST / f"{NAME}.zip"
INCLUDE = ["README.md", "requirements.txt", "requirements-dev.txt", "pyproject.toml",
           ".env.example", "run.sh", "run.cmd", "demo.sh",
           "src", "data", "docs", "tests", "tools", "out"]
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", "assets", "var", "dist"}
SKIP_NAMES = {"_probe.png", "_check2.png"}

DIST.mkdir(exist_ok=True)
if ZIP.exists():
    ZIP.unlink()

def add(zf, full: Path, rel: str, mode: int = 0o644) -> None:
    """zipfile 은 실행권한을 보존하지 않으므로 external_attr 로 직접 지정한다."""
    info = zipfile.ZipInfo(rel)
    info.external_attr = (mode & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    info.date_time = __import__("time").localtime()[:6]
    with full.open("rb") as fp:
        zf.writestr(info, fp.read())


EXEC = {"run.sh", "demo.sh", "package_zip.sh", "fetch_hub.sh"}

count = 0
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
    for item in INCLUDE:
        path = ROOT / item
        if not path.exists():
            continue
        if path.is_file():
            add(zf, path, f"{FOLDER}/{item}", 0o755 if item in EXEC else 0o644)
            count += 1
            continue
        for base, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name in SKIP_NAMES or name.endswith(".pyc"):
                    continue
                full = Path(base) / name
                rel = full.relative_to(ROOT)
                add(zf, full, f"{FOLDER}/{rel}", 0o755 if name in EXEC else 0o644)
                count += 1

names = zipfile.ZipFile(ZIP).namelist()
size_mb = ZIP.stat().st_size / 1024 / 1024
print(f"생성: {ZIP}")
print(f"크기: {size_mb:.1f} MB · 파일 {count}개")
print("\n필수 4종 확인")
checks = {
    "실행 소스 코드": "src/binteum/pipeline.py",
    "실행환경·매뉴얼": "README.md",
    "데이터 활용 명세": "docs/데이터활용명세.md",
    "결과 설명자료": "docs/결과설명자료.md",
}
for label, pattern in checks.items():
    hit = any(n.endswith(pattern) for n in names)
    print(f"  {'OK ' if hit else '없음'} {label:<12} {pattern}")
xlsx = [n for n in names if n.lower().endswith((".xlsx", ".xls"))]
print(f"  {'⚠ 있음' if xlsx else 'OK '} 대회 배포 xlsx 원본 미포함 {xlsx if xlsx else ''}")
print(f"  {'OK ' if any(n.endswith('run.sh') for n in names) else '없음'} 원클릭 실행 run.sh")
PY
