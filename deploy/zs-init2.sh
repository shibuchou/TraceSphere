#!/usr/bin/env bash
# ZSvirt 平台初始化 第2步：添加 KVM 主机（管理节点自身）
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
api() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -m 30 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"; else curl -s -m 30 -H "$AH" "$BASE/$p"; fi }

echo "== AddKVMHost (POST /hosts/kvm) =="
api POST hosts/kvm '{"params":{"name":"host-1","clusterUuid":"a29a9e1c13ac4017a187e30fca573625","managementIp":"${MN_IP:?}","username":"root","password":"${ZS_PW:?export ZS_PW}","sshPort":"22"}}' | head -c 700
echo
echo "== polling host state =="
for i in $(seq 1 30); do
  sleep 10
  H=$(api GET hosts)
  echo "[$i] $(echo "$H" | head -c 400)"
  if echo "$H" | grep -q Connected; then echo "HOST CONNECTED"; break; fi
done
