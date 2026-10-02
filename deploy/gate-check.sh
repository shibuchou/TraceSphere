#!/usr/bin/env bash
# TraceSphere Environment Gate - ZSvirt REST API 验证（在能访问管理节点的机器上运行）
# 注意: 本镜像中管理 API 直接监听 8080（443 为 UI 的 nginx，仅代理 /download-helper）
# 用法: bash gate-check.sh [管理节点IP]
set -u
MN="${1:-${MN_IP:?}}"
PW="${2:-${ZS_PW:?export ZS_PW}}"
BASE="http://$MN:8080/zstack/v1"

echo "== [1] 未认证请求 GET /vm-instances =="
curl -s -m 10 -o /tmp/gate1.json -w "HTTP %{http_code}\n" "$BASE/vm-instances"
head -c 300 /tmp/gate1.json; echo; echo

echo "== [2] 登录 PUT /accounts/login (admin) =="
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H "Content-Type: application/json" \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  -o /tmp/gate2.json -w "HTTP %{http_code}\n"
head -c 800 /tmp/gate2.json; echo; echo

SESSION=$(sed -n 's/.*"uuid"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' /tmp/gate2.json | head -1)
echo "SESSION=$SESSION"

if [ -n "$SESSION" ]; then
  echo "== [3] 带会话查询 GET /vm-instances =="
  curl -s -m 10 -o /tmp/gate3.json -w "HTTP %{http_code}\n" \
    -H "Authorization: OAuth $SESSION" "$BASE/vm-instances"
  head -c 800 /tmp/gate3.json; echo
fi
