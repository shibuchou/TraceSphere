#!/usr/bin/env bash
set -u
UIROOT=/usr/local/zstack/zstack-ui
FILES=$(grep -rl "backup-storage/local-backup-storage" "$UIROOT" 2>/dev/null | head -3)
echo "files:"; echo "$FILES"
for f in $FILES; do
  echo
  echo "== $f =="
  grep -o '.\{0,150\}local-backup-storage.\{0,600\}' "$f" | head -2
done
