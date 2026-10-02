#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PG=26391fe900e44409b3d2a37721b08f76
VM=63bbb4613a524e4e97090600af03da93
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

echo "== current dhcp-ip =="
curl -s -m 20 -H "$AH" "$BASE/l3-networks/$PG/dhcp-ip" | head -c 300
echo
echo "== change dhcp-ip -> 10.0.0.2 =="
curl -s -m 30 -X PUT -H "$AH" -H 'Content-Type: application/json' \
  -d '{"changeL3NetworkDhcpIpAddress":{"dhcpServerIp":"10.0.0.2"}}' \
  "$BASE/l3-networks/$PG/dhcp-ip" | head -c 300
echo
sleep 8
echo "== verify =="
curl -s -m 20 -H "$AH" "$BASE/l3-networks/$PG/dhcp-ip" | head -c 300
echo
echo "== MN dhcp service / 10.100 iface =="
mnssh 'ss -lnup | grep :67 | head -3; ip -4 addr | grep 10.100; ps aux | grep -iE "dnsmasq|dhcp" | grep -v grep | head -5'
echo
echo "== VM ip =="
curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"usedIps":\[[^]]*\]\|"ip":"[^"]*"' | head -5
