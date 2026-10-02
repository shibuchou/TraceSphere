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

echo "== providers (uuid/name/type) =="
curl -s -m 20 -H "$AH" "$BASE/network-services/providers" | grep -o '"uuid":"[0-9a-f]*"\|"name":"[^"]*"\|"type":"[^"]*"' | paste - - - 2>/dev/null || curl -s -m 20 -H "$AH" "$BASE/network-services/providers"
echo
echo "== service types full =="
curl -s -m 20 -H "$AH" "$BASE/network-services/types"
echo
