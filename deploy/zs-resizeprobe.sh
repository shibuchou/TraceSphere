#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
VOL=c6114309f9d34fa980a00a4895383654
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"

echo "== probe POST =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' \
  -d '{"resizeRootVolume":{"size":42949672960}}' \
  "$BASE/volumes/$VOL/actions" | head -c 300
echo
echo "== probe POST params 包装 =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' \
  -d '{"params":{"size":42949672960}}' \
  "$BASE/volumes/$VOL/actions" | head -c 300
