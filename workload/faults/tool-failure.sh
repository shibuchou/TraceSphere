#!/usr/bin/env bash
# Case 3: 工具调用故障注入（Toxiproxy API）
# 用法: tool-failure.sh latency|timeout|down|reset|clear
set -u
API=http://127.0.0.1:8474
MODE=${1:-latency}

case "$MODE" in
  latency)
    LATENCY_MS=${2:-3000}
    curl -s -X POST "$API/proxies/tool/toxics" -H 'Content-Type: application/json' \
      -d "{\"name\":\"latency_down\",\"type\":\"latency\",\"attributes\":{\"latency\":${LATENCY_MS}}}" >/dev/null
    echo "injected: latency ${LATENCY_MS}ms" ;;
  timeout)
    curl -s -X POST "$API/proxies/tool/toxics" -H 'Content-Type: application/json' \
      -d '{"name":"timeout_down","type":"timeout","attributes":{"timeout":5000}}' >/dev/null
    echo "injected: timeout 5000ms" ;;
  down)
    curl -s -X POST "$API/proxies/tool" -H 'Content-Type: application/json' \
      -d '{"enabled":false}' >/dev/null
    echo "injected: proxy disabled (service down)" ;;
  reset)
    curl -s -X POST "$API/proxies/tool/toxics" -H 'Content-Type: application/json' \
      -d '{"name":"reset_down","type":"reset_peer","attributes":{"timeout":0}}' >/dev/null
    echo "injected: reset_peer" ;;
  clear)
    for t in $(curl -s "$API/proxies/tool/toxics" | grep -o '"name":"[^"]*"' | cut -d'"' -f4); do
      curl -s -X DELETE "$API/proxies/tool/toxics/$t" >/dev/null
    done
    curl -s -X POST "$API/proxies/tool" -H 'Content-Type: application/json' \
      -d '{"enabled":true}' >/dev/null
    echo "cleared all toxics and re-enabled proxy" ;;
  *)
    echo "usage: $0 latency|timeout|down|reset|clear"; exit 1 ;;
esac
