#!/usr/bin/env bash
# 通过 virsh send-key 向 guest 控制台逐字符输入（用于无串口输出的 guest）
# 用法: sendkeys.sh "text"   支持 a-z 0-9 空格 . - / ; : , = _ @ |
set -u
VM="${SENDKEYS_VM:-zsvirt-mgmt}"

send() {
  sudo -n virsh send-key "$VM" "$@" >/dev/null
  sleep 0.12
}

text="$1"
i=0
while [ "$i" -lt "${#text}" ]; do
  ch="${text:$i:1}"
  case "$ch" in
    [a-z]) send "KEY_$(printf '%s' "$ch" | tr '[:lower:]' '[:upper:]')" ;;
    [0-9]) send "KEY_$ch" ;;
    ' ') send KEY_SPACE ;;
    '.') send KEY_DOT ;;
    '-') send KEY_MINUS ;;
    '/') send KEY_SLASH ;;
    ';') send KEY_SEMICOLON ;;
    ',') send KEY_COMMA ;;
    '=') send KEY_EQUAL ;;
    ':') send KEY_LEFTSHIFT KEY_SEMICOLON ;;
    '_') send KEY_LEFTSHIFT KEY_MINUS ;;
    '@') send KEY_LEFTSHIFT KEY_2 ;;
    '|') send KEY_LEFTSHIFT KEY_BACKSLASH ;;
    *) echo "[skip] unsupported char: '$ch'" >&2 ;;
  esac
  i=$((i + 1))
done
