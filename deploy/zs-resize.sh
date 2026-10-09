#!/usr/bin/env bash
# 扩盘：ZStack 根卷 resize 到 40GiB + VM 内容器 grow
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
VM=a1b2c3d456784b7d8e9f0a1b2c3d4e5f
VOL=c6114309f9d34fa980a00a4895383654
NEWSIZE=42949672960
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }
state() { curl -s -m 20 -H "$AH" "$BASE/vm-instances/$VM" | grep -o '"state":"[A-Za-z]*"' | head -1; }

echo "== stop VM =="
mnssh "virsh destroy $VM" >/dev/null 2>&1 || true
for i in $(seq 1 20); do sleep 5; S=$(state); echo "[$i] $S"; echo "$S" | grep -q Stopped && break; done

echo "== resizeRootVolume -> 40GiB =="
curl -s -m 90 -X PUT -H "$AH" -H 'Content-Type: application/json' \
  -d "{\"resizeRootVolume\":{\"size\":$NEWSIZE}}" \
  "$BASE/volumes/$VOL/actions" | head -c 300
echo
sleep 10
curl -s -m 30 -H "$AH" "$BASE/volumes/$VOL" | grep -o '"size":[0-9]*\|"status":"[A-Za-z]*"' | head -3

echo "== start VM =="
mnssh "virsh start $VM"
sleep 50

echo "== VM 内扩容 =="
sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 ubuntu@${VM_IP:?} \
  'lsblk /dev/vda; sudo growpart /dev/vda 1 2>&1 | tail -1; sudo resize2fs /dev/vda1 2>&1 | tail -1; df -h / | tail -1'
