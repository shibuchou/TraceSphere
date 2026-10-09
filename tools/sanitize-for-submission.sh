#!/usr/bin/env bash
# TraceSphere 提交包生成：排除内部资料 + 内网信息脱敏
#
# 用法（在仓库根执行）：
#   bash tools/sanitize-for-submission.sh [输出目录，默认 dist/submission]
#
# 产出：<输出目录>/ 以及同名 .tar.gz 提交包
#
# 安全约定：内网标识（网段 / VM uuid / 口令字样 / 本机用户名等）**不写入本仓库**，
# 本脚本从外部规则文件读取"待替换标识"，避免脱敏工具自身泄露内网信息。
#   规则文件：$TS_SANITIZE_RULES，默认 tools/sanitize-rules.local（已在 .gitignore）
#   文件格式：每行 "<正则><TAB><替换值>"，'#' 开头为注释；占位符 {USER} 替换为当前登录用户名。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist/submission}"
RULES_FILE="${TS_SANITIZE_RULES:-$ROOT/tools/sanitize-rules.local}"
LOCAL_USER="$(id -un 2>/dev/null || echo '')"

if [ ! -f "$RULES_FILE" ]; then
  echo "!! 缺少脱敏规则文件：$RULES_FILE" >&2
  echo "   该文件含内网标识，不随仓库分发；请从内部交接材料恢复，或用 TS_SANITIZE_RULES 指定。" >&2
  exit 2
fi

RULES=()
while IFS=$'\t' read -r pat rep || [ -n "${pat:-}" ]; do
  case "${pat:-}" in '' | \#*) continue ;; esac
  pat="${pat//\{USER\}/$LOCAL_USER}"
  rep="${rep//\{USER\}/$LOCAL_USER}"
  RULES+=("$pat"$'\t'"$rep")
done < "$RULES_FILE"

if [ "${#RULES[@]}" -eq 0 ]; then
  echo "!! 脱敏规则文件为空：$RULES_FILE" >&2
  exit 2
fi
PATTERNS="$(printf '%s\n' "${RULES[@]}" | cut -f1 | paste -sd'|' -)"

rm -rf "$OUT"
mkdir -p "$OUT"

rsync -a \
  --exclude '.git' --exclude 'node_modules' --exclude 'dist' \
  --exclude '.npm-cache' --exclude '.cache' \
  --exclude '.*-backup-*' \
  --exclude 'bin' --exclude 'data' --exclude '__pycache__' \
  --exclude 'docs/开工交接-*.md' \
  --exclude 'docs/交接文档-*.md' \
  --exclude 'docs/fixlog-*.md' \
  --exclude 'docs/anonymization-sweep-*.md' \
  --exclude 'docs/demo-*.md' \
  --exclude 'deploy/README.md' \
  --exclude 'deploy/zs-*.sh' \
  --exclude 'deploy/mn-*.sh' \
  --exclude 'deploy/*.exp' \
  --exclude 'deploy/login-try.sh' \
  --exclude 'tools/sanitize-for-submission.sh' \
  --exclude 'tools/sanitize-rules.local' \
  "$ROOT/" "$OUT/"

# 脱敏：按外部规则替换（仅作用于提交副本）
grep -rlI -E "$PATTERNS" "$OUT" 2>/dev/null \
  | while IFS= read -r f; do
      for rule in "${RULES[@]}"; do
        pat="${rule%%$'\t'*}"
        rep="${rule#*$'\t'}"
        sed -i -E "s|$pat|$rep|g" "$f"
      done
    done

echo "== 残留敏感信息扫描（应输出 clean）=="
if grep -rnI -E "$PATTERNS" "$OUT" 2>/dev/null; then
  echo "!! 仍有残留，请检查" >&2
  exit 1
else
  echo "clean"
fi

tar -C "$(dirname "$OUT")" -czf "${OUT%/}.tar.gz" "$(basename "$OUT")"
echo "== 提交包就绪：${OUT%/}.tar.gz =="