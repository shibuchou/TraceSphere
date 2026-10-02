#!/usr/bin/env bash
# 修正网络：确认 pg-demo 的 IP 段/DNS
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
PWD_IP="10.0.0.0"
BASE="http://$MN:8080/zstack/v1"
PG="26391fe900e44409b3d2a37721b08f76"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
api() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -m 60 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"; else curl -s -m 30 -H "$AH" "$BASE/$p"; fi }

echo "== all l3 networks (name/uuid/vlan) =="
api GET l3-networks | grep -o '"name":"[^"]*"\|"uuid":"[^"]*"\|"vlanId":[0-9]*\|"ipRanges":\[[^]]*\]' | head -40

echo
echo "== ip-ranges of pg-demo =="
api GET "l3-networks/$PG/ip-ranges" | head -c 400
echo

echo
echo "== add ip range to pg-demo =="
api POST "l3-networks/$PG/ip-ranges" '{"params":{"name":"range-demo","startIp":"10.0.0.10","endIp":"10.0.0.250","netmask":"255.255.255.0","gateway":"10.0.0.1","ipRangeType":"Normal"}}' | head -c 300
echo
echo "== add dns to pg-demo =="
api POST "l3-networks/$PG/dns" '{"params":{"dns":"223.5.5.5"}}' | head -c 300
echo
sleep 6
echo "== verify pg-demo =="
api GET "l3-networks" | grep -o '"name":"pg-demo"[^}]*' | head -c 800
echo
echo "== verify ip-ranges =="
api GET "l3-networks/$PG/ip-ranges" | head -c 500
