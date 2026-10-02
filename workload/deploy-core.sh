#!/usr/bin/env bash
# 部署非 llama 依赖的组件（Prometheus / cAdvisor / Toxiproxy / tool-service）
set -u
cd /opt/tracesphere/workload

echo "== 移除独立 cAdvisor（并入 compose）=="
sudo docker rm -f cadvisor >/dev/null 2>&1 || true

echo "== compose up（core 服务）=="
sudo docker compose up -d prometheus cadvisor toxiproxy tool-service 2>&1 | tail -8

echo
echo "== 状态 =="
sudo docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null | head -10

echo
echo "== 等待 toxiproxy 并初始化代理 =="
sleep 5
bash /opt/tracesphere/workload/toxiproxy-init.sh

echo
echo "== 冒烟：tool-service 直连 + 经代理 =="
sleep 2
curl -s --max-time 5 -X POST http://127.0.0.1:8666/tool -H 'Content-Type: application/json' -d '{"query":"smoke"}' | head -c 200
echo
echo "== Prometheus 目标状态 =="
sleep 6
curl -s --max-time 5 'http://127.0.0.1:9090/api/v1/targets?state=active' | grep -o '"health":"[a-z]*"' | sort | uniq -c
