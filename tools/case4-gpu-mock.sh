#!/usr/bin/env bash
# Case 4 演练编排（在 GPU1 运行）：Mock DCGM 模拟 GPU 显存耗尽 → 证据链 → 诊断
#
#   export TRACESPHERE_VM_HOST / TRACESPHERE_VM_UUID / VM_PASSWORD / ZSVIRT_PASSWORD 后：
#   bash tools/case4-gpu-mock.sh
#
# 前置：平台已开启 mock_gpu（TRACESPHERE_MOCK_GPU=1 且 TRACESPHERE_MOCK_GPU_VM 指向业务 VM），
#       VM 内 mock-dcgm 容器在运行（docker compose up -d mock-dcgm）。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VM=${TRACESPHERE_VM_HOST:?请先 export TRACESPHERE_VM_HOST（业务 VM IP）}
VM_UUID=${TRACESPHERE_VM_UUID:?请先 export TRACESPHERE_VM_UUID（ZSvirt VM uuid）}
PLATFORM=${TRACESPHERE_PLATFORM_URL:-http://127.0.0.1:8000}
# CLI 诊断进程单独读取环境变量：Prometheus 指向业务 VM（与 systemd 单元一致）
export TRACESPHERE_PROMETHEUS_URL=${TRACESPHERE_PROMETHEUS_URL:-http://$VM:9090}
# 平台 API Token（平台启用 TRACESPHERE_API_TOKEN 时必填）
AUTH=()
if [ -n "${TRACESPHERE_API_TOKEN:-}" ]; then
  AUTH=(-H "Authorization: Bearer ${TRACESPHERE_API_TOKEN}")
fi
# RCA CLI（diagnose/capture）通过该变量访问平台（与 systemd rca.env 一致）
export TRACESPHERE_PLATFORM_TOKEN=${TRACESPHERE_PLATFORM_TOKEN:-${TRACESPHERE_API_TOKEN:-}}
SSH="sshpass -p ${VM_PASSWORD:?请先 export VM_PASSWORD（业务 VM SSH 密码）} ssh -o StrictHostKeyChecking=no ubuntu@$VM"
GPU_RID=${TRACESPHERE_GPU_RESOURCE_ID:-gpu:mock-gpu0}
WL=/opt/tracesphere/workload
OUT=/tmp/final
mkdir -p "$OUT"

echo "== [0] 前置：mock-dcgm 状态 =="
$SSH "curl -s --max-time 5 http://127.0.0.1:9400/state" 2>&1 | tail -1; echo

echo
echo "== [0b] 重置平台数据（干净基线；直报不中断）=="
bash "$ROOT/tools/reset-platform.sh" | tail -1
sleep 16   # 等一轮探针/指标采样重新入库

echo
echo "== [1] 基线任务（预期成功）=="
$SSH "bash $WL/faults/run-task.sh 'GPU 演练前的基线任务'" 2>&1 | tail -c 160; echo

echo
echo "== [2] 注入模拟显存耗尽（POST /inject mode=exhaust）=="
$SSH "curl -s --max-time 5 -X POST http://127.0.0.1:9400/inject -H 'Content-Type: application/json' -d '{\"mode\":\"exhaust\"}'" 2>&1 | tail -1
sleep 8

echo
echo "== [3] 触发任务并抓取 correlation_id =="
RES=$($SSH "bash $WL/faults/run-task.sh 'GPU 显存耗尽演练任务（Mock DCGM）'" 2>&1)
printf '%s\n' "$RES" | tail -c 220; echo
CORR=$(printf '%s' "$RES" | sed -n 's/.*"correlation_id": *"\([^"]*\)".*/\1/p' | head -1)

echo
echo "== [4] 恢复模拟状态（mode=normal）=="
$SSH "curl -s --max-time 5 -X POST http://127.0.0.1:9400/inject -H 'Content-Type: application/json' -d '{\"mode\":\"normal\"}'" 2>&1 | tail -1
sleep 10

echo
echo "== [5] 关联 + 诊断（资源锚点：$GPU_RID）=="
curl -s --max-time 60 -X POST "${AUTH[@]}" "$PLATFORM/api/v1/correlate" -H 'Content-Type: application/json' \
  -d '{"window_seconds":5}' | python3 -c "import json,sys;print(' ',json.load(sys.stdin).get('stats'))" 2>/dev/null
cd "$ROOT/rca" || exit 1
./bin/tracesphere diagnose --resource-id "$GPU_RID" --window 10m > "$OUT/case4-gpu-mock.txt" 2>&1
head -22 "$OUT/case4-gpu-mock.txt"

echo
echo "== [6] 抓取回放 fixture =="
./bin/tracesphere capture --scenario case4-gpu-mock --resource-id "$GPU_RID" --window 10m \
    --out fixtures --description "Mock DCGM 降级模式抓取（2026-09-21）：GPU 显存耗尽" 2>&1 | tail -2

echo
echo "CORR=$CORR"
