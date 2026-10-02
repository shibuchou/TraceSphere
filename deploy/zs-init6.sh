#!/usr/bin/env bash
# ZSvirt 平台初始化 第6步：创建业务 VM（Ubuntu cloud image + cloud-init）
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
IMG=f39ba0991de143e6b76b0887e19edb0a
OFF=21830e28a8f74391ba2a5fe46aca85af
PG=26391fe900e44409b3d2a37721b08f76
CLU=a29a9e1c13ac4017a187e30fca573625
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
api() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -m 90 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"; else curl -s -m 30 -H "$AH" "$BASE/$p"; fi }

USERDATA='#cloud-config
ssh_pwauth: true
disable_root: false
chpasswd:
  list: |
    ubuntu:${ZS_PW:?export ZS_PW}
    root:${ZS_PW:?export ZS_PW}
  expire: false
'
B64=$(printf '%s' "$USERDATA" | base64 -w0)

echo "== CreateVmInstance =="
api POST vm-instances "{\"params\":{\"name\":\"workload-vm\",\"instanceOfferingUuid\":\"$OFF\",\"imageUuid\":\"$IMG\",\"l3NetworkUuids\":[\"$PG\"],\"defaultL3NetworkUuid\":\"$PG\",\"clusterUuid\":\"$CLU\",\"strategy\":\"InstantStart\"},\"systemTags\":[\"userdata::$B64\"]}" | head -c 500
echo
echo "== polling VM state =="
for i in $(seq 1 40); do
  sleep 15
  R=$(api GET vm-instances)
  echo "[$i] $(echo "$R" | head -c 500)"
  if echo "$R" | grep -q '"state":"Running"'; then echo "VM RUNNING"; break; fi
done
