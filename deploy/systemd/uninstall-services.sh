#!/usr/bin/env bash
# TraceSphere 服务化卸载（保留代码与数据）
# 用法: sudo bash uninstall-services.sh
set -euo pipefail
systemctl disable --now tracesphere-rca tracesphere-platform 2>/dev/null || true
rm -f /etc/systemd/system/tracesphere-platform.service /etc/systemd/system/tracesphere-rca.service
systemctl daemon-reload
systemctl reset-failed tracesphere-platform tracesphere-rca 2>/dev/null || true
echo "已卸载 platform / rca 服务（代码与数据保留）。"
