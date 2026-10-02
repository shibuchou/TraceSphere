#!/usr/bin/env bash
# ZSvirt 平台初始化 第1步：数据中心 / 集群 / 主机
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H "Content-Type: application/json" \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
echo "SESSION=$SESS"

api() {
  local m=$1 p=$2 d=${3:-}
  if [ -n "$d" ]; then
    curl -s -m 30 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"
  else
    curl -s -m 30 -H "$AH" "$BASE/$p"
  fi
}

echo
echo "== [1] CreateZone =="
api POST zones '{"params":{"name":"Datacenter-1","description":"TraceSphere demo"}}' | head -c 500
echo
ZONE=$(api GET zones | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
echo "ZONE=$ZONE"

echo
echo "== [2] CreateCluster =="
api POST clusters "{\"params\":{\"name\":\"Cluster-1\",\"zoneUuid\":\"$ZONE\",\"hypervisorType\":\"KVM\"}}" | head -c 500
echo
CLU=$(api GET clusters | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
echo "CLUSTER=$CLU"

echo
echo "== [3] AddKVMHost (host = 管理节点自身) =="
api POST hosts "{\"params\":{\"name\":\"host-1\",\"clusterUuid\":\"$CLU\",\"managementIp\":\"$MN\",\"username\":\"root\",\"password\":\"$PW\"}}" | head -c 600
echo
sleep 5
echo "== hosts state =="
api GET hosts | head -c 800
echo
