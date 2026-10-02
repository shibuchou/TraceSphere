#!/usr/bin/env bash
mkdir -p /root/dumps
cd /root/dumps
echo "== dump_mysql =="
zstack-ctl dump_mysql 2>&1 | tail -5
echo
D=$(ls -t /root/dumps/*.sql 2>/dev/null | head -1)
echo "dump_file=$D"
if [ -n "$D" ]; then
  echo "== AccountVO insert (first 1800 chars) =="
  grep -m1 -o "INSERT INTO \`AccountVO\`.*" "$D" | head -c 1800
  echo
  echo
  echo "== rows containing admin =="
  grep -o "(\([^()]*admin[^()]*\))" "$D" | head -5
fi
echo
echo "== full sha512 of ${ZS_PW:?export ZS_PW} =="
printf '%s' '${ZS_PW:?export ZS_PW}' | sha512sum
