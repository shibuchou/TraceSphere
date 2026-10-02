#!/usr/bin/env bash
# 查询 ZSvirt 平台当前资源状态
set -u
MN="${1:-${MN_IP:?}}"
PW="${2:-${ZS_PW:?export ZS_PW}}"
BASE="http://$MN:8080/zstack/v1"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H "Content-Type: application/json" \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
echo "SESSION=$SESS"
echo
for ep in zones clusters hosts primary-storage backup-storage l2-networks l3-networks images instance-offerings; do
  printf "== %s: " "$ep"
  curl -s -m 10 -H "Authorization: OAuth $SESS" "$BASE/$ep" | head -c 500
  echo
done
