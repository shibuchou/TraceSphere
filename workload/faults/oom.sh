#!/usr/bin/env bash
# Case 1: 容器 OOM —— 128MiB 内存限制下持续分配内存
set -u
docker rm -f oom-victim >/dev/null 2>&1 || true
docker run -d --name oom-victim --memory=128m --memory-swap=128m \
  python:3.12-slim \
  python -c "import time
blocks = []
while True:
    blocks.append(bytearray(16 * 1024 * 1024))
    time.sleep(0.2)" >/dev/null
echo "oom-victim started (memory limit 128MiB, will be OOM-killed)"
