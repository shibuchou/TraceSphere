#!/usr/bin/env bash
set -u
IP=${VM_IP:?}
VM=63bbb4613a524e4e97090600af03da93

echo "== ping =="
ping -c 2 -W 2 $IP | tail -3

echo
echo "== ssh test (ubuntu/${ZS_PW:?export ZS_PW}) =="
sshpass -p ${ZS_PW:?export ZS_PW} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 \
  ubuntu@$IP 'hostname; echo SSH_OK; ip -4 addr show | grep "inet " | head -3' 2>&1 | tail -8

echo
echo "== guest agent ping =="
virsh qemu-agent-command $VM '{"execute":"guest-ping"}' 2>&1 | head -3

echo
echo "== ls cdrom source =="
virsh dumpxml $VM | grep -A8 "device='cdrom'" | grep -E "source|target" | head -5
