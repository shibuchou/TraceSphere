#!/usr/bin/env bash
# 在 VM 内：后台拉取 llama.cpp server 镜像 + 下载 Qwen3.5-0.8B GGUF 模型
set -u
MIRROR=https://hf-mirror.com
REPO=ggml-org/Qwen3.5-0.8B-GGUF

echo "== 模型仓库文件列表 =="
LIST=$(curl -s --max-time 25 "$MIRROR/api/models/$REPO")
echo "$LIST" | grep -o '"rfilename":"[^"]*"' | sed 's/"rfilename":"//; s/"$//' > /tmp/gguf-list.txt
head -15 /tmp/gguf-list.txt

FILE=$(grep -i "q4_k_m.gguf" /tmp/gguf-list.txt | head -1)
[ -z "$FILE" ] && FILE=$(grep -i "q8_0.gguf" /tmp/gguf-list.txt | head -1)
[ -z "$FILE" ] && FILE=$(grep -i "\.gguf" /tmp/gguf-list.txt | head -1)
echo "selected: $FILE"

sudo mkdir -p /opt/tracesphere/models
if [ -n "$FILE" ]; then
  sudo nohup curl -sSL -o /opt/tracesphere/models/model.gguf "$MIRROR/$REPO/resolve/main/$FILE" > /tmp/model-dl.log 2>&1 < /dev/null &
  echo "model download started (background)"
fi

echo
echo "== 后台拉取 llama.cpp:server 镜像 =="
sudo nohup docker pull ghcr.m.daocloud.io/ggml-org/llama.cpp:server > /tmp/llama-pull.log 2>&1 < /dev/null &
echo "image pull started (background)"
sleep 5
echo "== 5s 后进度 =="
ls -la /opt/tracesphere/models/ 2>/dev/null
pgrep -af "curl.*model.gguf" | head -2
pgrep -af "docker pull" | head -2
