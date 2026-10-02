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

echo "== VM info (ip/state/mac) =="
curl -s -m 30 -H "$AH" "$BASE/vm-instances" | grep -o '"name":"workload-vm"[^}]*\|"ip":"[^"]*"\|"mac":"[^"]*"\|"state":"[A-Za-z]*"' | head -10
echo
echo "== MN 上的 10.100 网段与租约 =="
mnssh 'ip -4 addr | grep 10.100; echo ---; ip neigh | grep 10.100; echo ---; ps aux | grep -i dnsmasq | grep -v grep | head -3; echo ---; ss -lnup | grep :67 | head -3'
