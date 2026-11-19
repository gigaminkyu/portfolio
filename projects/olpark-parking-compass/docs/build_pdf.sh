#!/bin/sh
# plan_print.html → 기획서_미리보기.pdf (Chromium/Skia 인쇄, docs/build_docs.py 실행 후 사용)
set -e
cd "$(dirname "$0")"
CH=~/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
LD_LIBRARY_PATH=/workspace/var/libx/usr/lib/x86_64-linux-gnu $CH \
  --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$(pwd)/기획서_미리보기.pdf" --virtual-time-budget=8000 \
  "file://$(pwd)/plan_print.html" 2>&1 | grep -i "bytes written" || true
python3 -c "from pypdf import PdfReader; print('pages', len(PdfReader('기획서_미리보기.pdf').pages))"
