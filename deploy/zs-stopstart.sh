#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
VM=a1b2c3d456784b7d8e9f0a1b2c3d4e5f
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

state() { curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"state":"[A-Za-z]*"' | head -1; }

echo "== stop vm =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' \
  -d '{"stopVmInstance":{"type":"grace"}}' "$BASE/vm-instances/$VM/actions" >/dev/null
for i in $(seq 1 20); do sleep 6; S=$(state); echo "[$i] $S"; echo "$S" | grep -q Stopped && break; done

echo "== start vm =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' \
  -d '{"startVmInstance":{}}' "$BASE/vm-instances/$VM/actions" >/dev/null
for i in $(seq 1 20); do sleep 6; S=$(state); echo "[$i] $S"; echo "$S" | grep -q Running && break; done

echo
echo "== MN dhcp right after start =="
mnssh 'ps aux | grep -i dnsmasq | grep -v grep | head -3; ss -lnup | grep :67 | head -2'
echo
echo "== poll ip (4min) =="
for i in $(seq 1 16); do
  sleep 15
  IP=$(curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"usedIps":\[[^]]*\]' | head -1)
  echo "[$i] $IP"
  echo "$IP" | grep -q '10\.100\.' && { echo "VM GOT IP"; break; }
done
