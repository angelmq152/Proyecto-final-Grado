#!/bin/bash
set -e

echo "=== Instalando Docker en Debian ==="

apt-get update -q
apt-get install -y -q ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

usermod -aG docker angel || true

echo "=== Levantando contenedor Docker nginx ==="
cd /home/angel/futuraweb
docker compose up -d

echo ""
echo "============================================"
echo "  Contenedor Docker: http://localhost:8083"
echo "  Servidor nginx actual: http://localhost:8081"
echo "============================================"
