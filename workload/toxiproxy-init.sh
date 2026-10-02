#!/usr/bin/env bash
# 初始化 Toxiproxy 代理：8666 -> tool-service:9000
set -u
API=http://127.0.0.1:8474

echo "== 等待 toxiproxy 就绪 =="
for i in $(seq 1 20); do
  if curl -s --max-time 3 "$API/version" >/dev/null 2>&1; then echo "ready"; break; fi
  sleep 2
done

echo "== 创建/更新代理 tool =="
curl -s -X POST "$API/proxies" -H 'Content-Type: application/json' \
  -d '{"name":"tool","listen":"0.0.0.0:8666","upstream":"tool-service:9000","enabled":true}' | head -c 300
echo
curl -s "$API/proxies/tool" | head -c 300
echo
