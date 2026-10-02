#!/usr/bin/env bash
set -u
UIROOT=/usr/local/zstack/zstack-ui
echo "== backup-storage 相关 API 字符串 =="
grep -rho "backup-storage/[a-zA-Z0-9/_-]*" "$UIROOT" 2>/dev/null | sort -u | head -40
echo
echo "== primary-storage 相关 API 字符串 =="
grep -rho "primary-storage/[a-zA-Z0-9/_-]*" "$UIROOT" 2>/dev/null | sort -u | head -20
echo
echo "== 找 'Local Directory' 文案上下文 =="
grep -rl "Local Directory" "$UIROOT" 2>/dev/null | head -5
