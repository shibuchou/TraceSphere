#!/usr/bin/env bash
set -u
WARROOT=/usr/local/zstack/apache-tomcat-8.5.99/webapps/zstack/WEB-INF
echo "== find jars containing the message =="
grep -ral "need to attach backup storage" "$WARROOT/lib" "$WARROOT/classes" 2>/dev/null | head -5
echo
J=$(grep -ral "need to attach backup storage" "$WARROOT/lib" 2>/dev/null | head -1)
echo "jar=$J"
if [ -n "$J" ]; then
  cd /tmp && rm -rf jx && mkdir jx && cd jx
  unzip -o -q "$J" 2>/dev/null
  F=$(grep -ral "need to attach backup storage" . 2>/dev/null | head -1)
  echo "class=$F"
  if [ -n "$F" ]; then
    strings "$F" | grep -i -B2 -A2 "attach backup storage" | head -20
    echo "--- nearby filter strings ---"
    strings "$F" | grep -iE "BackupStorageFilter|ImageCache|image.*filter|filter" | head -20
  fi
fi
