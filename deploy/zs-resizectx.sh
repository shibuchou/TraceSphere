#!/usr/bin/env bash
set -u
UI=/usr/local/zstack/zstack-ui/zstack-ui
FILES=$(grep -rl "resizeRootVolume" "$UI" 2>/dev/null | head -3)
echo "files:"; echo "$FILES"
for f in $FILES; do
  echo
  echo "== $f =="
  grep -o '.\{0,250\}resizeRootVolume.\{0,250\}' "$f" | head -3
done
