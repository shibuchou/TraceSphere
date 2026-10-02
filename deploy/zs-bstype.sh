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

echo "== backup storage types =="
curl -s -m 30 -H "$AH" "$BASE/backup-storage-types" | head -c 1000
echo
echo "== current backup storage =="
curl -s -m 30 -H "$AH" "$BASE/backup-storage" | head -c 600
echo
echo "== try candidate add endpoints probe =="
for ep in backup-storage/local backup-storage/local-storage backup-storage/local-directory; do
  echo "--- $ep ---"
  curl -s -m 20 -o /dev/null -w "HTTP %{http_code}\n" -X POST -H "$AH" -H 'Content-Type: application/json' -d '{"params":{}}' "$BASE/$ep"
done
