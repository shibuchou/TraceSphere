#!/usr/bin/env bash
# TraceSphere - vm-agent eBPF 能力实测（成员 A, W1 Environment Gate 支持）
# 在目标内核上确认 hook 可用性与权限，输出用于冻结 vm-agent 的 attach 方案
set -u
echo "== kernel =="
uname -r
echo "perf_event_paranoid=$(cat /proc/sys/kernel/perf_event_paranoid)"
echo "BTF: $(test -f /sys/kernel/btf/vmlinux && echo yes || echo no)"
echo

echo "== hook 盘点 =="
for pat in "*oom*" "tracepoint:tcp:*" "tracepoint:sched:sched_process_*"; do
  echo "--- bpftrace -l '$pat' (head 12) ---"
  sudo -n bpftrace -l "$pat" 2>&1 | head -12
  echo
done

echo "== tracefs / bpffs =="
mount | grep -E "tracefs|bpffs" || echo "(未显式挂载，bpftrace 通常会自动处理)"
echo

echo "== attach 实测 1/3: oom:mark_victim (6s) =="
sudo -n timeout 6 bpftrace -e 'tracepoint:oom:mark_victim { printf("OOM pid=%d comm=%s\n", pid, comm); }' 2>&1 || true
echo

echo "== attach 实测 2/3: sched_process_exec (6s) =="
sudo -n timeout 6 bpftrace -e 'tracepoint:sched:sched_process_exec { printf("EXEC pid=%d comm=%s\n", pid, comm); }' 2>&1 || true
echo

echo "== attach 实测 3/3: tcp:tcp_retransmit_skb (6s) =="
sudo -n timeout 6 bpftrace -e 'tracepoint:tcp:tcp_retransmit_skb { printf("RETRANSMIT pid=%d\n", pid); }' 2>&1 || true
echo

echo "capability test done"
