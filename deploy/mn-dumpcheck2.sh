#!/usr/bin/env bash
D=$(ls -t /var/lib/zstack/mysql-backup/*.gz 2>/dev/null | head -1)
echo "dump=$D"
zcat "$D" > /tmp/zstack-dump.sql 2>/dev/null
ls -la /tmp/zstack-dump.sql
echo
echo "== AccountVO / Account insert statements =="
grep -m2 -o "INSERT INTO [^ ]*[Aa]ccount[^ ]* .*" /tmp/zstack-dump.sql | head -c 2500
echo
echo
echo "== hash comparison =="
printf '${ZS_PW:?export ZS_PW} sha512: '; printf '%s' '${ZS_PW:?export ZS_PW}' | sha512sum | cut -d' ' -f1
printf 'password   sha512: '; printf '%s' 'password' | sha512sum | cut -d' ' -f1
echo
echo "== zstack-zsvirt-ctl help =="
zstack-zsvirt-ctl --help 2>&1 | head -30
