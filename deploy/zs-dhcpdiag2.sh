#!/usr/bin/env bash
set -u
LOG=/var/log/zstack/zstack-kvmagent.log
echo "== flat dhcp 相关调用（最近20条）=="
grep -a "flatnetworkprovider" "$LOG" 2>/dev/null | tail -20
echo
echo "== agent 报错（最近10条）=="
grep -a -iE "error|exception" "$LOG" 2>/dev/null | tail -10
echo
echo "== kvmagent 进程 =="
ps aux | grep -i kvmagent | grep -v grep | head -3
echo
echo "== libvirt 域 =="
virsh list --all 2>/dev/null | head -10
echo
echo "== netns / dnsmasq 配置 =="
ip netns list 2>/dev/null | head -5
find /var/lib/zstack /etc -name "*dnsmasq*" 2>/dev/null | head -8
echo
echo "== VM 域 XML 摘要（找 ZStack-VM）=="
D=$(virsh list --name 2>/dev/null | head -3)
echo "domains: $D"
