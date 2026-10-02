#!/usr/bin/env bash
set -u
echo "== dnsmasq status =="
systemctl is-active dnsmasq 2>/dev/null
pgrep -af dnsmasq | head -3

echo
echo "== lease files =="
for f in /var/lib/misc/dnsmasq.leases /var/lib/dnsmasq/dnsmasq.leases /var/lib/dnsmasq.leases; do
  if [ -f "$f" ]; then echo "--- $f ---"; cat "$f"; fi
done

LEASE=""
for f in /var/lib/misc/dnsmasq.leases /var/lib/dnsmasq/dnsmasq.leases; do
  [ -f "$f" ] && LEASE="$f"
done
IP=$(awk '{print $3}' "$LEASE" 2>/dev/null | head -1)
echo
echo "IP=[$IP]"
if [ -n "$IP" ]; then
  ping -c 2 -W 2 "$IP" | tail -2
  echo
  sshpass -p ${ZS_PW:?export ZS_PW} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 \
    ubuntu@$IP 'hostname; echo SSH_OK; ip -4 addr show | grep inet | head -4; sudo cloud-init status 2>/dev/null | head -2' 2>&1 | tail -8
fi
