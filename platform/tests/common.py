"""Shared test helpers."""

import os
import shutil
import sys
import tempfile

PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLATFORM_ROOT not in sys.path:
    sys.path.insert(0, PLATFORM_ROOT)

FIXTURES_DIR = os.path.join(PLATFORM_ROOT, "fixtures")

WORKLOAD_VM_UUID = "a1b2c3d456784b7d8e9f0a1b2c3d4e5f"
HOST_UUID = "cbb61d8a22cc4fd1b3702af673cbf405"
CLUSTER_UUID = "a29a9e1c13ac4017a187e30fca573625"
ZONE_UUID = "26fd04cdf31047e4a96aff5e41225420"
L3_UUID = "26391fe900e44409b3d2a37721b08f76"


class TempDB(object):
    """Context manager giving a fresh SQLite path in a temp directory."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="tsplatform-test-")
        return os.path.join(self.dir, "test.db")

    def __exit__(self, exc_type, exc, tb):
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


def make_config(db_path, token=""):
    from tsplatform.config import load_config

    cfg = load_config()
    cfg["platform"]["db_path"] = db_path
    cfg["zsvirt"]["fixtures_dir"] = FIXTURES_DIR
    cfg["zsvirt"]["provider"] = "fixture"
    cfg["api"]["token"] = token
    return cfg


def make_app(db_path=None, token="", provider=None):
    from tsplatform.app import PlatformApp
    from tsplatform.zsvirt import FixtureProvider

    if db_path is None:
        db_path = os.path.join(tempfile.mkdtemp(prefix="tsplatform-test-"), "test.db")
    cfg = make_config(db_path, token=token)
    if provider is None:
        provider = FixtureProvider(FIXTURES_DIR)
    return PlatformApp(cfg, provider=provider)
