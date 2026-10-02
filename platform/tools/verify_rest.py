#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REST-mode verification against a real ZSvirt management node.

    export ZSVIRT_PASSWORD='...'
    python3 tools/verify_rest.py

Logs in with the real REST API, syncs the Resource Registry, ingests ZSvirt
alarms/events, and prints a report (resources, graph for the workload VM,
alarm event stream). Uses a temporary database unless --db is given.
"""

import argparse
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tsplatform.app import PlatformApp, build_provider  # noqa: E402
from tsplatform.config import load_config  # noqa: E402

WORKLOAD_VM_UUID = "63bbb4613a524e4e97090600af03da93"


def main(argv=None):
    parser = argparse.ArgumentParser(description="TraceSphere platform REST verification")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/zstack/v1")
    parser.add_argument("--account", default="admin")
    parser.add_argument("--password-env", default="ZSVIRT_PASSWORD")
    parser.add_argument("--db", default=None)
    parser.add_argument("--vm-uuid", default=WORKLOAD_VM_UUID)
    args = parser.parse_args(argv)

    temp_dir = None
    if not args.db:
        temp_dir = tempfile.mkdtemp(prefix="ts-rest-verify-")
        args.db = os.path.join(temp_dir, "verify.db")

    cfg = load_config()
    cfg["zsvirt"]["provider"] = "rest"
    cfg["zsvirt"]["base_url"] = args.base_url
    cfg["zsvirt"]["account"] = args.account
    cfg["zsvirt"]["password_env"] = args.password_env
    cfg["platform"]["db_path"] = args.db

    try:
        provider = build_provider(cfg)
    except RuntimeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    app = PlatformApp(cfg, provider=provider)
    exit_code = 0
    try:
        print("== REST sync")
        result = app.sync()
        print(
            "   provider=%s ok=%s resources=%d edges=%d events_ingested=%d events_duplicated=%d"
            % (result.provider, result.ok, result.resources, result.edges,
               result.events_ingested, result.events_duplicated)
        )
        if result.errors:
            print("   errors: %s" % result.errors)

        print("== resources by kind")
        for kind in ("zone", "cluster", "host", "vm", "image", "network", "datastore", "volume", "offering"):
            items = app.resources.list(kind=kind, limit=50)
            for item in items:
                print("   [%-9s] %-42s %s" % (kind, item["resource_id"], item.get("name")))

        print("== workload VM graph (depth=2)")
        graph = app.resources.subgraph("vm:%s" % args.vm_uuid, depth=2)
        for edge in graph["edges"]:
            print("   %s -[%s]-> %s" % (edge["src_id"], edge["relation"], edge["dst_id"]))
        vm = app.resources.get("vm:%s" % args.vm_uuid)
        if vm:
            print("   vm attrs: cpu=%s mem=%s state=%s host=%s" % (
                vm["attributes"].get("cpuNum"), vm["attributes"].get("memorySize"),
                vm["state"], vm["host_id"]))

        print("== ZSvirt alarm / event stream")
        alarms = app.events.query(event_type="zsvirt.alarm", limit=20, order="desc")
        print("   alarm events=%d event events=%d" % (len(alarms), app.events.count(event_type="zsvirt.event")))
        for event in alarms:
            payload = event.get("payload") or {}
            print("   [%s] %s status=%s metric=%s target=%s" % (
                event.get("severity"), payload.get("name"), payload.get("status"),
                payload.get("metricName"), payload.get("targetResourceUuid")))

        print("== verify_rest OK (db=%s)" % args.db)
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print("verify_rest FAILED: %s" % exc, file=sys.stderr)
        exit_code = 1
    finally:
        app.close()
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
