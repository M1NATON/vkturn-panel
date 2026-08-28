#!/usr/bin/env bash
# VK TURN: полная установка на чистый VPS одной командой.
# = install-server.sh (WireGuard + vk-turn-proxy) + install.sh (панель + бот).
# Запускать от root.
set -euo pipefail

DIR=$(cd "$(dirname "$0")" && pwd)

echo "==> Часть 1/2: серверная часть"
bash "$DIR/install-server.sh"

echo
echo "==> Часть 2/2: панель и бот"
bash "$DIR/install.sh"
