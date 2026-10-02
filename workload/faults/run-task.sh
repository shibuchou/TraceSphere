#!/usr/bin/env bash
# 触发一次 Agent 任务（正常链路冒烟）
# 用法: run-task.sh [question]
# 可选：TASK_TOKEN 环境变量（与 agent-service 的 TASK_TOKEN 一致时自动加 X-Task-Token）
set -u
Q=${1:-请用一句话介绍虚拟机可观测性}
HDR=(-H 'Content-Type: application/json')
if [ -n "${TASK_TOKEN:-}" ]; then
  HDR+=(-H "X-Task-Token: ${TASK_TOKEN}")
fi
curl -s --max-time 180 -X POST http://127.0.0.1:8082/task \
  "${HDR[@]}" \
  -d "{\"question\": \"$Q\"}"
echo
