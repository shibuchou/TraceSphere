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
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

echo "== api job =="
curl -s -m 30 -H "$AH" "$BASE/api-jobs/c08d760ee1a142bcb4bfaa3b4772ae83" | head -c 800
echo
echo "== recent errors in MN log =="
mnssh 'grep -a -iE "ERROR|workload-vm|CreateVmInstance" /usr/local/zstack/apache-tomcat/logs/management-server.log | tail -25'
