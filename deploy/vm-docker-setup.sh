#!/usr/bin/env bash
# workload-vm 内：安装 Docker + compose 插件 + registry 镜像加速
set -e
echo "== apt 换清华源 =="
if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
  sudo sed -i 's|http://archive.ubuntu.com/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ubuntu|g; s|http://security.ubuntu.com/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' /etc/apt/sources.list.d/ubuntu.sources
fi
sudo apt-get update -qq

echo "== 安装 docker + compose =="
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2 >/dev/null
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu

echo "== registry mirror =="
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1panel.live",
    "https://hub.rat.dev"
  ]
}
EOF
sudo systemctl restart docker
sleep 3

echo "== 版本 =="
sudo docker version --format 'server={{.Server.Version}}'

echo "== 冒烟测试 =="
sudo docker pull hello-world >/dev/null 2>&1 && echo "PULL_OK" || echo "PULL_FAIL"
sudo docker run --rm hello-world 2>&1 | grep -i "working" | head -1 || true
