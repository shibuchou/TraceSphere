#!/usr/bin/env bash
# vm-agent 卸载脚本
# 用法: sudo bash uninstall.sh [--purge]
#   --purge  同时删除证据/日志目录（/opt/tracesphere/evidence）
set -euo pipefail

systemctl disable --now tracesphere-vm-agent 2>/dev/null || true
rm -f /etc/systemd/system/tracesphere-vm-agent.service
rm -f /opt/tracesphere/bin/vm-agent
systemctl daemon-reload
systemctl reset-failed tracesphere-vm-agent 2>/dev/null || true

echo "vm-agent 已卸载（服务、单元文件、二进制）。"
if [ "${1:-}" = "--purge" ]; then
  rm -rf /opt/tracesphere/evidence
  echo "证据/日志目录已清理（--purge）。"
else
  echo "证据与日志保留在 /opt/tracesphere/evidence；如需清理: sudo bash $0 --purge"
fi
