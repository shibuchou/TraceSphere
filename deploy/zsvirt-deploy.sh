#!/usr/bin/env bash
# TraceSphere - ZSvirt 管理节点快速部署脚本（Environment Gate 专用）
# 用法: bash zsvirt-deploy.sh [--memory 16384] [--vcpus 12] [--vm-name zsvirt-mgmt]
# 前置: 镜像已下载到 ~/zsvirt/ZSvirt-x86_64-1.0.0-h84r.qcow2
set -euo pipefail

IMG_SRC="${HOME}/zsvirt/ZSvirt-x86_64-1.0.0-h84r.qcow2"
IMG_DST="/var/lib/libvirt/images/ZSvirt-x86_64-1.0.0-h84r.qcow2"
SHA256="383099b3ad9cfd793dfd49e4b2dc99743832073d3c39e86deae91be59e5d9c3b"
VM_NAME="zsvirt-mgmt"
MEMORY=16384
VCPUS=12

while [ $# -gt 0 ]; do
  case "$1" in
    --memory) MEMORY="$2"; shift 2 ;;
    --vcpus) VCPUS="$2"; shift 2 ;;
    --vm-name) VM_NAME="$2"; shift 2 ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
done

echo "[1/5] 校验镜像 SHA256..."
if [ -f "$IMG_DST" ]; then
  echo "镜像已在存储池: $IMG_DST（跳过校验与迁移）"
else
  if [ ! -f "$IMG_SRC" ]; then echo "镜像不存在: $IMG_SRC"; exit 1; fi
  echo "$SHA256  $IMG_SRC" | sha256sum -c -

  echo "[2/5] 迁移镜像到 libvirt 存储池..."
  sudo mv -n "$IMG_SRC" "$IMG_DST"
fi

if sudo virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
  echo "虚拟机 $VM_NAME 已存在，跳过创建。"
  sudo virsh list --all
  exit 0
fi

echo "[3/5] 确保 default 网络已启动..."
sudo virsh net-start default >/dev/null 2>&1 || true
sudo virsh net-autostart default >/dev/null 2>&1 || true

echo "[4/5] 创建并启动 ZSvirt 管理节点虚拟机（${VCPUS} vCPU / ${MEMORY} MiB）..."
sudo virt-install \
  --name "$VM_NAME" \
  --memory "$MEMORY" \
  --vcpus "$VCPUS" \
  --cpu host-passthrough \
  --disk path="$IMG_DST",format=qcow2,bus=virtio \
  --import \
  --network network=default,model=virtio \
  --graphics none \
  --osinfo detect=on,require=off \
  --noautoconsole

echo "[5/5] 等待 DHCP 分配地址（最多 120s）..."
for i in $(seq 1 24); do
  LEASES=$(sudo virsh net-dhcp-leases default 2>/dev/null || true)
  echo "$LEASES"
  if echo "$LEASES" | grep -q ipv4; then break; fi
  sleep 5
done

echo
echo "后续步骤:"
echo "  1) 登录控制台: sudo virsh console $VM_NAME   # 初始密码见 ZSvirt 安装文档，登录后立即 passwd 修改"
echo "  2) 配置管理服务: zstack-ctl change_ip --ip <管理节点IP> && zstack-ctl start"
echo "  3) 浏览器访问 https://<管理节点IP> 完成平台初始化"
echo "  4) Gate 验证: curl -k https://<管理节点IP>/zstack/v1/vm-instances（携带 OAuth session）"
