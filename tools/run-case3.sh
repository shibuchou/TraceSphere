#!/usr/bin/env bash
# Case 3 演练编排：工具调用故障（Toxiproxy）→ Agent 任务失败 → 证据链
set -u
EV=/opt/tracesphere/evidence
WL=/opt/tracesphere/workload
sudo mkdir -p "$EV"

echo "== [0] 确保 vm-agent 运行 =="
if ! pgrep -x vm-agent >/dev/null; then
  sudo cp /tmp/vm-agent-psi /opt/tracesphere/vm-agent
  sudo chmod +x /opt/tracesphere/vm-agent
  sudo bash -c 'nohup /opt/tracesphere/vm-agent > /opt/tracesphere/evidence/vm-agent.log 2>&1 &'
  sleep 3
fi
pgrep -x vm-agent >/dev/null && echo "vm-agent running"

echo
echo "== [1] 基线任务（预期成功）=="
bash "$WL/faults/run-task.sh" "工具故障演练基线任务" | head -c 260; echo

echo
echo "== [2] 注入：工具调用延迟 12s（超过 agent 10s 超时）=="
bash "$WL/faults/tool-failure.sh" latency 12000

echo
echo "== [3] 触发任务（预期超时失败）=="
RES=$(bash "$WL/faults/run-task.sh" "工具故障演练任务 - 期望超时失败")
echo "$RES" | head -c 400; echo
CORR=$(echo "$RES" | sed -n 's/.*"correlation_id": "\([^"]*\)".*/\1/p' | head -1)
echo "CORR=$CORR"

echo
echo "== [4] 清除故障 =="
bash "$WL/faults/tool-failure.sh" clear

echo
echo "== [5] 生成证据链报告 =="
bash /opt/tracesphere/tools/evidence-chain.sh --minutes 4 --container toxiproxy \
  --corr "$CORR" --out "$EV/case3-tool-failure-chain.md"
echo "report -> $EV/case3-tool-failure-chain.md"

echo
echo "== [6] 恢复后功能确认 =="
bash "$WL/faults/run-task.sh" "恢复确认任务" | head -c 260; echo
