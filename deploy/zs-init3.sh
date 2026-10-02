#!/usr/bin/env bash
# ZSvirt 平台初始化 第3步：数据存储（本地）+ 镜像存储
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
ZONE=26fd04cdf31047e4a96aff5e41225420
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
api() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -m 60 -X "$m" -H "$AH" -H 'Content-Type: application/json' -d "$d" "$BASE/$p"; else curl -s -m 30 -H "$AH" "$BASE/$p"; fi }

echo "== [1] AddLocalPrimaryStorage =="
api POST primary-storage/local-storage "{\"params\":{\"url\":\"/var/lib/zstack/ps-local\",\"name\":\"ps-local\",\"zoneUuid\":\"$ZONE\"}}" | head -c 700
echo
for i in $(seq 1 18); do
  sleep 5
  R=$(api GET primary-storage)
  echo "[$i] $(echo "$R" | head -c 260)"
  if echo "$R" | grep -q Connected; then echo "PRIMARY STORAGE CONNECTED"; break; fi
done

echo
echo "== [2] AddImageStoreBackupStorage =="
api POST backup-storage/image-store "{\"params\":{\"hostname\":\"$MN\",\"username\":\"root\",\"password\":\"$PW\",\"sshPort\":22,\"url\":\"/var/lib/zstack/imagestore-bs\",\"name\":\"bs-local\",\"importImages\":false}}" | head -c 500
echo
for i in $(seq 1 24); do
  sleep 10
  R=$(api GET backup-storage)
  echo "[$i] $(echo "$R" | head -c 320)"
  if echo "$R" | grep -q Connected; then echo "BACKUP STORAGE CONNECTED"; break; fi
done
