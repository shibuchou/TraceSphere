#!/usr/bin/env bash
set -u
UIROOT=/usr/local/zstack/zstack-ui/zstack-ui
F=$(grep -rl "backup-storage/local-backup-storage" "$UIROOT" 2>/dev/null | head -1)
echo "file=$F"
if [ -n "$F" ]; then
  echo "== context around endpoint =="
  grep -o '.\{0,120\}local-backup-storage.\{0,400\}' "$F" | head -3
  echo
  echo "== nearby param names =="
  grep -o '.\{0,400\}local-backup-storage.\{0,400\}' "$F" | grep -o '"[a-zA-Z]\{3,20\}":' | sort -u | head -30
fi
