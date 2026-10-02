#!/usr/bin/env bash
set -u
UI=/usr/local/zstack/zstack-ui/zstack-ui
echo "== resize 相关 API 名字 =="
grep -rhoE "resizeRootVolume|resizeDataVolume|resizeVolume|changeVolumeSize" "$UI" 2>/dev/null | sort -u | head -12
echo
echo "== volume action URL =="
grep -rhoE "volumes/[^\"' ]{0,60}/actions[^\"' ]{0,30}" "$UI" 2>/dev/null | sort -u | head -12
echo
echo "== 管理端支持的 API 列表（从日志历史请求里找）=="
grep -aoE "/zstack/v1/volumes/[0-9a-f]+/actions" /usr/local/zstack/apache-tomcat-8.5.99/logs/management-server.log 2>/dev/null | sort -u | head -5
