#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
HOST=cbb61d8a22cc4fd1b3702af673cbf405
VM=a1b2c3d456784b7d8e9f0a1b2c3d4e5f
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

echo "== reconnect host (PUT) =="
curl -s -m 30 -X PUT -H "$AH" -H 'Content-Type: application/json' -d '{"reconnectHost":{}}' \
  "$BASE/hosts/$HOST/actions" | head -c 200
echo
for i in $(seq 1 12); do
  sleep 10
  ST=$(curl -s -m 20 -H "$AH" "$BASE/hosts/$HOST" | grep -o '"status":"[a-zA-Z]*"' | head -1)
  echo "[$i] $ST"
  echo "$ST" | grep -q Connected && break
done
echo
echo "== MN dhcp/iface after reconnect =="
mnssh 'ss -lnup | grep :67 | head -2; ps aux | grep -i dnsmasq | grep -v grep | head -3; ip -4 addr | grep 10.100 | head -3; ip link | grep -iE "dvs|2344" | head -6'
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
