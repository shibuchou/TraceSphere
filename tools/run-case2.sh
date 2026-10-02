#!/usr/bin/env bash
# Case 2 演练编排：CPU 资源争抢 → 服务延迟升高 → 证据链
set -u
EV=/opt/tracesphere/evidence
WL=/opt/tracesphere/workload
sudo mkdir -p "$EV"

task_wall() { # 输出 wall_ms + 响应片段
  local q="$1"
  local t0 t1 resp ms corr
  t0=$(date +%s%N)
  resp=$(bash "$WL/faults/run-task.sh" "$q")
  t1=$(date +%s%N)
  ms=$(( (t1 - t0) / 1000000 ))
  corr=$(echo "$resp" | sed -n 's/.*"correlation_id": "\([^"]*\)".*/\1/p' | head -1)
  echo "wall_ms=$ms corr=$corr"
}

echo "== [0] 确保 vm-agent 运行 =="
if ! pgrep -x vm-agent >/dev/null; then
  sudo cp /tmp/vm-agent-psi /opt/tracesphere/vm-agent
  sudo chmod +x /opt/tracesphere/vm-agent
  sudo bash -c 'nohup /opt/tracesphere/vm-agent > /opt/tracesphere/evidence/vm-agent.log 2>&1 &'
  sleep 3
fi
echo "vm-agent $(pgrep -x vm-agent >/dev/null && echo running)"

echo
echo "== [1] 基线任务 ×2 =="
for i in 1 2; do echo "baseline$i: $(task_wall "CPU 演练基线任务$i")"; done

echo
echo "== [2] 注入 CPU 争抢（2 个满载 worker，cpus=2）=="
bash "$WL/faults/cpu.sh"
sleep 5
sudo docker inspect -f 'cpu-stress status={{.State.Status}}' cpu-stress

echo
echo "== [3] 争抢期间任务 ×2 =="
RES1=$(task_wall "CPU 争抢期间任务A")
echo "stressedA: $RES1"
CORR=$(echo "$RES1" | sed -n 's/.*corr=\([^ ]*\).*/\1/p')
RES2=$(task_wall "CPU 争抢期间任务B")
echo "stressedB: $RES2"

echo
echo "== [4] 生成证据链报告（目标：cpu-stress，仍在线）=="
bash /opt/tracesphere/tools/evidence-chain.sh --minutes 4 --container cpu-stress \
  --corr "$CORR" --out "$EV/case2-cpu-chain.md" >/dev/null
echo "report -> $EV/case2-cpu-chain.md"

echo
echo "== [5] 停止压力 =="
sudo docker rm -f cpu-stress >/dev/null 2>&1 || true
sleep 3

echo "== [6] 恢复后任务 =="
echo "recovery: $(task_wall "CPU 恢复确认任务")"

echo
echo "== [7] 报告摘要 =="
grep -E "wall_ms|psi_cpu|container_memory_working_set_bytes" "$EV/case2-cpu-chain.md" | head -12
