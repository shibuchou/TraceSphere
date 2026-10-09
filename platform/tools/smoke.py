#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local vertical-slice smoke test (no ZSvirt / no VM required).

    fixtures -> Resource Registry -> SQLite WAL -> Agent Registration
    -> AppEvent + system events -> Correlation -> Evidence -> graph query

Usage::

    python tools/smoke.py
    python tools/smoke.py --db data/smoke.db --fixtures fixtures
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tsplatform.app import PlatformApp  # noqa: E402
from tsplatform.config import load_config  # noqa: E402
from tsplatform.util import format_rfc3339, now_utc  # noqa: E402
from tsplatform.zsvirt import FixtureProvider  # noqa: E402

WORKLOAD_VM_UUID = "a1b2c3d456784b7d8e9f0a1b2c3d4e5f"
CONTAINER_KEY = hashlib.sha256(b"smoke-container").hexdigest()
CORRELATION_ID = "corr-smoke-01"
TASK_ID = "task-smoke-01"


def _stamp(offset_seconds=0.0):
    import datetime

    return format_rfc3339(now_utc() + datetime.timedelta(seconds=offset_seconds))


def main(argv=None):
    parser = argparse.ArgumentParser(description="TraceSphere platform smoke test")
    parser.add_argument("--fixtures", default=os.path.join(ROOT, "fixtures"))
    parser.add_argument("--db", default=None, help="SQLite path (default: temporary, removed afterwards)")
    parser.add_argument("--full", action="store_true", help="print full JSON payloads")
    args = parser.parse_args(argv)

    temp_dir = None
    db_path = args.db
    if not db_path:
        temp_dir = tempfile.mkdtemp(prefix="tracesphere-smoke-")
        db_path = os.path.join(temp_dir, "smoke.db")

    cfg = load_config()
    cfg["platform"]["db_path"] = db_path
    cfg["zsvirt"]["fixtures_dir"] = args.fixtures

    app = PlatformApp(cfg, provider=FixtureProvider(args.fixtures))
    exit_code = 0
    try:
        print("== 1. ZSvirt fixture sync -> Resource Registry")
        result = app.sync()
        print(
            "   provider=%s mode=%s ok=%s resources=%d edges=%d events=%d errors=%s"
            % (result.provider, result.mode, result.ok, result.resources, result.edges,
               result.events_ingested, result.errors or "-")
        )

        print("== 2. Resource graph")
        graph = app.resources.subgraph("vm:%s" % WORKLOAD_VM_UUID, depth=2, direction="both")
        for node in graph["nodes"]:
            print("   [%s] %s (%s)" % (node.get("kind"), node.get("resource_id"), node.get("name")))
        for edge in graph["edges"]:
            print("   %s -[%s]-> %s" % (edge["src_id"], edge["relation"], edge["dst_id"]))

        print("== 3. Agent registration")
        registered = app.agents.upsert(
            {
                "agent_id": "vm-agent-smoke",
                "resource_id": "vm:%s" % WORKLOAD_VM_UUID,
                "configured_vm_uuid": WORKLOAD_VM_UUID,
                "machine_id": "smoke-machine-id",
                "dmi_uuid": "smoke-dmi-uuid",
                "hostname": "workload-vm",
                "ips": ["10.0.0.10"],
                "version": "smoke",
            }
        )
        print("   agent=%s -> %s" % (registered["agent_id"], registered["resource_id"]))

        print("== 4. Inject the Case-1 event chain (cgroup + AppEvent)")
        t0 = _stamp(-6)
        events = [
            {
                "schema_version": "v1",
                "origin": "cgroup",
                "mode": "mock",
                "observed_at": t0,
                "type": "event",
                "event_type": "memory.current",
                "resource_id": "container:%s" % CONTAINER_KEY,
                "source": "vm-agent",
                "payload": {"current": 104000000, "max": 104857600, "ratio": 0.99},
            },
            {
                "schema_version": "v1",
                "origin": "cgroup",
                "mode": "mock",
                "observed_at": _stamp(-4),
                "type": "event",
                "event_type": "memory.events.oom_kill",
                "resource_id": "container:%s" % CONTAINER_KEY,
                "source": "vm-agent",
                "payload": {"delta": 1},
            },
            {
                "event_type": "task.started",
                "task_id": TASK_ID,
                "correlation_id": CORRELATION_ID,
                "service": "agent-service",
                "timestamp": t0,
                "status": "ok",
                "attributes": {"container_id": CONTAINER_KEY},
            },
            {
                "event_type": "task.failed",
                "task_id": TASK_ID,
                "correlation_id": CORRELATION_ID,
                "service": "agent-service",
                "timestamp": _stamp(-2),
                "status": "timeout",
                "attributes": {"container_id": CONTAINER_KEY, "reason": "upstream inference aborted"},
            },
        ]
        summary = app.ingest.ingest_many(
            events, default_origin="app", default_mode="mock", default_source="smoke"
        )
        print("   inserted=%d duplicates=%d warnings=%s" % (summary["inserted"], summary["duplicates"], summary["warnings"] or "-"))

        print("== 5. Correlation engine")
        correlated = app.correlation.correlate(window_seconds=30)
        stats = correlated["stats"]
        print("   clusters=%d evidence=%d events_considered=%d" % (stats["clusters"], stats["evidence"], stats["events_considered"]))
        for cluster in correlated["clusters"]:
            print("   cluster %s rule=%s" % (cluster["cluster_id"], cluster.get("rule")))
            print("     summary: %s" % cluster.get("summary"))
            for item in cluster.get("evidence", []):
                print("     - [%s] %s | %s" % (item.get("kind"), item.get("signal"), item.get("description")))

        print("== 6. Evidence query by correlation_id / resource_id")
        by_corr = app.evidence.query(correlation_id=CORRELATION_ID, limit=50)
        by_resource = app.evidence.query(resource_id="container:%s" % CONTAINER_KEY, limit=50)
        print("   evidence(correlation_id=%s)=%d" % (CORRELATION_ID, len(by_corr)))
        print("   evidence(resource_id=container:%s...)=%d" % (CONTAINER_KEY[:12], len(by_resource)))

        if args.full:
            print(json.dumps(correlated, ensure_ascii=False, indent=2, default=str))

        print("== smoke OK (db=%s)" % db_path)
    except Exception as exc:  # noqa: BLE001
        print("smoke FAILED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        import traceback

        traceback.print_exc()
        exit_code = 1
    finally:
        app.close()
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
