#!/usr/bin/env bash
# platform 数据重置（在 GPU1 上运行）：停服务 → 清空 SQLite WAL → 重启 → 重新同步 ZSvirt 资源
#
#   bash tools/reset-platform.sh
#
# 用途：演示前获得干净基线，避免历史事件/历史 OOM 证据影响当前诊断的关联与评分。
# 兼容两种运行方式：systemd（tracesphere-platform）优先，否则 nohup。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/platform" || exit 1
mkdir -p data

if systemctl list-unit-files tracesphere-platform.service >/dev/null 2>&1; then
  sudo -n systemctl stop tracesphere-platform 2>/dev/null || true
  sleep 1
  rm -f data/tracesphere.db data/tracesphere.db-wal data/tracesphere.db-shm
  echo "db reset: $(pwd)/data/tracesphere.db (systemd)"
  sudo -n systemctl start tracesphere-platform
else
  pkill -f "run.py --provider rest" 2>/dev/null
  sleep 1
  rm -f data/tracesphere.db data/tracesphere.db-wal data/tracesphere.db-shm
  echo "db reset: $(pwd)/data/tracesphere.db (nohup)"
  ZSVIRT_PASSWORD=${ZSVIRT_PASSWORD:?请先 export ZSVIRT_PASSWORD} nohup python3 run.py --provider rest \
      --host 0.0.0.0 --port 8000 --db data/tracesphere.db > data/platform.log 2>&1 &
fi
sleep 6
curl -s --max-time 10 http://127.0.0.1:8000/api/v1/health | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('provider', d['provider']['name'], d['provider']['mode'], '| counts', d['database']['counts'])
"
