#!/usr/bin/env bash
# TraceSphere 一键起演示环境（B 的 platform + A 的采集（vm-agent/agent-service 直报）+ C 的诊断服务/Console）
#
#   bash tools/demo-up.sh            # 起服务
#   bash tools/demo-up.sh --status   # 查看状态
#   bash tools/demo-up.sh --stop     # 停止（不动物业/VM 内的业务容器）
#
# 端口：platform 8000 ｜ RCA + Console 8010 ｜ Prometheus（业务 VM）:9090
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 部署环境参数（必填，避免仓库内硬编码部署信息）
VM=${TRACESPHERE_VM_HOST:?请先 export TRACESPHERE_VM_HOST（业务 VM IP）}
VM_UUID=${TRACESPHERE_VM_UUID:?请先 export TRACESPHERE_VM_UUID（ZSvirt VM uuid）}
PLATFORM=${TRACESPHERE_PLATFORM_URL:-http://127.0.0.1:8000}
ACTION=${1:-up}
SSH="sshpass -p ${VM_PASSWORD:?请先 export VM_PASSWORD（业务 VM SSH 密码）} ssh -o StrictHostKeyChecking=no ubuntu@$VM"

start_platform() {
  if systemctl list-unit-files tracesphere-platform.service >/dev/null 2>&1; then
    sudo -n systemctl start tracesphere-platform 2>/dev/null || true
    sleep 2
    echo "  [platform] systemd: $(systemctl is-active tracesphere-platform) -> $PLATFORM"
    return
  fi
  if pgrep -f "run.py --provider rest" >/dev/null 2>&1; then
    echo "  [platform] 已在运行（nohup）"
    return
  fi
  cd "$ROOT/platform" || exit 1
  mkdir -p data
  ZSVIRT_PASSWORD=${ZSVIRT_PASSWORD:?请先 export ZSVIRT_PASSWORD} nohup python3 run.py --provider rest \
      --host 0.0.0.0 --port 8000 --db data/tracesphere.db > data/platform.log 2>&1 &
  sleep 6
  echo "  [platform] 已启动 -> $PLATFORM"
}

ensure_vm_agent() {
  STATUS=$($SSH 'systemctl is-active tracesphere-vm-agent 2>/dev/null || sudo systemctl restart tracesphere-vm-agent; systemctl is-active tracesphere-vm-agent' 2>/dev/null | tail -1)
  echo "  [vm-agent] $STATUS（直报 -> $PLATFORM）"
}

start_rca() {
  if systemctl list-unit-files tracesphere-rca.service >/dev/null 2>&1; then
    sudo -n systemctl start tracesphere-rca 2>/dev/null || true
    sleep 2
    echo "  [rca] systemd: $(systemctl is-active tracesphere-rca) -> http://<GPU1-IP>:8010"
    return
  fi
  cd "$ROOT/rca" || exit 1
  if pgrep -f "bin/tracesphere serve" >/dev/null 2>&1; then
    echo "  [rca] 已在运行（nohup）"
    return
  fi
  CONSOLE=""
  [ -d "$ROOT/console/dist" ] && CONSOLE="--console $ROOT/console/dist"
  TRACESPHERE_PLATFORM_URL=$PLATFORM nohup ./bin/tracesphere serve --listen :8010 $CONSOLE \
      > /tmp/rca-serve.log 2>&1 &
  sleep 3
  echo "  [rca] 诊断服务 + Console 已启动 -> http://<GPU1-IP>:8010"
}

case "$ACTION" in
  up)
    echo "== 启动 TraceSphere 演示环境 =="
    start_platform
    ensure_vm_agent
    start_rca
    echo
    curl -s --max-time 5 $PLATFORM/api/v1/health | python3 -c "import json,sys;d=json.load(sys.stdin);print('  platform :',d['provider']['name'],d['database']['counts'])" 2>/dev/null
    curl -s --max-time 5 http://127.0.0.1:8010/api/v1/health | python3 -c "import json,sys;d=json.load(sys.stdin);print('  rca      :',d['sources'])" 2>/dev/null
    curl -s --max-time 5 -o /dev/null -w "  console  : HTTP %{http_code}\n" http://127.0.0.1:8010/
    ;;
  --status|status)
    echo "platform : $(systemctl is-active tracesphere-platform 2>/dev/null || echo stopped)"
    echo "rca      : $(systemctl is-active tracesphere-rca 2>/dev/null || echo stopped)"
    echo "vm-agent : $($SSH 'systemctl is-active tracesphere-vm-agent' 2>/dev/null || echo stopped)"
    curl -s --max-time 5 http://127.0.0.1:8010/api/v1/health | python3 -m json.tool 2>/dev/null | head -20
    ;;
  --stop|stop)
    if systemctl list-unit-files tracesphere-rca.service >/dev/null 2>&1; then
      sudo -n systemctl stop tracesphere-rca tracesphere-platform 2>/dev/null || true
    else
      pkill -f "bin/tracesphere serve" 2>/dev/null
      pkill -f "run.py --provider rest" 2>/dev/null
    fi
    echo "已停止 platform / rca（VM 内 vm-agent/负载保持运行）"
    ;;
  *)
    echo "用法: $0 [up|--status|--stop]"; exit 2 ;;
esac
