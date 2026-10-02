#!/usr/bin/env bash
# ZSvirt 管理节点内部诊断：API 监听端口与 nginx 路由
set -u
echo "== listeners =="
ss -tlnp 2>/dev/null | grep -E ':(443|8080|8443|8009)' || true
echo
echo "== nginx (443) localhost =="
curl -sk -m 8 -o /tmp/d1 -w 'HTTP %{http_code}\n' https://127.0.0.1/zstack/v1/vm-instances
head -c 200 /tmp/d1; echo; echo
echo "== tomcat 8080 localhost =="
curl -s -m 8 -o /tmp/d2 -w 'HTTP %{http_code}\n' http://127.0.0.1:8080/zstack/v1/vm-instances
head -c 200 /tmp/d2; echo; echo
echo "== zstack-ui configs =="
ls /usr/local/zstack/zstack-ui/configs/ 2>/dev/null
echo
echo "== nginx location/proxy =="
grep -n 'location\|proxy_pass' /usr/local/zstack/zstack-ui/configs/extend.server.nginx.conf 2>/dev/null | head -20
echo
echo "== zstack-cli =="
command -v zstack-cli || ls /usr/local/zstack/*/bin/ 2>/dev/null | head
