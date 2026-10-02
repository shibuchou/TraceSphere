#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"

echo "== network service types =="
curl -s -m 30 -H "$AH" "$BASE/network-service-types" | head -c 600
echo
echo "== network service providers =="
curl -s -m 30 -H "$AH" "$BASE/network-service-providers" | head -c 900
echo
echo "== pg-demo networkServices =="
curl -s -m 30 -H "$AH" "$BASE/l3-networks" | grep -o '"name":"pg-demo"[^]]*networkServices":\[[^]]*\]' | head -c 700
echo
