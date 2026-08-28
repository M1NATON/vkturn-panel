#!/usr/bin/env bash
# VK TURN: установка панели и бота (без WireGuard и vk-turn-proxy).
# Для серверов, где серверная часть уже настроена (см. install-server.sh).
# Идемпотентен: существующий /opt/vkturn/config.json не трогает.
# Запускать от root.
set -euo pipefail

APP_DIR=/opt/vkturn
SRC_DIR=$(cd "$(dirname "$0")" && pwd)

step() { echo; echo "==> $1"; }

step "1/5 Проверки"

if [ "$EUID" -ne 0 ]; then
  echo "Запусти от root (или через sudo)"
  exit 1
fi

WARN=0
if ! command -v wg >/dev/null 2>&1; then
  echo "  предупреждение: wg не найден (WireGuard не установлен)"
  WARN=1
fi
if [ ! -f /etc/wireguard/wg0.conf ]; then
  echo "  предупреждение: нет /etc/wireguard/wg0.conf"
  WARN=1
fi
if ! systemctl cat vk-turn-proxy.service >/dev/null 2>&1; then
  echo "  предупреждение: нет vk-turn-proxy.service"
  WARN=1
fi
if [ "$WARN" -eq 1 ]; then
  echo "  Серверная часть не готова. На чистом VPS сначала запусти: bash install-server.sh"
  echo "  Панель и бот всё равно поставлю."
fi

step "2/5 Python и venv"
if ! command -v python3 >/dev/null 2>&1; then
  apt-get update && apt-get install -y python3
fi
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/venv" 2>/dev/null || {
    apt-get update && apt-get install -y python3-venv
    python3 -m venv "$APP_DIR/venv"
  }
fi

step "3/5 Файлы и конфиг"
mkdir -p "$APP_DIR"
cp "$SRC_DIR"/core.py "$SRC_DIR"/panel.py "$SRC_DIR"/bot.py "$SRC_DIR"/vkcalls.py "$SRC_DIR"/requirements.txt "$APP_DIR"/

if [ ! -f "$APP_DIR/config.json" ]; then
  cp "$SRC_DIR/config.json.example" "$APP_DIR/config.json"
  echo "  создан $APP_DIR/config.json"

  # server_public_key — публичный ключ из PrivateKey wg0.conf
  PRIV=""
  if [ -f /etc/wireguard/wg0.conf ] && command -v wg >/dev/null 2>&1; then
    PRIV=$(sed -n 's/^[[:space:]]*PrivateKey[[:space:]]*=[[:space:]]*//p' /etc/wireguard/wg0.conf | head -n1 || true)
    PRIV="${PRIV//[[:space:]]/}"
  fi
  if [ -n "$PRIV" ]; then
    if PUB=$(echo "$PRIV" | wg pubkey 2>/dev/null); then
      sed -i "s|\"server_public_key\": \"[^\"]*\"|\"server_public_key\": \"$PUB\"|" "$APP_DIR/config.json"
      echo "  server_public_key подставлен из wg0.conf"
    else
      echo "  предупреждение: не удалось посчитать публичный ключ — впиши server_public_key вручную"
    fi
  else
    echo "  предупреждение: PrivateKey в wg0.conf не найден — впиши server_public_key вручную"
  fi

  # peer_address — публичный IP + порт 56000
  IP=$(curl -fs4 --max-time 10 ifconfig.me 2>/dev/null || true)
  if [ -n "$IP" ]; then
    sed -i "s|\"peer_address\": \"[^\"]*\"|\"peer_address\": \"$IP:56000\"|" "$APP_DIR/config.json"
    echo "  peer_address подставлен: $IP:56000"
  else
    echo "  предупреждение: не удалось узнать публичный IP — впиши peer_address вручную"
  fi
else
  echo "  $APP_DIR/config.json уже есть — не трогаю"
fi

step "4/5 Python-зависимости"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

step "5/5 Systemd и запуск"
cat > /etc/systemd/system/vkturn-panel.service << EOF
[Unit]
Description=VK TURN Panel
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/panel.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/vkturn-bot.service << EOF
[Unit]
Description=VK TURN Bot
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vkturn-panel >/dev/null 2>&1
systemctl restart vkturn-panel
echo "  панель запущена"

BOT_TOKEN=$("$APP_DIR/venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("bot_token") or "")' "$APP_DIR/config.json" 2>/dev/null || true)
if [ -n "$BOT_TOKEN" ]; then
  systemctl enable vkturn-bot >/dev/null 2>&1
  systemctl restart vkturn-bot
  echo "  бот запущен"
else
  systemctl stop vkturn-bot >/dev/null 2>&1 || true
  echo "  бот не запущен: bot_token пуст."
  echo "  Когда впишешь токен: systemctl enable --now vkturn-bot"
fi

IP=$(curl -fs4 --max-time 10 ifconfig.me 2>/dev/null || echo "IP_СЕРВЕРА")

echo
echo "Готово. Установлено в $APP_DIR"
echo
echo "Дальше:"
echo "  1) nano $APP_DIR/config.json — задай panel_password (а если что-то не подставилось — проверь остальное)"
echo "  2) systemctl restart vkturn-panel vkturn-bot — после правки конфига"
echo
echo "Панель:  http://$IP:8808"
echo "Логи:    journalctl -u vkturn-panel -f   |   journalctl -u vkturn-bot -f"
