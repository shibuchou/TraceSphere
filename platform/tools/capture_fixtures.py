#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture raw ZSvirt REST responses into ``fixtures/`` (run where ZSvirt is reachable).

Example (on a host that can reach the ZSvirt management API)::

    export ZSVIRT_PASSWORD='<admin password>'
    python3 tools/capture_fixtures.py --out fixtures

The script stores every response exactly as returned (official ZStack shape
``{"inventories": [...], "total": N}``), probes candidate paths for the
unverified ``QueryAlarm`` / ``QueryEvent`` endpoints, checks clock skew
between the management node and this host, and updates ``fixtures/_capture.json``.
The password and the OAuth session uuid are never written or printed.
"""

import argparse
import email.utils
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tsplatform.util import format_rfc3339, now_utc, parse_timestamp  # noqa: E402
from tsplatform.zsvirt.rest import ZSvirtError, ZSvirtRestClient  # noqa: E402

# (fixture filename, primary path, candidate paths); {zone}/{cluster} are
# substituted from the already-captured zones/clusters responses
COLLECTIONS = (
    ("zones", "zones", ["zones"]),
    ("clusters", "clusters", ["clusters"]),
    ("hosts", "hosts", ["hosts"]),
    ("vms", "vm-instances", ["vm-instances"]),
    ("images", "images", ["images"]),
    ("l3-networks", "l3-networks", ["l3-networks"]),
    ("l2-networks", "l2-networks", ["l2-networks"]),
    ("port-groups", "l2-networks/port-groups", ["l2-networks/port-groups", "port-groups"]),
    (
        "primary-storages",
        "primary-storage",  # verified on real ZSvirt 2026-09-20 (singular)
        [
            "primary-storage",
            "primary-storages",
            "storage/primary-storages",
        ],
    ),
    (
        "backup-storages",
        "backup-storage",  # verified on real ZSvirt 2026-09-20 (singular)
        [
            "backup-storage",
            "backup-storages",
            "image-stores",
        ],
    ),
    ("instance-offerings", "instance-offerings", ["instance-offerings"]),
    ("alerts", "zwatch/alarms", ["zwatch/alarms", "alarms"]),
    ("events", "zwatch/events", ["zwatch/events", "events"]),
)

CORE_COLLECTIONS = ("zones", "clusters", "hosts", "vms")


def clock_check(base_url, timeout=10.0):
    """Compare server Date header with local UTC; returns dict with skew seconds."""
    request = urllib.request.Request(base_url.rstrip("/") + "/", method="GET")
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        try:
            response = urllib.request.urlopen(request, timeout=timeout, context=context)
            header = response.headers.get("Date")
        except urllib.error.HTTPError as exc:
            header = exc.headers.get("Date")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if not header:
        return {"ok": False, "error": "no Date header"}
    server_time = email.utils.parsedate_to_datetime(header)
    local_time = now_utc()
    skew = (server_time - local_time).total_seconds()
    return {
        "ok": True,
        "server_date": header,
        "local_time": format_rfc3339(local_time),
        "skew_seconds": round(skew, 3),
        "warning": "clock skew exceeds ±5s correlation window" if abs(skew) > 5 else None,
    }


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def capture(client, out_dir, quiet=False):
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    context = {"zone": "", "cluster": ""}
    for filename, primary, candidates in COLLECTIONS:
        chosen = None
        payload = None
        errors = []
        for candidate in candidates:
            path = candidate.format(**context)
            try:
                payload = client.query(path)
                chosen = path
                break
            except ZSvirtError as exc:
                errors.append("%s: %s" % (path, exc))
        if payload is None:
            results[filename] = {"ok": False, "errors": errors}
            if not quiet:
                print("FAIL  %-20s %s" % (filename, "; ".join(errors)))
            continue
        write_json(os.path.join(out_dir, filename + ".json"), payload)
        total = payload.get("total") if isinstance(payload, dict) else None
        results[filename] = {"ok": True, "path": chosen, "total": total}
        if not quiet:
            print("OK    %-20s path=%-30s total=%s" % (filename, chosen, total))
        if filename in ("zones", "clusters"):
            items = payload.get("inventories") or []
            if items:
                context[filename.rstrip("s")] = items[0].get("uuid") or ""
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Capture ZSvirt fixtures")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/zstack/v1")
    parser.add_argument("--account", default="admin")
    parser.add_argument("--password", default=None, help="prefer --password-env/ZSVIRT_PASSWORD over this flag")
    parser.add_argument("--password-env", default="ZSVIRT_PASSWORD")
    parser.add_argument("--out", default=os.path.join(ROOT, "fixtures"))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--no-clock-check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    password = args.password or os.environ.get(args.password_env)
    if not password:
        print("error: set %s (or --password); password is never stored" % args.password_env, file=sys.stderr)
        return 2

    client = ZSvirtRestClient(
        base_url=args.base_url,
        account=args.account,
        password=password,
        timeout=args.timeout,
        verify_tls=False,
        page_size=args.page_size,
    )
    try:
        client.login()
    except ZSvirtError as exc:
        print("login failed: %s" % exc, file=sys.stderr)
        return 1
    if not args.quiet:
        print("login ok (%s)" % args.base_url)

    clock = {"ok": False, "skipped": True} if args.no_clock_check else clock_check(args.base_url, args.timeout)
    if not args.quiet and not clock.get("skipped"):
        print("clock check: %s" % json.dumps(clock, ensure_ascii=False))

    results = capture(client, args.out, quiet=args.quiet)

    meta_path = os.path.join(args.out, "_capture.json")
    meta = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
        except ValueError:
            meta = {}
    meta.update(
        {
            "provider": "fixture",
            "provisional": False,
            "captured_at": format_rfc3339(now_utc()),
            "base_url": args.base_url,
            "account": args.account,
            "note": (
                "Real ZSvirt REST responses captured as-is. Do not edit by hand; "
                "re-run tools/capture_fixtures.py on the KVM host to refresh."
            ),
            "paths": {
                filename: entry.get("path")
                for filename, entry in results.items()
                if entry.get("ok")
            },
            "clock": clock,
            "results": results,
        }
    )
    write_json(meta_path, meta)

    failed_core = [name for name in CORE_COLLECTIONS if not results.get(name, {}).get("ok")]
    if failed_core:
        print("core collections failed: %s" % ", ".join(failed_core), file=sys.stderr)
        return 1
    if not args.quiet:
        print("captured into %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
