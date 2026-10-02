#!/usr/bin/env bash
set -u
VM=63bbb4613a524e4e97090600af03da93
VOLDIR=/var/lib/zstack/ps-local/rootVolumes/acct-36c27e8ff05c4780bf6d2fa65700f22e/vol-c6114309f9d34fa980a00a4895383654

echo "== volume dir 内容 =="
ls -la "$VOLDIR"
FILE=$(find "$VOLDIR" -type f -name "*.qcow2" | head -1)
[ -z "$FILE" ] && FILE=$(find "$VOLDIR" -type f | head -1)
echo "file=$FILE"

echo
echo "== stop VM =="
virsh destroy $VM 2>/dev/null || true
sleep 3

echo "== resize =="
qemu-img info "$FILE" | grep -E "file format|virtual size|disk size"
qemu-img resize "$FILE" 40G
qemu-img info "$FILE" | grep -E "virtual size|disk size"

echo "== start VM =="
virsh start $VM
sleep 50
virsh list --all | head -3
