#!/usr/bin/env bash
echo "== AccountVO INSERT =="
grep -o "INSERT INTO \`AccountVO\` VALUES [^;]*" /tmp/zstack-dump.sql | head -c 3000
echo
echo
echo "== Account INSERT (if any) =="
grep -o "INSERT INTO \`Account\` VALUES [^;]*" /tmp/zstack-dump.sql | head -c 3000
echo
echo
echo "== grep admin context in AccountVO =="
grep -o "INSERT INTO \`AccountVO\` VALUES .*" /tmp/zstack-dump.sql | grep -o "([^)]*admin[^)]*)" | head -3
