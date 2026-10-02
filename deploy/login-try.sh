#!/usr/bin/env bash
# 尝试常见初始密码，定位 ZSvirt 初始 admin 口令
set -u
BASE=http://${MN_IP:?}:8080/zstack/v1
for pw in password admin zsvirt ${ZS_PW:?export ZS_PW} ZStack zstack ZStack123 123456 password123 Admin123 admin123 zstack123 ZStack@123; do
  code=$(curl -s -m 10 -o /tmp/lt.json -w '%{http_code}' -X PUT "$BASE/accounts/login" \
    -H 'Content-Type: application/json' \
    -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$pw\"}}")
  desc=$(sed -n 's/.*"description":"\([^"]*\)".*/\1/p' /tmp/lt.json | head -1)
  uuid=$(sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' /tmp/lt.json | head -1)
  echo "pw=$pw code=$code desc=$desc uuid=$uuid"
done
