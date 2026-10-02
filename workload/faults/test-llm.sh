#!/usr/bin/env bash
set -u
URL=http://127.0.0.1:8081/v1/chat/completions

echo "== A: 默认（可能触发思考模式）=="
curl -s --max-time 120 "$URL" -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"你好，用一句话介绍你自己"}],"max_tokens":128}' | head -c 600
echo
echo
echo "== B: 关闭思考（enable_thinking=false）=="
curl -s --max-time 120 "$URL" -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"你好，用一句话介绍你自己"}],"max_tokens":128,"chat_template_kwargs":{"enable_thinking":false}}' | head -c 600
echo
