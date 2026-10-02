#!/usr/bin/env bash
# TraceSphere 服务化安装（platform + rca）：systemd 常驻 + 开机自启
# 用法: sudo bash install-services.sh
set -euo pipefail

DIR=$(cd "$(dirname "$0")" && pwd)
TS_ROOT="$(cd "$DIR/../.." && pwd)"
TS_USER="${SUDO_USER:-$(id -un)}"

echo "== 停止 nohup 版进程（如存在）=="
pkill -f "run.py --provider rest" 2>/dev/null || true
pkill -f "bin/tracesphere serve" 2>/dev/null || true
sleep 2

echo "== 安装单元文件（用户=$TS_USER，仓库=$TS_ROOT）=="
sed -e "s|__TS_USER__|$TS_USER|g" -e "s|__TS_ROOT__|$TS_ROOT|g" \
  "$DIR/tracesphere-platform.service" > /tmp/tracesphere-platform.service
sed -e "s|__TS_USER__|$TS_USER|g" -e "s|__TS_ROOT__|$TS_ROOT|g" \
  "$DIR/tracesphere-rca.service" > /tmp/tracesphere-rca.service
install -m 0644 /tmp/tracesphere-platform.service /etc/systemd/system/tracesphere-platform.service
install -m 0644 /tmp/tracesphere-rca.service /etc/systemd/system/tracesphere-rca.service
rm -f /tmp/tracesphere-platform.service /tmp/tracesphere-rca.service

echo "== 环境文件模板（缺失则生成）=="
install -d /etc/tracesphere
if [ ! -f /etc/tracesphere/platform.env ]; then
  cat > /etc/tracesphere/platform.env <<'ENVEOF'
# TraceSphere Platform 运行时环境（本地部署信息，勿提交仓库）
# ZSVIRT_PASSWORD=<password>
# ZSVIRT_BASE_URL=http://127.0.0.1:8080/zstack/v1
# TRACESPHERE_API_TOKEN=<random-token>   # 非回环绑定必填（直报链路需同值）
# TRACESPHERE_RATE_LIMIT=600              # 写接口每 IP 每分钟限流（0=关闭）
# ZSVIRT_SYNC_INTERVAL=120                # 周期同步秒数（0=仅启动同步）
ENVEOF
  echo "已生成 /etc/tracesphere/platform.env 模板（请填写 ZSVIRT_PASSWORD / TRACESPHERE_API_TOKEN）"
fi
if [ ! -f /etc/tracesphere/rca.env ]; then
  cat > /etc/tracesphere/rca.env <<'ENVEOF'
# TraceSphere RCA 运行时环境（本地部署信息，勿提交仓库）
# TRACESPHERE_PROMETHEUS_URL=http://127.0.0.1:9090
# TRACESPHERE_PLATFORM_TOKEN=<同 platform 的 API token>   # 平台侧启用 token 时必填
# TRACESPHERE_RCA_TOKEN=<random-token>                     # 控制台/CLI 接入需带 Bearer
# TRACESPHERE_RCA_RATE_LIMIT=600
ENVEOF
  echo "已生成 /etc/tracesphere/rca.env 模板（按需填写）"
fi

echo "== 启用并启动 =="
systemctl daemon-reload
systemctl enable --now tracesphere-platform tracesphere-rca
sleep 6
systemctl --no-pager --lines=0 status tracesphere-platform tracesphere-rca | grep -E "●|Active:" || true
echo
echo "日志："
echo "  platform: journalctl -u tracesphere-platform -f"
echo "  rca     : journalctl -u tracesphere-rca -f"
