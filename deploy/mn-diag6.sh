#!/usr/bin/env bash
CTL=/var/lib/zstack/virtualenv/zstackctl/lib/python2.7/site-packages/zstackctl/ctl.py
echo "== mysql portal helpers =="
grep -n "mysql_portal\|def get_live\|def get_mysql\|MYSQL_PORTAL" "$CTL" | head -20
echo
echo "== decrypt helpers =="
grep -n "def decrypt\|AESDecrypt\|decrypt_password\|decode_password" "$CTL" | head -20
echo
echo "== context around reset_password def class =="
sed -n '10340,10390p' "$CTL"
