#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PS=4a0ecf3f472c4042aa4f9f9d36494b11
CLU=a29a9e1c13ac4017a187e30fca573625
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"

echo "== primary storage full =="
curl -s -m 30 -H "$AH" "$BASE/primary-storage" | head -c 900
echo
echo
echo "== attach to cluster =="
curl -s -m 60 -X POST -H "$AH" -H 'Content-Type: application/json' -d '{"params":{}}' \
  "$BASE/primary-storage/$PS/clusters/$CLU" | head -c 400
echo
sleep 8
echo "== verify =="
curl -s -m 30 -H "$AH" "$BASE/primary-storage" | head -c 900
echo
