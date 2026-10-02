#!/usr/bin/env bash
# Case 2 真实演练（在 workload-vm 上以 sudo 运行）：CPU 争抢 → 推理超时 → Agent 任务失败
#
#   sudo bash case2-cpu-real.sh
#
# 注入：① cpu-stress 容器打满 vCPU；② 收紧 llama-server 的 cpu.max（--cpus=0.5）
# 观测：PSI cpu.some 升高、cgroup/cAdvisor 节流计数递增、推理 duration_ms 暴涨 → 任务超时
set -u
WL=/opt/tracesphere/workload

echo "== [0] 前置检查 =="
pgrep -a vm-agent | head -2 || echo "警告：vm-agent 未运行"

echo
echo "== [1] 注入 CPU 争抢 =="
bash "$WL/faults/cpu.sh"
sudo docker update --cpus=0.5 llama-server
sleep 4
sudo docker inspect -f 'llama-server cpus={{.HostConfig.NanoCpus}}' llama-server
sudo docker inspect -f 'cpu-stress cpus={{.HostConfig.NanoCpus}} status={{.State.Status}}' cpu-stress

echo
echo "== [2] 触发任务（预期推理超时，客户端 120s 上限）=="
RES=$(bash "$WL/faults/run-task.sh" "CPU 争抢演练任务 - 期望推理超时" 2>&1)
echo "$RES" | head -c 400; echo
CORR=$(printf '%s' "$RES" | sed -n 's/.*"correlation_id": *"\([^"]*\)".*/\1/p' | head -1)

echo
echo "== [3] 恢复 =="
sudo docker rm -f cpu-stress >/dev/null 2>&1
sudo docker update --cpus=0 llama-server >/dev/null 2>&1
cd "$WL" && sudo docker compose up -d --force-recreate llama-server >/dev/null 2>&1
for i in $(seq 1 15); do
  sleep 2
  if curl -s --max-time 4 http://127.0.0.1:8081/health >/dev/null 2>&1; then echo "llama-server 已恢复"; break; fi
done

echo
echo "CORR=$CORR"
