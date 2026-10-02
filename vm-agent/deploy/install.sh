#!/usr/bin/env bash
# vm-agent 安装脚本：安装二进制 + systemd 服务
# 用法: sudo bash install.sh [vm-agent 二进制路径]
set -euo pipefail

SRC=${1:-}
if [ -z "$SRC" ]; then
  for c in ./vm-agent /tmp/vm-agent /tmp/vm-agent-psi; do
    [ -f "$c" ] && SRC="$c" && break
  done
fi
[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "找不到 vm-agent 二进制，请传入路径"; exit 1; }

PREFIX=/opt/tracesphere
DIR=$(cd "$(dirname "$0")" && pwd)

echo "== 安装二进制 =="
install -d "$PREFIX/bin" "$PREFIX/evidence" "$PREFIX/deploy"
install -m 0755 "$SRC" "$PREFIX/bin/vm-agent"

echo "== 运行时环境（缺失则生成模板，实际值由部署方填写）=="
install -d /etc/tracesphere
if [ ! -f /etc/tracesphere/agent.env ]; then
  cat > /etc/tracesphere/agent.env <<'ENVEOF'
# vm-agent 运行时环境（本地部署信息，勿提交仓库）
# VMAGENT_PLATFORM_URL=http://<platform-host>:8000   # 为空则关闭直报，仅本地日志
# VMAGENT_VM_UUID=<ZSvirt VM uuid>                   # VM 级证据挂到资源图
# VMAGENT_TOKEN=
# VMAGENT_REPORT_PROCESS=0
ENVEOF
  echo "已生成 /etc/tracesphere/agent.env 模板（请按环境填写）"
else
  echo "/etc/tracesphere/agent.env 已存在，保留"
fi

echo "== 固化部署文件 =="
for f in install.sh uninstall.sh measure-overhead.sh tracesphere-vm-agent.service; do
  src="$DIR/$f"; dst="$PREFIX/deploy/$f"
  if [ -e "$dst" ] && [ "$(readlink -f "$src")" = "$(readlink -f "$dst")" ]; then
    continue
  fi
  install -m 0644 "$src" "$dst"
done
chmod 0755 "$PREFIX/deploy/"*.sh

echo "== 安装 systemd 服务 =="
install -m 0644 "$DIR/tracesphere-vm-agent.service" /etc/systemd/system/tracesphere-vm-agent.service
systemctl daemon-reload
systemctl enable tracesphere-vm-agent
systemctl restart tracesphere-vm-agent

sleep 2
echo
systemctl --no-pager -l status tracesphere-vm-agent | head -12 || true
echo
echo "安装完成。"
echo "  日志/事件: $PREFIX/evidence/vm-agent.log"
echo "  卸载:      sudo bash $DIR/uninstall.sh"
