#!/usr/bin/env bash
# Case 3 真实演练（在 workload-vm 上以 sudo 运行）：Agent 工具调用失败
#
#   sudo bash case3-tool-real.sh [down|reset|timeout|latency]
#
# 注入：Toxiproxy 对 tool-service 代理做故障注入（默认 down = 服务不可达 → 连接被拒）
# 观测：tool.result error（Connection refused / reset / timed out）、task.failed、tcp 重传（如内核有）
set -u
WL=/opt/tracesphere/workload
MODE=${1:-down}

echo "== [0] 前置检查 =="
curl -s --max-time 4 http://127.0.0.1:8474/proxies/tool | head -c 200; echo

echo
echo "== [1] 注入工具故障（$MODE）=="
bash "$WL/faults/tool-failure.sh" "$MODE"
sleep 2
curl -s http://127.0.0.1:8474/proxies/tool | head -c 200; echo

echo
echo "== [2] 触发任务（预期工具调用失败）=="
RES=$(bash "$WL/faults/run-task.sh" "工具故障演练任务 - 期望工具调用失败" 2>&1)
echo "$RES" | head -c 400; echo
CORR=$(printf '%s' "$RES" | sed -n 's/.*"correlation_id": *"\([^"]*\)".*/\1/p' | head -1)

echo
echo "== [3] 清除注入 =="
bash "$WL/faults/tool-failure.sh" clear
sleep 2
RES2=$(bash "$WL/faults/run-task.sh" "恢复后的验证任务" 2>&1)
printf '%s' "$RES2" | head -c 200; echo

echo
echo "CORR=$CORR"
