#!/usr/bin/env bash
set -u
MN=${MN_IP:?}
PW=${ZS_PW:?export ZS_PW}
BASE="http://$MN:8080/zstack/v1"
PWHASH=$(printf '%s' "$PW" | sha512sum | cut -d' ' -f1)
SESS=$(curl -s -m 15 -X PUT "$BASE/accounts/login" \
  -H 'Content-Type: application/json' \
  -d "{\"logInByAccount\":{\"accountName\":\"admin\",\"password\":\"$PWHASH\"}}" \
  | sed -n 's/.*"uuid":"\([^"]*\)".*/\1/p' | head -1)
AH="Authorization: OAuth $SESS"
mnssh() { sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@$MN "$@"; }

probe() {
  echo "--- POST /$1 ---"
  curl -s -m 20 -X POST -H "$AH" -H 'Content-Type: application/json' -d "$2" "$BASE/$1" | head -c 300
  echo
}

probe backup-storage/nfs '{"params":{"name":"bs-nfs","url":"${MN_IP:?}:/var/lib/zstack/nfs-bs"}}'
probe backup-storage/local '{"params":{"name":"bs-localdir","url":"/var/lib/zstack/bs-localdir"}}'
probe backup-storage/local-directory '{"params":{"name":"bs-localdir","url":"/var/lib/zstack/bs-localdir"}}'
probe backup-storage/local-backup-storage '{"params":{"name":"bs-localdir","url":"/var/lib/zstack/bs-localdir"}}'

echo
echo "== NFS server availability on MN =="
mnssh 'rpm -q nfs-utils 2>/dev/null; which exportfs; systemctl is-active nfs-server 2>/dev/null; echo ---; grep -i nfs /etc/exports 2>/dev/null | head -3'
