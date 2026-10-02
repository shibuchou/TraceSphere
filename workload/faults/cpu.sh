#!/usr/bin/env bash
# Case 2: CPU 资源争抢 —— 运行 CPU 压力容器（2 workers，cpus=2）
set -u
docker rm -f cpu-stress >/dev/null 2>&1 || true
docker run -d --name cpu-stress --cpus=2 \
  python:3.12-slim \
  python -c "import multiprocessing, time
def burn():
    while True:
        pass
for _ in range(2):
    multiprocessing.Process(target=burn).start()
time.sleep(7200)" >/dev/null
echo "cpu-stress started (2 workers, cpus=2)"
