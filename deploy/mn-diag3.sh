#!/usr/bin/env bash
# 查找 reset_password 实现与 MySQL 凭据
set -u
echo "== /root/.my.cnf =="
cat /root/.my.cnf 2>/dev/null || echo none
echo
echo "== zstackctl site-packages =="
ls -d /var/lib/zstack/virtualenv/zstackctl/lib/python*/site-packages/ 2>/dev/null
ls /var/lib/zstack/virtualenv/zstackctl/lib/python*/site-packages/ 2>/dev/null | head -40
echo
echo "== grep reset_password =="
grep -rln reset_password /var/lib/zstack/virtualenv/zstackctl/ 2>/dev/null | head
echo
echo "== grep DB.password handling =="
grep -rln 'DB.password\|decrypt' /var/lib/zstack/virtualenv/zstackctl/lib/python*/site-packages/ 2>/dev/null | head
echo
echo "== zstack management venv =="
ls -d /var/lib/zstack/virtualenv/*/ 2>/dev/null
