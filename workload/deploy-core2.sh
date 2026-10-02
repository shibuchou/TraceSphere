#!/usr/bin/env bash
set -u
echo "== 尝试 backuptag / 备用源 =="
sudo docker pull shopify/toxiproxy:latest 2>&1 | tail -1
sudo docker pull docker.1panel.live/shopify/toxiproxy:2.11.0 2>&1 | tail -1

echo
echo "== 启动 core（不含 toxiproxy）=="
cd /opt/tracesphere/workload
sudo docker compose up -d prometheus cadvisor tool-service 2>&1 | tail -6

echo
echo "== 状态 =="
sudo docker compose ps --format "table {{.Name}}\t{{.Status}}" | head -8

echo
echo "== Prometheus 抓取目标 =="
sleep 8
curl -s --max-time 5 'http://127.0.0.1:9090/api/v1/targets?state=active' | grep -o '"job":"[a-z-]*"\|"health":"[a-z]*"' | paste - - 2>/dev/null | head -8
