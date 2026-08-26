#!/usr/bin/env bash
# Установка панели и бота VK TURN. Запускать от root на сервере.
set -euo pipefail

APP_DIR=/opt/vkturn
SRC_DIR=$(cd "$(dirname "$0")" && pwd)

if [ "$EUID" -ne 0 ]; then
  echo "Запусти от root (или через sudo)"
  exit 1
fi

command -v wg >/dev/null || { echo "WireGuard не найден — сначала настрой wg0"; exit 1; }

if ! command -v python3 >/dev/null; then
  apt-get update && apt-get install -y python3
fi
python3 -m venv "$APP_DIR/venv" 2>/dev/null || {
  apt-get update && apt-get install -y python3-venv
  mkdir -p "$APP_DIR"
  python3 -m venv "$APP_DIR/venv"
}

mkdir -p "$APP_DIR"
cp "$SRC_DIR"/core.py "$SRC_DIR"/panel.py "$SRC_DIR"/bot.py "$SRC_DIR"/vkcalls.py "$SRC_DIR"/requirements.txt "$APP_DIR"/
[ -f "$APP_DIR/config.json" ] || cp "$SRC_DIR/config.json.example" "$APP_DIR/config.json"

"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

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
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

echo ""
echo "✅ Установлено в $APP_DIR"
echo ""
echo "Дальше:"
echo "  1) nano $APP_DIR/config.json   ← заполни свои значения"
echo "  2) systemctl enable --now vkturn-panel"
echo "  3) systemctl enable --now vkturn-bot   ← после того как впишешь bot_token"
eecho ""
echo "Панель: http://IP_СЕРВЕРА:8808 (пароль из config.json)"
