#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
VOL=c6114309f9d34fa980a00a4895383654
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"

echo "== A: resizeRootVolume with uuid in body =="
curl -s -m 30 -X PUT -H "$AH" -H 'Content-Type: application/json' \
  -d "{\"resizeRootVolume\":{\"uuid\":\"$VOL\",\"size\":42949672960}}" \
  "$BASE/volumes/$VOL/actions" | head -c 250
echo
echo "== B: params wrapper =="
curl -s -m 30 -X PUT -H "$AH" -H 'Content-Type: application/json' \
  -d "{\"params\":{\"uuid\":\"$VOL\",\"size\":42949672960}}" \
  "$BASE/volumes/$VOL/actions" | head -c 250
echo
echo "== C: mysql root 默认密码探测 =="
mysql -uroot -pzstack.mysql.password -e 'select 1;' 2>&1 | head -2
