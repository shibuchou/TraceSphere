#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PG=26391fe900e44409b3d2a37721b08f76
VM=a1b2c3d456784b7d8e9f0a1b2c3d4e5f
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

echo "== PUT change dhcp-ip =="
curl -s -m 30 -X PUT -H "$AH" -H 'Content-Type: application/json' \
  -d '{"changeL3NetworkDhcpIpAddress":{"dhcpServerIp":"10.0.0.2"}}' \
  "$BASE/l3-networks/$PG/dhcp-ip" | head -c 300
echo
sleep 10
echo "== GET dhcp-ip =="
curl -s -m 20 -H "$AH" "$BASE/l3-networks/$PG/dhcp-ip" | head -c 200
echo
echo "== MN dhcp processes =="
mnssh 'ps aux | grep -i dnsmasq | grep -v grep | head -3; ss -lnup | grep :67 | head -2; ip netns list 2>/dev/null | head -5; ip -4 addr | grep 10.100 | head -3'
echo
echo "== reboot VM & poll ip =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' -d '{"rebootVmInstance":{}}' \
  "$BASE/vm-instances/$VM/actions" >/dev/null
for i in $(seq 1 16); do
  sleep 15
  IP=$(curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"usedIps":\[[^]]*\]' | head -1)
  echo "[$i] $IP"
  echo "$IP" | grep -q '10\.100\.' && { echo "VM GOT IP"; break; }
done
