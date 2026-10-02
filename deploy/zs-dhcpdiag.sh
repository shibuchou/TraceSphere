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

echo "== dhcp-ip change job =="
curl -s -m 20 -H "$AH" "$BASE/api-jobs/22c35bbe54d648bd89b4ed411c0104a6" | head -c 500
echo
echo "== pg-demo full inventory =="
curl -s -m 30 -H "$AH" "$BASE/l3-networks" | python2 -c "
import sys, json
d = json.load(sys.stdin)
for inv in d.get('inventories', []):
    if inv.get('name') == 'pg-demo':
        print(json.dumps(inv, indent=1)[:2500])
" 2>/dev/null || curl -s -m 30 -H "$AH" "$BASE/l3-networks" | grep -o '"name":"pg-demo".*' | head -c 1500
echo
echo "== MN log around dhcp =="
mnssh 'grep -a -i "dhcp" /usr/local/zstack/apache-tomcat-8.5.99/logs/management-server.log | tail -12'
