#!/usr/bin/env bash
set -u
echo "== /usr/bin/zstack-ctl (tail) =="
tail -40 /usr/bin/zstack-ctl
echo
echo "== find zstackctl impl =="
ls /usr/local/zstack/ 2>/dev/null
find / -maxdepth 4 -name '*.py' -path '*zstackctl*' 2>/dev/null | head -10
find / -maxdepth 4 -type d -name 'zstackctl' 2>/dev/null | head
echo
echo "== grep reset_password in likely dirs =="
grep -rln reset_password /usr/local/zstack /opt/zstack /var/lib/zstack/zstackctl 2>/dev/null | grep -v ansible | head -10
