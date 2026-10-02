#!/usr/bin/env bash
set -u
echo "== find api mapping files =="
grep -rl "backup-storage/image-store" /usr/local/zstack/apache-tomcat-8.5.99/ /usr/local/zstack/apache-tomcat/ 2>/dev/null | head -5
echo
echo "== all backup-storage creational paths in mapping =="
for f in $(grep -rl "backup-storage/image-store" /usr/local/zstack/apache-tomcat-8.5.99/ 2>/dev/null | head -2); do
  echo "--- $f ---"
  grep -o '"[^"]*backup-storage[^"]*"' "$f" 2>/dev/null | sort -u | head -30
done
echo
echo "== GET /backup-storage/types =="
MN=${MN_IP:?}; PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" -H 'Content-Type: application/json' -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
curl -s -m 20 -H "Authorization: OAuth $SESS" "$BASE/backup-storage/types" | head -c 600
echo
