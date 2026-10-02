#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe candidate ZSvirt API paths (W1 endpoint verification helper).

    export ZSVIRT_PASSWORD='...'
    python3 tools/probe_paths.py

Prints one line per candidate path: HTTP status, error code, and the response
keys / total so real field names and query paths can be frozen into
``config/zsvirt.paths`` and ``tools/capture_fixtures.py``.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tsplatform.zsvirt.rest import ZSvirtError, ZSvirtRestClient  # noqa: E402

DEFAULT_ZONE = "26fd04cdf31047e4a96aff5e41225420"
DEFAULT_CLUSTER = "a29a9e1c13ac4017a187e30fca573625"

PROBES = (
    (
        "primary-storages",
        [
            "primary-storages",
            "primary-storage",
            "storage/primary-storages",
            "clusters/{cluster}/primary-storages",
            "zones/{zone}/primary-storages",
            "system/primary-storages",
        ],
    ),
    (
        "backup-storages",
        [
            "backup-storages",
            "backup-storage",
            "image-stores",
            "zones/{zone}/backup-storages",
            "system/backup-storages",
        ],
    ),
    ("port-groups", ["l2-networks/port-groups", "port-groups", "l2-networks/vswitch/port-groups"]),
    ("alarms", ["zwatch/alarms", "alarms", "zwatch/trigger-actions"]),
    ("events", ["zwatch/events", "events"]),
    ("vm-instances", ["vm-instances", "vm-instances/status/Running"]),
    ("l2-networks", ["l2-networks", "l2-networks/vswitch"]),
)


def probe(client, path):
    try:
        payload = client._request("GET", path, params={"limit": 1, "start": 0})
    except ZSvirtError as exc:
        return {"ok": False, "status": exc.status, "code": exc.code, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"ok": True, "type": type(payload).__name__}
    keys = sorted(payload.keys())
    count = None
    for key in ("inventories", "events"):
        if isinstance(payload.get(key), list):
            count = len(payload[key])
            break
    return {
        "ok": True,
        "keys": keys,
        "count": count,
        "total": payload.get("total"),
        "success": payload.get("success"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Probe ZSvirt API paths")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/zstack/v1")
    parser.add_argument("--account", default="admin")
    parser.add_argument("--password", default=None)
    parser.add_argument("--password-env", default="ZSVIRT_PASSWORD")
    parser.add_argument("--zone", default=DEFAULT_ZONE)
    parser.add_argument("--cluster", default=DEFAULT_CLUSTER)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)

    password = args.password or os.environ.get(args.password_env)
    if not password:
        print("error: set %s (or --password)" % args.password_env, file=sys.stderr)
        return 2

    client = ZSvirtRestClient(args.base_url, args.account, password, timeout=args.timeout)
    try:
        client.login()
    except ZSvirtError as exc:
        print("login failed: %s" % exc, file=sys.stderr)
        return 1

    for logical, candidates in PROBES:
        print("== %s" % logical)
        for candidate in candidates:
            path = candidate.format(zone=args.zone, cluster=args.cluster)
            result = probe(client, path)
            if result["ok"]:
                print(
                    "   OK   %-38s keys=%s total=%s count=%s"
                    % (path, ",".join(result.get("keys") or []), result.get("total"), result.get("count"))
                )
            else:
                print(
                    "   FAIL %-38s status=%s code=%s %s"
                    % (path, result.get("status"), result.get("code"), result.get("error"))
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
