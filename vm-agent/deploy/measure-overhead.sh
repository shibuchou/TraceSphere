#!/usr/bin/env bash
# vm-agent 开销实测：按间隔采样 CPU% 与 RSS，输出统计
# 用法: measure-overhead.sh [--seconds 60] [--interval 2] [--label idle]
set -u
SECONDS_RUN=60
INTERVAL=2
LABEL=idle
while [ $# -gt 0 ]; do
  case "$1" in
    --seconds)  SECONDS_RUN=$2; shift 2 ;;
    --interval) INTERVAL=$2; shift 2 ;;
    --label)    LABEL=$2; shift 2 ;;
    *) echo "unknown arg: $1"; exit 1 ;;
  esac
done

PID=$(pgrep -x vm-agent | head -1)
[ -z "$PID" ] && { echo "vm-agent 未运行"; exit 1; }
HZ=$(getconf CLK_TCK)

cpu_ticks() { awk '{print $14+$15}' "/proc/$1/stat"; }
rss_kb()    { awk '/VmRSS/{print $2}' "/proc/$1/status"; }

START=$(date +%s)
LAST=$START
C0=$(cpu_ticks "$PID")
N=0; SUM=0; MAX=0
echo "label=$LABEL pid=$PID interval=${INTERVAL}s duration=${SECONDS_RUN}s hz=$HZ"
printf "%-8s %-8s %-10s\n" "t(s)" "cpu%" "rss_MB"
while [ $(( $(date +%s) - START )) -lt "$SECONDS_RUN" ]; do
  sleep "$INTERVAL"
  T1=$(date +%s); C1=$(cpu_ticks "$PID")
  RSS=$(rss_kb "$PID"); RSSMB=$((RSS / 1024))
  DT=$((T1 - LAST)); [ "$DT" -le 0 ] && DT=1
  CPU=$(awk -v c0="$C0" -v c1="$C1" -v hz="$HZ" -v dt="$DT" 'BEGIN{printf "%d", (c1-c0)*100.0/hz/dt}')
  printf "%-8s %-8s %-10s\n" "$((T1 - START))" "$CPU" "$RSSMB"
  N=$((N + 1)); SUM=$((SUM + CPU)); [ "$RSSMB" -gt "$MAX" ] && MAX=$RSSMB
  LAST=$T1; C0=$C1
done
AVG=$((SUM / N))
echo "----"
echo "summary: label=$LABEL samples=$N avg_cpu=${AVG}% max_rss=${MAX}MB"
