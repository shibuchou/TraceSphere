#!/usr/bin/env bash
# TraceSphere 提交包生成：排除内部资料 + 内网信息脱敏
#
# 用法（在仓库根执行）：
#   bash tools/sanitize-for-submission.sh [输出目录，默认 dist/submission]
#
# 产出：<输出目录>/ 以及同名 .tar.gz 提交包
# 约定：内部资料清单见 README「内部资料与提交边界」；内网网段统一替换为
#       RFC 5737 文档保留网段（192.0.2.0/24、10.0.0.0/24），VM uuid 替换为占位值。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist/submission}"

rm -rf "$OUT"
mkdir -p "$OUT"

rsync -a \
  --exclude '.git' --exclude 'node_modules' --exclude 'dist' \
  --exclude '.npm-cache' --exclude '.cache' \
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
  "$ROOT/" "$OUT/"

# 脱敏：内网网段 / VM uuid / 口令 / 本机用户名与内网宿主 -> 占位值（仅作用于提交副本）
grep -rlI -E '192\.168\.122\.|10\.100\.0\.|63bbb4613a524e4e97090600af03da93|zsvirt\.123|222\.24\.18\.171|ailab1' "$OUT" 2>/dev/null \
  | while IFS= read -r f; do
      sed -i \
        -e 's/192\.168\.122\./192.0.2./g' \
        -e 's/10\.100\.0\./10.0.0./g' \
        -e 's/63bbb4613a524e4e97090600af03da93/a1b2c3d456784b7d8e9f0a1b2c3d4e5f/g' \
        -e 's/63bbb461/a1b2c3d4/g' \
        -e 's/zsvirt\.123/<password>/g' \
        -e 's/222\.24\.18\.171/<kvm-host>/g' \
        -e 's#/home/ailab1#/home/<user>#g' \
        -e 's/ailab1/<user>/g' \
        "$f"
    done

echo "== 残留敏感信息扫描（应输出 clean）=="
if grep -rnI -E 'zsvirt\.123|192\.168\.122\.|10\.100\.0\.|222\.24\.18\.171|ailab1|87994|63bbb461' "$OUT" 2>/dev/null; then
  echo "!! 仍有残留，请检查" >&2
  exit 1
else
  echo "clean"
fi

tar -C "$(dirname "$OUT")" -czf "${OUT%/}.tar.gz" "$(basename "$OUT")"
echo "== 提交包就绪：${OUT%/}.tar.gz =="
