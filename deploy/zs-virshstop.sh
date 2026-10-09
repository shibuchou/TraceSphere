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

echo "== stop job error? =="
curl -s -m 20 -H "$AH" "$BASE/api-jobs/20aa9ef166974618aff2feb6935d5130" | head -c 300
echo
echo "== virsh destroy on MN =="
mnssh "virsh destroy $VM; sleep 2; virsh list --all | head -5"
echo
echo "== wait ZStack sees Stopped =="
for i in $(seq 1 20); do sleep 5; S=$(state); echo "[$i] $S"; echo "$S" | grep -q Stopped && break; done

echo "== start via API =="
curl -s -m 30 -X POST -H "$AH" -H 'Content-Type: application/json' \
  -d '{"startVmInstance":{}}' "$BASE/vm-instances/$VM/actions" | head -c 200
echo
for i in $(seq 1 20); do sleep 5; S=$(state); echo "[$i] $S"; echo "$S" | grep -q Running && break; done

echo
echo "== MN dhcp after start =="
mnssh 'ps aux | grep -i dnsmasq | grep -v grep | head -3; ss -lnup | grep :67 | head -2; ip netns list | head -8'
echo
echo "== poll ip =="
for i in $(seq 1 12); do
  sleep 15
  IP=$(curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"usedIps":\[[^]]*\]' | head -1)
  echo "[$i] $IP"
  echo "$IP" | grep -q '10\.100\.' && { echo "VM GOT IP"; break; }
done
