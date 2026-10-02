#!/usr/bin/env bash
# ZSvirt 平台初始化 第5步：等待镜像下载 → AddImage → 实例规格
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BS=2fa50ded127743859cf2bb80e9d3a25a
BASE="http://$MN:8080/zstack/v1"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
api() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -m 60 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"; else curl -s -m 30 -H "$AH" "$BASE/$p"; fi }
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

echo "== wait for image download =="
for i in $(seq 1 48); do
  SZ=$(mnssh 'stat -c %s /var/lib/zstack/imagestore-bs/ubuntu-24.04.img 2>/dev/null || echo 0')
  RUN=$(mnssh 'pgrep -x curl >/dev/null && echo 1 || echo 0')
  echo "[$i] size=$SZ curl=$RUN"
  if [ "$RUN" = "0" ] && [ "$SZ" -gt 500000000 ]; then echo "DOWNLOAD DONE size=$SZ"; break; fi
  sleep 10
done

echo
echo "== AddImage =="
api POST images "{\"params\":{\"name\":\"ubuntu-24.04-cloudimg\",\"url\":\"/var/lib/zstack/imagestore-bs/ubuntu-24.04.img\",\"mediaType\":\"RootVolumeTemplate\",\"architecture\":\"x86_64\",\"system\":false,\"format\":\"qcow2\",\"platform\":\"Linux\",\"backupStorageUuids\":[\"$BS\"],\"virtio\":true}}" | head -c 500
echo
for i in $(seq 1 30); do
  sleep 10
  R=$(api GET images)
  echo "[$i] $(echo "$R" | head -c 340)"
  if echo "$R" | grep -q '"status":"Ready"'; then echo "IMAGE READY"; break; fi
done

echo
echo "== create instance offering =="
api POST instance-offerings '{"params":{"name":"off-small","cpuNum":4,"memorySize":4294967296,"description":"4 vCPU / 4 GiB for workload VM"}}' | head -c 400
echo
sleep 5
api GET instance-offerings | head -c 600
echo
