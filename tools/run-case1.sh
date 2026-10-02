#!/usr/bin/env bash
# Case 1 演练编排：容器 OOM → Agent 任务失败 → 证据链串联
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
pgrep -af vm-agent | head -2

echo
echo "== [1] 基线任务（预期成功）=="
bash "$WL/faults/run-task.sh" "OOM 演练前的基线任务" | head -c 260; echo

echo
echo "== [2] 注入 OOM：tool-service 内存上限 8MB（低于 Python 运行所需）=="
sudo docker update --memory=8m --memory-swap=8m tool-service
echo "waiting for OOM kill..."
for i in $(seq 1 15); do
  sleep 2
  RC=$(sudo docker inspect -f '{{.RestartCount}}' tool-service 2>/dev/null || echo 0)
  if [ "$RC" -gt 0 ]; then echo "tool-service restarted (RestartCount=$RC)"; break; fi
done
sudo docker inspect -f 'restarts={{.RestartCount}} status={{.State.Status}}' tool-service

echo
echo "== [3] 触发任务（预期工具调用失败）=="
RES=$(bash "$WL/faults/run-task.sh" "OOM 演练任务 - 期望工具调用失败")
echo "$RES" | head -c 400; echo
CORR=$(echo "$RES" | sed -n 's/.*"correlation_id": "\([^"]*\)".*/\1/p' | head -1)
echo "CORR=$CORR"

echo
echo "== [4] 恢复 tool-service（force-recreate 才能清除 update 施加的限制）=="
cd "$WL"
sudo docker compose up -d --force-recreate tool-service >/dev/null 2>&1
for i in $(seq 1 10); do
  sleep 2
  if curl -s --max-time 3 -X POST http://127.0.0.1:8666/tool -H 'Content-Type: application/json' -d '{"query":"recovery"}' >/dev/null 2>&1; then
    echo "tool-service recovered"; break
  fi
done

echo
echo "== [5] 生成证据链报告 =="
bash /opt/tracesphere/tools/evidence-chain.sh --minutes 4 --container tool-service --corr "$CORR" --out "$EV/case1-oom-chain.md"
echo "report -> $EV/case1-oom-chain.md"

echo
echo "== [6] 恢复后功能确认 =="
bash "$WL/faults/run-task.sh" "恢复后的任务" | head -c 260; echo
