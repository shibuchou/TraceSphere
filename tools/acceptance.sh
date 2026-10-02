#!/usr/bin/env bash
# TraceSphere 三场景验收脚本（在 GPU1 上运行）：干净基线 → 注入 → 采集 → 关联 → RCA → 抓取 fixture
#
#   bash tools/acceptance.sh
#
# 前置：demo-up.sh 已起（platform + RCA）；vm-agent 直报（systemd 服务）已部署。
# 本脚本每个场景会重置 platform DB 以获得干净基线（直报数据源不中断）。
# 产出：/tmp/final/case{1,2,3}*.txt（诊断报告）+ rca/fixtures/*.json（真实回放数据）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 部署环境参数（必填）
VM=${TRACESPHERE_VM_HOST:?请先 export TRACESPHERE_VM_HOST（业务 VM IP）}
VM_UUID=${TRACESPHERE_VM_UUID:?请先 export TRACESPHERE_VM_UUID（ZSvirt VM uuid）}
PLATFORM=${TRACESPHERE_PLATFORM_URL:-http://127.0.0.1:8000}
# CLI 诊断进程单独读取环境变量：Prometheus 指向业务 VM（与 systemd 单元一致）
export TRACESPHERE_PROMETHEUS_URL=${TRACESPHERE_PROMETHEUS_URL:-http://$VM:9090}
# 平台 API Token（平台启用 TRACESPHERE_API_TOKEN 时必填，直报链路同值）
AUTH=()
if [ -n "${TRACESPHERE_API_TOKEN:-}" ]; then
  AUTH=(-H "Authorization: Bearer ${TRACESPHERE_API_TOKEN}")
fi
# RCA CLI（diagnose/capture）通过该变量访问平台（与 systemd rca.env 一致）
export TRACESPHERE_PLATFORM_TOKEN=${TRACESPHERE_PLATFORM_TOKEN:-${TRACESPHERE_API_TOKEN:-}}
SSH="sshpass -p ${VM_PASSWORD:?请先 export VM_PASSWORD（业务 VM SSH 密码）} ssh -o StrictHostKeyChecking=no ubuntu@$VM"
WL=/opt/tracesphere/workload
OUT=/tmp/final
mkdir -p "$OUT"

ensure_vm_agent() {
  $SSH 'sudo systemctl restart tracesphere-vm-agent; sleep 2; systemctl is-active tracesphere-vm-agent' 2>/dev/null | tail -1
}
reset_db() { bash "$ROOT/tools/reset-platform.sh" | tail -1; }

run_case() {  # $1=场景名 $2=注入命令 $3=恢复命令 $4=任务问题
  local SCEN=$1 INJECT=$2 RESTORE=$3 QUESTION=$4
  echo "══════════════ $SCEN ══════════════"
  reset_db
  echo "--- vm-agent 直报就绪：$(ensure_vm_agent) ---"
  echo "--- 注入 ---"; $SSH "$INJECT" 2>&1 | tail -3
  sleep 3
  echo "--- 触发任务 ---"
  local RES; RES=$($SSH "bash $WL/faults/run-task.sh '$QUESTION'" 2>&1)
  printf '%s\n' "$RES" | tail -c 260; echo
  local CORR; CORR=$(printf '%s' "$RES" | sed -n 's/.*"correlation_id": *"\([^"]*\)".*/\1/p' | head -1)
  echo "--- 恢复 ---"; $SSH "$RESTORE" 2>&1 | tail -2
  sleep 14
  echo "--- 平台入库（直报）---"
  curl -s --max-time 5 "${AUTH[@]}" $PLATFORM/api/v1/health | python3 -c "import json,sys;print(' ',json.load(sys.stdin)['database']['counts'])" 2>/dev/null
  echo "--- 关联 ---"
  curl -s --max-time 60 -X POST "${AUTH[@]}" "$PLATFORM/api/v1/correlate" -H 'Content-Type: application/json' \
    -d '{"window_seconds":5}' | python3 -c "import json,sys;d=json.load(sys.stdin);print(' ',d.get('stats'))"
  echo "--- RCA 诊断 ---"
  cd "$HOME/tracesphere/rca" || exit 1
  ./bin/tracesphere diagnose --correlation-id "$CORR" --window 10m > "$OUT/$SCEN.txt" 2>&1
  head -18 "$OUT/$SCEN.txt"
  echo "--- 抓取真实 fixture ---"
  ./bin/tracesphere capture --scenario "$SCEN" --correlation-id "$CORR" --window 10m \
      --out fixtures --description "真实环境抓取（2026-09-21，GPU1 + workload-vm）：$QUESTION" 2>&1 | tail -2
  echo
}

run_case "case1-oom" \
  "for a in 1 2 3 4; do sudo docker update --memory=8m --memory-swap=8m tool-service 2>&1 | tail -1; sleep 6; RC=\$(sudo docker inspect -f '{{.RestartCount}}' tool-service); if ! curl -s --max-time 4 -X POST http://127.0.0.1:8666/tool -H 'Content-Type: application/json' -d '{\"query\":\"probe\"}' >/dev/null 2>&1; then echo \"tool-service 不可达 (RestartCount=\$RC, attempt=\$a)\"; break; fi; echo \"attempt \$a: 工具仍可用 (RestartCount=\$RC)\"; done; sudo docker inspect -f 'restarts={{.RestartCount}} oomkilled={{.State.OOMKilled}} status={{.State.Status}}' tool-service" \
  "cd $WL && sudo docker compose up -d --force-recreate tool-service >/dev/null 2>&1; sleep 8; echo tool-service-restored" \
  "OOM 演练任务 - 期望工具调用失败"

run_case "case2-cpu" \
  "bash $WL/faults/cpu.sh; sudo docker update --cpus=0.5 llama-server; sleep 4; sudo docker inspect -f 'llama cpus={{.HostConfig.NanoCpus}}' llama-server" \
  "sudo docker rm -f cpu-stress >/dev/null 2>&1; sudo docker update --cpus=0 llama-server; cd $WL && sudo docker compose up -d --force-recreate llama-server >/dev/null 2>&1; sleep 12; echo cpu-restored" \
  "CPU 争抢演练任务 - 期望推理超时"

run_case "case3-tool-failure" \
  "bash $WL/faults/tool-failure.sh down; sleep 2; curl -s http://127.0.0.1:8474/proxies/tool | head -c 160; echo" \
  "bash $WL/faults/tool-failure.sh clear; sleep 2; echo tool-restored" \
  "工具故障演练任务 - 期望连接失败"

# Case 4：Mock DCGM 模拟显存耗尽（无 GPU 降级模式，赛题 §4）；资源锚点诊断
echo "══════════════ case4-gpu-mock ══════════════"
reset_db
echo "--- vm-agent 直报就绪：$(ensure_vm_agent) ---"
echo "--- 注入（Mock DCGM 显存耗尽）---"
$SSH "curl -s --max-time 5 -X POST http://127.0.0.1:9400/inject -H 'Content-Type: application/json' -d '{\"mode\":\"exhaust\"}'; sleep 6" 2>&1 | tail -2
echo "--- 触发任务 ---"
RES=$($SSH "bash $WL/faults/run-task.sh 'GPU 显存耗尽演练任务（Mock DCGM）'" 2>&1)
printf '%s\n' "$RES" | tail -c 260; echo
CORR=$(printf '%s' "$RES" | sed -n 's/.*"correlation_id": *"\([^"]*\)".*/\1/p' | head -1)
echo "--- 恢复 ---"
$SSH "curl -s --max-time 5 -X POST http://127.0.0.1:9400/inject -H 'Content-Type: application/json' -d '{\"mode\":\"normal\"}'" 2>&1 | tail -1
sleep 14
echo "--- 平台入库（直报）---"
curl -s --max-time 5 "${AUTH[@]}" $PLATFORM/api/v1/health | python3 -c "import json,sys;print(' ',json.load(sys.stdin)['database']['counts'])" 2>/dev/null
echo "--- 关联 ---"
curl -s --max-time 60 -X POST "${AUTH[@]}" "$PLATFORM/api/v1/correlate" -H 'Content-Type: application/json' \
  -d '{"window_seconds":5}' | python3 -c "import json,sys;d=json.load(sys.stdin);print(' ',d.get('stats'))"
echo "--- RCA 诊断（资源锚点：GPU）---"
cd "$HOME/tracesphere/rca" || exit 1
GPU_RID=${TRACESPHERE_GPU_RESOURCE_ID:-gpu:mock-gpu0}
./bin/tracesphere diagnose --resource-id "$GPU_RID" --window 10m > "$OUT/case4-gpu-mock.txt" 2>&1
head -18 "$OUT/case4-gpu-mock.txt"
echo "--- 抓取真实 fixture ---"
./bin/tracesphere capture --scenario case4-gpu-mock --resource-id "$GPU_RID" --window 10m \
    --out fixtures --description "Mock DCGM 降级模式抓取（2026-09-21）：GPU 显存耗尽" 2>&1 | tail -2
echo

echo "══════════════ 汇总 ══════════════"
for f in "$OUT"/case*.txt; do
  echo "--- $(basename "$f")"
  grep -E '^\[1\]|Evidence Match|数据源|说明' "$f" | head -4 || true
done

