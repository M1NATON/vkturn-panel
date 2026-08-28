#!/usr/bin/env bash
# VK TURN: серверная часть — WireGuard (wg0) + vk-turn-proxy (SRTP-форк anton48).
# Для чистого VPS. Идемпотентен: существующие wg0.conf и vk-turn-proxy.service не трогает.
# Панель и бот этот скрипт НЕ ставит — для них install.sh.
# Запускать от root.
set -euo pipefail

step() { echo; echo "==> $1"; }

if [ "$EUID" -ne 0 ]; then
  echo "Запусти от root (или через sudo)"
  exit 1
fi

step "1/3 WireGuard"
if [ -f /etc/wireguard/wg0.conf ]; then
  echo "  /etc/wireguard/wg0.conf уже есть — пропускаю"
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y wireguard curl iptables

  IFACE=$(ip route show default | sed -n 's/.*dev \([^ ]*\).*/\1/p' | head -n1 || true)
  IFACE=${IFACE:-eth0}
  echo "  внешний интерфейс: $IFACE"

  mkdir -p /etc/wireguard
  PRIV=$(wg genkey)

  cat > /etc/wireguard/wg0.conf << EOF
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = $PRIV
PostUp = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o $IFACE -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o $IFACE -j MASQUERADE
EOF
  chmod 600 /etc/wireguard/wg0.conf

  echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-vkturn.conf
  sysctl -p /etc/sysctl.d/99-vkturn.conf >/dev/null

  systemctl enable --now wg-quick@wg0
  echo "  wg0 поднят: 10.8.0.1/24, порт 51820"
fi

step "2/3 vk-turn-proxy"
if systemctl cat vk-turn-proxy.service >/dev/null 2>&1; then
  echo "  vk-turn-proxy.service уже есть — пропускаю"
else
  # curl нужен и когда WG-шаг был пропущен (уже стоял)
  if ! command -v curl >/dev/null 2>&1; then
    apt-get update && apt-get install -y curl
  fi

  if [ ! -x /opt/vk-turn-proxy/server ]; then
    case "$(uname -m)" in
      x86_64)  ARCH=amd64 ;;
      aarch64) ARCH=arm64 ;;
      *) echo "Архитектура $(uname -m) не поддерживается (нужны x86_64 или aarch64)"; exit 1 ;;
    esac

    echo "  ищу asset server-linux-$ARCH в последнем релизе..."
    URL=$(curl -fsSL https://api.github.com/repos/anton48/vk-turn-proxy/releases/latest \
      | grep -o "\"browser_download_url\":[[:space:]]*\"[^\"]*/server-linux-$ARCH\"" \
      | head -n1 | cut -d'"' -f4 || true)

    if [ -z "${URL:-}" ]; then
      echo "Не нашёл asset server-linux-$ARCH в последнем релизе."
      echo "Скачай вручную:"
      echo "  1) открой https://github.com/anton48/vk-turn-proxy/releases/latest"
      echo "  2) скачай server-linux-$ARCH"
      echo "  3) положи его в /opt/vk-turn-proxy/server и сделай chmod +x"
      echo "  4) запусти этот скрипт ещё раз — он подхватит бинарник и создаст сервис"
      exit 1
    fi

    mkdir -p /opt/vk-turn-proxy
    curl -fsSL "$URL" -o /opt/vk-turn-proxy/server
    chmod +x /opt/vk-turn-proxy/server
    echo "  скачан: $URL"
  fi

  cat > /etc/systemd/system/vk-turn-proxy.service << 'EOF'
[Unit]
Description=VK TURN Proxy
After=network.target

[Service]
ExecStart=/opt/vk-turn-proxy/server -listen 0.0.0.0:56000 -connect 127.0.0.1:51820 -srtp
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now vk-turn-proxy
  echo "  vk-turn-proxy запущен: 0.0.0.0:56000/udp -> 127.0.0.1:51820 (srtp)"
fi

step "3/3 Файрвол"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 56000/udp >/dev/null
  echo "  ufw: разрешён 56000/udp"
else
  echo "  ufw не активен — пропускаю"
fi

echo
echo "Готово. Серверная часть стоит."
echo "Дальше — панель и бот:  bash install.sh"
