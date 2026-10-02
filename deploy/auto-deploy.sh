#!/usr/bin/env bash
# Watcher: 等待 ZSvirt 镜像下载完成后自动执行部署脚本（仅一次）
set -u
LOG="$HOME/zsvirt/auto-deploy.log"
echo "[$(date '+%F %T')] watcher started" >> "$LOG"

while pgrep -f 'curl.*ZSvirt-x86_64' >/dev/null 2>&1; do
  sleep 60
done

echo "[$(date '+%F %T')] download finished (curl exited)" >> "$LOG"
sleep 15
bash "$HOME/zsvirt/zsvirt-deploy.sh" >> "$LOG" 2>&1
RC=$?
echo "[$(date '+%F %T')] deploy script exit=$RC" >> "$LOG"
