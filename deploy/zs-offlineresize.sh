#!/usr/bin/env bash
# 离线扩盘：qemu-img resize + VolumeVO 同步 + 重启 VM
set -u
VM=63bbb4613a524e4e97090600af03da93
VOL=c6114309f9d34fa980a00a4895383654
NEW=42949672960
DBPW=zstack.mysql.password

echo "== stop VM =="
virsh destroy $VM 2>/dev/null || true
sleep 3
virsh list --all | head -3

echo
echo "== 找卷文件 =="
FILE=$(find /var/lib/zstack/ps-local -name "*${VOL}*" 2>/dev/null | head -1)
echo "file=$FILE"
if [ -z "$FILE" ]; then
  echo "未找到，列出目录："
  find /var/lib/zstack/ps-local -maxdepth 4 -name "*.qcow2" 2>/dev/null | head -10
  exit 1
fi
qemu-img info "$FILE" | grep -E "file format|virtual size|disk size"

echo
echo "== resize 40G =="
qemu-img resize "$FILE" 40G
qemu-img info "$FILE" | grep -E "virtual size|disk size"

echo
echo "== DB 同步 =="
mysql -uroot -p$DBPW zstack -e "select uuid,size,actualSize from VolumeVO where uuid='$VOL';"
mysql -uroot -p$DBPW zstack -e "update VolumeVO set size=$NEW where uuid='$VOL';"
mysql -uroot -p$DBPW zstack -e "select uuid,size from VolumeVO where uuid='$VOL';"

echo
echo "== start VM =="
virsh start $VM
sleep 45
virsh list --all | head -3
