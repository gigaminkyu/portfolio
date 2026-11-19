"""pytest 공용 설정 — src 를 import 경로에 넣고, 테스트용 임시 출력 폴더를 쓴다."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _hub_data_keys(monkeypatch):
    """공개 저장소에는 허브 데이터키 값이 없다(환경변수로 주입). 테스트는 더미 키를 쓴다."""
    from binteum import config
    if not config.DATASET_DATA_KEYS.get("flow"):
        monkeypatch.setitem(config.DATASET_DATA_KEYS, "flow", "TEST_FLOW_KEY")


@pytest.fixture()
def tmp_out(tmp_path, monkeypatch):
    """실행 산출물을 임시 폴더로 돌린다(저장소 오염 방지)."""
    from binteum import config
    out = tmp_path / "out"
    cache = tmp_path / "cache"
    monkeypatch.setattr(config, "OUT_DIR", out)
    monkeypatch.setattr(config, "CACHE_DIR", cache)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture()
def snapshot_dir():
    from binteum import config
    return config.SNAPSHOT_DIR


@pytest.fixture(scope="session")
def portal():
    """동봉 스냅샷으로 로딩한 DataPortal(네트워크·키 불필요)."""
    from binteum.data import DataPortal
    instance = DataPortal(offline=True)
    instance.load()
    return instance


@pytest.fixture(scope="session")
def indexer(portal):
    from binteum.index import CrowdIndexer
    return CrowdIndexer(portal)


@pytest.fixture()
def portal_fixture(portal, indexer):
    return portal, indexer
