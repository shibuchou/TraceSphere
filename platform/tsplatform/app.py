"""Platform application wiring: stores + provider + registry + correlation."""

import logging
from typing import Any, Dict, Optional

from .config import resolve_zsvirt_password
from .correlate import CorrelationEngine
from .db import Database
from .ingest import EventIngest
from .mockgpu import register_mock_gpu
from .registry import ResourceRegistry, SyncResult
from .store_agents import AgentStore
from .store_events import EventStore
from .store_evidence import ClusterStore, EvidenceStore
from .store_resources import ResourceStore
from .zsvirt import FixtureProvider, RESTProvider, ZSvirtRestClient

logger = logging.getLogger("tsplatform.app")


class PlatformApp(object):
    def __init__(self, cfg: Dict[str, Any], provider: Optional[Any] = None):
        self.cfg = cfg
        self.db = Database(cfg["platform"]["db_path"])
        self.db.init()
        self.resources = ResourceStore(self.db)
        self.events = EventStore(self.db)
        self.evidence = EvidenceStore(self.db)
        self.clusters = ClusterStore(self.db)
        self.agents = AgentStore(self.db)
        self.ingest = EventIngest(self.resources, self.events)
        self.registry = ResourceRegistry(self.db, self.resources, self.ingest)
        self.correlation = CorrelationEngine(
            self.events,
            self.resources,
            self.evidence,
            self.clusters,
            window_seconds=cfg.get("correlation", {}).get("window_seconds", 5.0),
            max_events=cfg.get("correlation", {}).get("max_events", 5000),
        )
        self.provider = provider if provider is not None else build_provider(cfg)
        self.mock_gpu_id = None

    # ----- operations -----------------------------------------------------
    def sync(self, ingest_events: bool = True) -> SyncResult:
        result = self.registry.sync(self.provider, ingest_events=ingest_events)
        # 降级模式：注册模拟 GPU 资源与 Host/Gpu/VM 边（未启用时为 no-op）
        self.mock_gpu_id = register_mock_gpu(self.resources, self.cfg)
        return result

    def status(self) -> Dict[str, Any]:
        counts = self.db.table_counts()
        last_sync = self.registry.last_sync()
        return {
            "provider": {
                "name": self.provider.name,
                "mode": self.provider.mode,
                "description": self.provider.description,
            },
            "database": {"path": self.cfg["platform"]["db_path"], "counts": counts},
            "last_sync": last_sync,
        }

    def close(self) -> None:
        self.db.close()


def build_provider(cfg: Dict[str, Any]) -> Any:
    zsvirt = cfg.get("zsvirt", {})
    provider_name = str(zsvirt.get("provider") or "fixture").lower()
    if provider_name == "rest":
        password = resolve_zsvirt_password(cfg)
        if not password:
            raise RuntimeError(
                "zsvirt.provider=rest requires a password: set %s (never commit it)"
                % (zsvirt.get("password_env") or "ZSVIRT_PASSWORD")
            )
        client = ZSvirtRestClient(
            base_url=zsvirt.get("base_url"),
            account=zsvirt.get("account") or "admin",
            password=password,
            timeout=zsvirt.get("request_timeout_sec", 20),
            verify_tls=zsvirt.get("verify_tls", False),
            page_size=zsvirt.get("page_size", 100),
            paths=zsvirt.get("paths") or {},
        )
        return RESTProvider(client)
    return FixtureProvider(
        fixtures_dir=zsvirt.get("fixtures_dir"),
        scenario=zsvirt.get("fixture_scenario"),
    )
