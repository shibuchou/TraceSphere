#!/usr/bin/env bash
# evidence-chain.sh —— TraceSphere 最小证据链串联（interim 实现）
# 用途：B 的 Evidence Store/Correlation 上线前，用脚本把一次故障的多层证据按时间窗串联展示
# 用法：
#   evidence-chain.sh [--minutes 5] [--container llama-server] [--corr <correlation_id>] [--out <file>]
#
# 证据来源：
#   1) vm-agent 事件/指标（/opt/tracesphere/evidence/vm-agent.log）
#   2) 容器 cgroup v2（memory.events / memory.current / cpu.stat）
#   3) Prometheus（cAdvisor 容器指标：内存/节流/重启）
#   4) agent-service AppEvent（docker logs）
set -u

MINUTES=5
CONTAINER=""
CORR=""
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --minutes) MINUTES="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    --corr) CORR="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 1 ;;
  esac
done

NOW=$(date -u +%s)
START=$((NOW - MINUTES * 60))
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
[ -z "$OUT" ] && OUT="/opt/tracesphere/evidence/chain-${STAMP}.md"
sudo mkdir -p /opt/tracesphere/evidence

exec > >(sudo tee "$OUT") 2>&1

echo "# TraceSphere 证据链报告（interim）"
echo
echo "- 生成时间：$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "- 时间窗：最近 ${MINUTES} 分钟（$(date -u -d @$START +%H:%M:%S) ~ $(date -u -d @$NOW +%H:%M:%S) UTC）"
[ -n "$CONTAINER" ] && echo "- 目标容器：\`$CONTAINER\`"
[ -n "$CORR" ] && echo "- correlation_id：\`$CORR\`"
echo

# ---------- 1) vm-agent 事件与指标 ----------
echo "## 1. vm-agent 内核事件 / PSI 指标"
LOG=/opt/tracesphere/evidence/vm-agent.log
if [ -f "$LOG" ]; then
  WIN_LO=$(date -u -d "-${MINUTES} minutes" +%Y-%m-%dT%H:%M:%S)
  echo "### 1.1 OOM / 网络异常事件"
  echo '```json'
  grep -a '"wall"' "$LOG" | awk -v w="$WIN_LO" -F'"wall":"' '{split($2,a,"\""); if (a[1] >= w) print}' | grep -aE '"origin":"(oom|tcp)"' | tail -20
  echo '```'
  echo "### 1.2 进程事件（窗口内最后 15 条）"
  echo '```json'
  grep -a '"wall"' "$LOG" | awk -v w="$WIN_LO" -F'"wall":"' '{split($2,a,"\""); if (a[1] >= w) print}' | grep -a '"origin":"process"' | tail -15
  echo '```'
  echo "### 1.3 PSI / cgroup 指标（最近 12 条）"
  echo '```json'
  grep -a '"type":"metric"' "$LOG" | awk -v s="${START}000000000" -F'"ts":' '{split($2,a,","); if (a[1]+0 >= s) print}' | tail -12
  echo '```'
else
  echo "_vm-agent 日志不存在（未启动？）_"
fi
echo

# ---------- 2) 容器 cgroup v2 证据 ----------
CG=""
if [ -n "$CONTAINER" ]; then
  echo "## 2. 容器 cgroup v2 证据（\`$CONTAINER\`）"
  CID=$(sudo docker inspect -f '{{.Id}}' "$CONTAINER" 2>/dev/null | cut -c1-64)
  PID=$(sudo docker inspect -f '{{.State.Pid}}' "$CONTAINER" 2>/dev/null || echo 0)
  CGPATH=""
  if [ "$PID" != "0" ] && sudo test -r "/proc/$PID/cgroup"; then
    CGPATH=$(sudo cat "/proc/$PID/cgroup" 2>/dev/null | awk -F: '/^0:/{print $3}')
  fi
  [ -z "$CGPATH" ] && CGPATH="/system.slice/docker-${CID}.scope"
  CG="/sys/fs/cgroup${CGPATH}"
  echo
  echo "- cgroup 路径：\`$CG\`（container_id=${CID:0:12}… pid=$PID）"
  echo '```text'
  for f in memory.current memory.max memory.events cpu.stat; do
    if sudo test -f "$CG/$f"; then
      echo "--- $f ---"
      sudo cat "$CG/$f" 2>/dev/null | head -12
    fi
  done
  echo '```'
  if sudo test -f "$CG/memory.events"; then
    OOMK=$(sudo awk '/oom_kill/{print $2}' "$CG/memory.events")
    echo
    echo "> **关键证据**：\`memory.events.oom_kill = ${OOMK:-0}\`（>0 表示该容器发生过 cgroup OOM 杀进程）"
  fi
  echo
fi

# ---------- 3) Prometheus 指标（cAdvisor） ----------
echo "## 3. Prometheus / cAdvisor 指标（时间窗内）"
if [ -n "$CONTAINER" ]; then
  pquery() {
    local q="$1" label="$2"
    local enc
    enc=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$q")
    curl -s --max-time 8 "http://127.0.0.1:9090/api/v1/query_range?query=${enc}&start=${START}&end=${NOW}&step=15" | python3 -c "
import json, sys
label = sys.argv[1]
try:
    d = json.load(sys.stdin)
    res = d.get('data', {}).get('result', [])
    if not res:
        print(label + ': (no data)')
    else:
        vals = [float(v[1]) for v in res[0]['values']]
        print('%s: min=%.3g max=%.3g last=%.3g (n=%d)' % (label, min(vals), max(vals), vals[-1], len(vals)))
except Exception as e:
    print(label + ': parse error ' + str(e))
" "$label"
  }
  pquery "container_memory_working_set_bytes{id=\"${CGPATH}\"}" "container_memory_working_set_bytes (id)"
  pquery "container_cpu_cfs_throttled_periods_total{id=\"${CGPATH}\"}" "cpu_cfs_throttled_periods_total (id)"
  pquery "container_cpu_cfs_periods_total{id=\"${CGPATH}\"}" "cpu_cfs_periods_total (id)"
  pquery "container_start_time_seconds{id=\"${CGPATH}\"}" "container_start_time_seconds (id, 重启检测)"
else
  echo "_未指定容器，跳过_"
fi
echo

# ---------- 4) agent-service AppEvent ----------
echo "## 4. Agent 任务事件（agent-service 日志）"
echo '```json'
if [ -n "$CORR" ]; then
  sudo docker logs agent-service --since "${MINUTES}m" 2>&1 | grep -a "$CORR" | tail -20
else
  sudo docker logs agent-service --since "${MINUTES}m" 2>&1 | grep -a '"event_type"' | tail -30
fi
echo '```'
echo

# ---------- 5) 关联提示 ----------
echo "## 5. 关联提示（供 RCA 使用）"
echo "- 把「时间窗内同时出现」的证据按发生时间排序，即可得到："
echo "  1. 系统层信号（vm-agent/cgroup 指标）→ 2. 容器层状态（cgroup/Prometheus）→ 3. 应用层表现（Agent 事件）"
echo "- 若携带 \`correlation_id\`：应用层事件可直接串联；系统层事件按 \`resource_id / 时间窗 / 容器身份\` 关联"
