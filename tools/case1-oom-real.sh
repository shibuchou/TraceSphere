#!/usr/bin/env bash
# Case 1 真实演练（在 workload-vm 上以 root/sudo 运行）：容器 OOM → Agent 工具调用失败
#
#   sudo bash case1-oom-real.sh [case-dir] [memory-limit]
#
# 说明：`docker update --memory` 在容器重启窗口内偶发 runc 报错，因此这里"重试 + 探活"，
# 直到工具服务真的不可达（或达到重试上限）再触发 Agent 任务；结束自动还原 tool-service。
set -u
CASE_DIR=${1:-/tmp/tracesphere-cases}
LIMIT=${2:-8m}
WL=/opt/tracesphere/workload
mkdir -p "$CASE_DIR"

echo "== [0] 前置检查 =="
pgrep -a vm-agent | head -2 || echo "警告：vm-agent 未运行"
systemctl is-active tracesphere-vm-agent >/dev/null 2>&1 && echo "vm-agent 直报运行中" || echo "提示：vm-agent 未运行（证据不会入库）"

echo
echo "== [1] 基线任务（预期成功）=="
bash "$WL/faults/run-task.sh" "OOM 演练前的基线任务" > "$CASE_DIR/case1-baseline.json" 2>&1
tail -c 160 "$CASE_DIR/case1-baseline.json"; echo

echo
echo "== [2] 注入 OOM：tool-service 内存上限 $LIMIT（重试 + 探活）=="
for attempt in 1 2 3 4; do
  sudo docker update --memory="$LIMIT" --memory-swap="$LIMIT" tool-service 2>&1 | tail -1
  sleep 6
  RESTARTS=$(sudo docker inspect -f '{{.RestartCount}}' tool-service 2>/dev/null || echo 0)
  if ! curl -s --max-time 4 -X POST http://127.0.0.1:8666/tool \
        -H 'Content-Type: application/json' -d '{"query":"probe"}' >/dev/null 2>&1; then
    echo "tool-service 已不可达（attempt=$attempt, RestartCount=$RESTARTS）"
    break
  fi
  echo "attempt $attempt：工具仍可用（RestartCount=$RESTARTS），继续加压"
done
sudo docker inspect -f 'restarts={{.RestartCount}} oomkilled={{.State.OOMKilled}} status={{.State.Status}}' tool-service

echo
echo "== [3] 触发任务（预期工具调用失败）=="
RES=$(bash "$WL/faults/run-task.sh" "OOM 演练任务 - 期望工具调用失败" 2>&1)
echo "$RES" | head -c 400; echo
echo "$RES" > "$CASE_DIR/case1-failed-task.json"
CORR=$(printf '%s' "$RES" | sed -n 's/.*"correlation_id": *"\([^"]*\)".*/\1/p' | head -1)

echo
echo "== [4] 恢复 tool-service =="
cd "$WL" || exit 1
sudo docker compose up -d --force-recreate tool-service >/dev/null 2>&1
for i in $(seq 1 10); do
  sleep 2
  if curl -s --max-time 3 -X POST http://127.0.0.1:8666/tool \
      -H 'Content-Type: application/json' -d '{"query":"recovery"}' >/dev/null 2>&1; then
    echo "tool-service 已恢复"; break
  fi
done

echo
echo "CORR=$CORR"
