#!/usr/bin/env bash
# ZSvirt 平台初始化 第4步：网络（分布式交换机 + 端口组 + IP段 + DNS）
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
ZONE=26fd04cdf31047e4a96aff5e41225420
BS=2fa50ded127743859cf2bb80e9d3a25a
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
api() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -m 60 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"; else curl -s -m 30 -H "$AH" "$BASE/$p"; fi }

echo "== [1] AttachBackupStorageToZone =="
api POST "zones/$ZONE/backup-storage/$BS" '{"params":{}}' | head -c 400
echo

echo "== [2] CreateL2VirtualSwitch (ens2, LinuxBridge) =="
api POST l2-networks/virtual-switch "{\"params\":{\"isDistributed\":true,\"name\":\"dvs-ens2\",\"description\":\"TraceSphere nested switch\",\"zoneUuid\":\"$ZONE\",\"physicalInterface\":\"ens2\",\"vSwitchType\":\"LinuxBridge\"}}" | head -c 500
echo
sleep 8
VS=$(api GET l2-networks | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
echo "VSWITCH=$VS"

echo
echo "== [3] CreatePortGroup (vlan 2344, IPAM on) =="
api POST l3-networks/port-group "{\"params\":{\"vSwitchUuid\":\"$VS\",\"vlanMode\":\"ACCESS\",\"vlan\":2344,\"name\":\"pg-demo\",\"description\":\"TraceSphere workload network\",\"type\":\"L3BasicNetwork\",\"category\":\"Private\",\"ipVersion\":4,\"system\":false,\"enableIPAM\":true}}" | head -c 500
echo
sleep 8
PG=$(api GET l3-networks | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
echo "PORTGROUP=$PG"

echo
echo "== [4] AddIpRange =="
api POST "l3-networks/$PG/ip-ranges" '{"params":{"name":"range-1","startIp":"10.0.0.10","endIp":"10.0.0.250","netmask":"255.255.255.0","gateway":"10.0.0.1","ipRangeType":"Normal"}}' | head -c 400
echo

echo "== [5] AddDnsToL3Network =="
api POST "l3-networks/$PG/dns" '{"params":{"dns":"223.5.5.5"}}' | head -c 300
echo

echo
echo "== [6] state check =="
echo "-- l2 --"; api GET l2-networks | head -c 400; echo
echo "-- l3 --"; api GET l3-networks | head -c 700; echo
