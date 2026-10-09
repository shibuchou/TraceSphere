#!/usr/bin/env bash
# REST-mode HTTP smoke for the TraceSphere platform.
#
# Run on a host that can reach the ZSvirt management API (e.g. GPU1):
#   export ZSVIRT_PASSWORD='...'
#   bash tools/rest_http_smoke.sh
#
# Starts run.py in REST mode on 127.0.0.1:$PORT with a throwaway SQLite DB,
# exercises health / sync / graph / alarm-event endpoints, then stops it.
set -euo pipefail

PORT="${PORT:-8010}"
DB="${DB:-/tmp/ts-rest-smoke.db}"
BASE="http://127.0.0.1:${PORT}"
cd "$(dirname "$0")/.."

if [ -z "${ZSVIRT_PASSWORD:-}" ]; then
    echo "error: set ZSVIRT_PASSWORD" >&2
    exit 2
fi

rm -f "$DB" "$DB-wal" "$DB-shm"
export ZSVIRT_PASSWORD
nohup python3 run.py --provider rest --host 127.0.0.1 --port "$PORT" --db "$DB" \
    > /tmp/ts-rest-smoke.log 2>&1 &
PID=$!
cleanup() {
    kill "$PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 5

python3 - "$BASE" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]


def call(path, method="GET"):
    request = urllib.request.Request(base + path, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


health = call("/api/v1/health")
print("health: status=%s provider=%s/%s resources=%s events=%s" % (
    health["status"], health["provider"]["name"], health["provider"]["mode"],
    health["database"]["counts"]["resources"], health["database"]["counts"]["events"]))

sync = call("/api/v1/resources/sync", method="POST")
print("sync: ok=%s resources=%d edges=%d events_ingested=%d duplicates=%d" % (
    sync["ok"], sync["resources"], sync["edges"], sync["events_ingested"], sync["events_duplicated"]))

graph = call("/api/v1/resources/vm:a1b2c3d456784b7d8e9f0a1b2c3d4e5f/graph?depth=1")
print("graph: nodes=%d edges=%d" % (len(graph["nodes"]), len(graph["edges"])))
for edge in graph["edges"]:
    print("  %s -[%s]-> %s" % (edge["src_id"], edge["relation"], edge["dst_id"]))

alarms = call("/api/v1/events?event_type=zsvirt.alarm")
print("alarm events: total=%d" % alarms["total"])
for event in alarms["events"]:
    print("  [%s] %s status=%s" % (
        event["severity"], event["payload"].get("name"), event["payload"].get("status")))

zwatch = call("/api/v1/events?event_type=zsvirt.event")
print("zwatch events: total=%d" % zwatch["total"])
PY

echo "rest_http_smoke OK (db=$DB)"
