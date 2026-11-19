@echo off
REM 빈틈(BinTeum) Windows 실행 스크립트: run.cmd  (기본 포트 8000)
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
where python >nul 2>nul
if errorlevel 1 (
  echo [오류] python 을 찾을 수 없습니다. 파이썬 3.10 이상을 설치하세요.
  exit /b 1
)
if not exist data\snapshot\manifest.json (
  echo [안내] 스냅샷이 없어 새로 만듭니다.
  python -m binteum snapshot
)
python -m binteum serve %*
endlocal
