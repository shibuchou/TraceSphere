#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PG=26391fe900e44409b3d2a37721b08f76
VM=a1b2c3d456784b7d8e9f0a1b2c3d4e5f
FLAT=a64965c0f7d54653a1fa7f7ae5d927b7
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

echo "== POST attach DHCP+Userdata (Flat) =="
curl -s -m 60 -X POST -H "$AH" -H 'Content-Type: application/json' \
  -d "{\"params\":{\"networkServices\":{\"$FLAT\":[\"DHCP\",\"Userdata\"]}}}" \
  "$BASE/l3-networks/$PG/network-services" | head -c 400
echo
sleep 12
echo "== pg-demo networkServices =="
curl -s -m 30 -H "$AH" "$BASE/l3-networks" | grep -o '"name":"pg-demo".*' | grep -o 'networkServices":\[[^]]*\]' | head -1
echo
echo "== MN listen/iface =="
mnssh 'ss -lnup | grep :67 | head -2; ps aux | grep -i dnsmasq | grep -v grep | head -2; ip -4 addr | grep 10.100 | head -3'
echo
echo "== reboot VM =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' -d '{"rebootVmInstance":{}}' \
  "$BASE/vm-instances/$VM/actions" >/dev/null
echo "== poll VM ip (6min) =="
for i in $(seq 1 24); do
  sleep 15
  IP=$(curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"usedIps":\[[^]]*\]' | head -1)
  echo "[$i] $IP"
  if echo "$IP" | grep -q '10\.100\.'; then
    echo "VM GOT IP"
    break
  fi
done
echo
echo "== MN arp/neigh =="
mnssh 'ip neigh | grep 10.100 | head -5'
