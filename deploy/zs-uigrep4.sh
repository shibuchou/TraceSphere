#!/usr/bin/env bash
set -u
D=/usr/local/zstack/zstack-ui/zstack-ui-server/zsphere-data-protection/local-backup-storage
echo "== dir =="; ls -la "$D"; ls -la "$D/query" 2>/dev/null
echo
echo "== module.js (head) =="; head -c 1500 "$D/local-backup-storage.module.js" 2>/dev/null
echo
echo "== query.js (head) =="; head -c 2000 "$D/query/local-backup-storage-query.js" 2>/dev/null
echo
echo "== grep api path in dir =="
grep -rho "backup-storage/[a-zA-Z0-9/_-]*\|/zstack/v1[a-zA-Z0-9/_-]*" "$D" 2>/dev/null | sort -u | head -20
