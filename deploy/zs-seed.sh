#!/usr/bin/env bash
# 为 VM 注入 cloud-init NoCloud seed（设置 ubuntu/root 密码 + 允许密码 SSH）
set -u
VM=63bbb4613a524e4e97090600af03da93
SEED=/var/lib/zstack/seed.iso

echo "== 工具检查 =="
command -v genisoimage || command -v mkisofs || command -v xorriso || dnf install -y genisoimage >/dev/null 2>&1 || true
command -v genisoimage || command -v mkisofs || command -v xorriso || { echo "NO ISO TOOL"; exit 1; }

echo "== 制作 seed =="
rm -rf /tmp/seed && mkdir -p /tmp/seed
cat > /tmp/seed/meta-data <<'EOF'
instance-id: iid-tracesphere-1
local-hostname: workload-vm
EOF
cat > /tmp/seed/user-data <<'EOF'
#cloud-config
ssh_pwauth: true
disable_root: false
chpasswd:
  list: |
    ubuntu:${ZS_PW:?export ZS_PW}
    root:${ZS_PW:?export ZS_PW}
  expire: false
EOF

if command -v genisoimage >/dev/null; then
  genisoimage -output $SEED -volid cidata -joliet -rock /tmp/seed/user-data /tmp/seed/meta-data >/dev/null
else
  xorriso -as mkisofs -output $SEED -volid cidata -joliet -rock /tmp/seed/user-data /tmp/seed/meta-data >/dev/null 2>&1
fi
ls -la $SEED

echo "== 关机 + 替换 cdrom 为 seed =="
virsh destroy $VM 2>/dev/null || true
sleep 2
virsh change-media $VM hdc $SEED --config --force 2>&1 | head -3 || \
  virsh attach-disk $VM $SEED hdd --type cdrom --config --targetbus ide 2>&1 | head -3

echo "== 启动 =="
virsh start $VM
sleep 60

echo "== 租约 =="
cat /var/lib/misc/dnsmasq.leases 2>/dev/null

echo
echo "== SSH 测试 =="
IP=$(awk '{print $3}' /var/lib/misc/dnsmasq.leases 2>/dev/null | head -1)
echo "IP=$IP"
sshpass -p ${ZS_PW:?export ZS_PW} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 \
  ubuntu@$IP 'hostname; echo SSH_OK; cloud-init status 2>/dev/null | head -2; ip -4 addr show | grep "inet " | head -3' 2>&1 | tail -8
