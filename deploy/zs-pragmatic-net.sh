#!/usr/bin/env bash
# 务实方案：宿主机侧手工提供 DHCP+NAT（绕过 ZSvirt flat DHCP 应用问题）
set -u
VM=a1b2c3d456784b7d8e9f0a1b2c3d4e5f

echo "== [0] 环境检查 =="
which dnsmasq || echo "no-dnsmasq"
systemctl is-active firewalld 2>/dev/null || true

echo
echo "== [1] VM config drive (cdrom) =="
virsh dumpxml $VM | grep -B2 -A4 "device='cdrom'\|cdrom" | head -20

echo
echo "== [2] 桥接口配置 =="
ip addr show br_dvs0_2344 | head -5
ip addr add 10.0.0.2/24 dev br_dvs0_2344 2>/dev/null && echo "ip added" || echo "ip exists or failed"
sysctl -qw net.ipv4.ip_forward=1
iptables -t nat -C POSTROUTING -s 10.0.0.0/24 ! -d 10.0.0.0/24 -j MASQUERADE 2>/dev/null \
  || iptables -t nat -A POSTROUTING -s 10.0.0.0/24 ! -d 10.0.0.0/24 -j MASQUERADE
echo "nat ready"

echo
echo "== [3] dnsmasq =="
cat > /etc/dnsmasq.d/zs-pg-demo.conf <<EOF
interface=br_dvs0_2344
bind-interfaces
except-interface=lo
dhcp-range=10.0.0.10,10.0.0.250,255.255.255.0,12h
dhcp-option=3,10.0.0.2
dhcp-option=6,223.5.5.5
EOF
systemctl restart dnsmasq 2>/dev/null || systemctl start dnsmasq 2>/dev/null || {
  pkill -f "dnsmasq.*zs-pg-demo" 2>/dev/null
  dnsmasq --conf-file=/etc/dnsmasq.d/zs-pg-demo.conf
}
sleep 2
ss -lnup | grep :67 | head -3
systemctl is-active dnsmasq 2>/dev/null || true

echo
echo "== [4] 启动 VM =="
virsh start $VM
sleep 50
virsh list --all | head -5

echo
echo "== [5] dnsmasq 租约 =="
cat /var/lib/misc/dnsmasq.leases 2>/dev/null || cat /var/lib/dnsmasq/dnsmasq.leases 2>/dev/null || echo "no lease file yet"
