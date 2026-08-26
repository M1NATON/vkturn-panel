# VK TURN Panel + Bot

Мини-панель и Telegram-бот для выдачи доступов к VPN через ВК-звонки
(vk-turn-proxy + WireGuard). Работает поверх существующей установки:
панель/бот просто добавляют и удаляют `[Peer]`-блоки в `/etc/wireguard/wg0.conf`
и генерируют ссылки `vkturnproxy://` для iOS-приложения.

## Установка (на сервере, от root)

```bash
unzip vkturn-panel.zip
cd vkturn-panel
bash install.sh
```

## Настройка

```bash
nano /opt/vkturn/config.json
```

Заполнить:

| Поле | Где взять |
|---|---|
| `peer_address` | Публичный IP сервера + порт из `systemctl cat vk-turn-proxy.service` (флаг `-listen`), например `1.2.3.4:56000` |
| `vk_links` | Ссылки на ВК-звонки (массив, 1–3 шт.) — из приложения на айфоне. Несколько ссылок = запас: если один звонок умрёт, пользователи продолжат работать через остальные |
| `server_public_key` | Уже заполнен твоим значением |
| `panel_password` | Придумай пароль для входа в панель |
| `bot_token` | У @BotFather в Telegram (для бота) |
| `admin_ids` | Твой Telegram ID (узнать: @userinfobot), например `[123456789]` |
| `testflight_url` | Публичная TestFlight-ссылка приложения (уже заполнена) |
| `vk_access_token` | Токен ВК для автосоздания звонков — можно не трогать файл и вставить через панель (⚙️ Настройки) |

## Запуск

```bash
systemctl enable --now vkturn-panel   # панель: http://IP:8808
systemctl enable --now vkturn-bot     # бот (после bot_token)
ufw allow 8808                        # если включён ufw
```

## Использование

- **Панель** (для себя): `http://IP:8808` → пароль → «+ Добавить» → «Ссылка + QR».
- **Бот** (для пользователей): человек пишет боту `/start` → получает ссылку,
  QR и инструкцию. Тебе приходит уведомление.
- Команды админа в боте: `/users` — список, `/revoke 10.8.0.5` — отключить.

## Автоматика звонков (без ручных ссылок)

Панель сама создаёт ВК-звонки через VK API (`calls.start`) — тот же механизм,
что у кнопки «Get VK call URL» в приложении. Бонус: звонки, созданные через
API, живут бессрочно, а созданные руками в браузере с августа 2026 умирают,
как только создатель выходит из звонка.

Разовая настройка (2 минуты с айфона):

1. В Safari войди в ВК под отдельным (burner) аккаунтом.
2. Открой `https://oauth.vk.ru/authorize?client_id=6287487&scope=calls&response_type=token`
   и подтверди «Continue as».
3. После редиректа скопируй из адресной строки текст между `access_token=` и `&`.
4. В панели: ⚙️ Настройки → вставь токен → Сохранить.

Дальше всё само: при каждой выдаче доступа (панель или бот) создаётся свежий
звонок, он становится первым в пуле, а весь пул (по умолчанию 3 ссылки)
вшивается в ссылку пользователя. Если один звонок умрёт — работают остальные.

Токен живёт ~год. Если автосоздание перестанет работать (⚙️ → «Создать звонок
сейчас» покажет ошибку) — повтори шаги 1–4.

## Заметки

- Панель работает по HTTP с паролем — для круга друзей ок. Не публикуй адрес.
- Логи: `journalctl -u vkturn-panel -f` / `journalctl -u vkturn-bot -f`.
- Файл `/opt/vkturn/users.json` — база выданных доступов, не удаляй.

## Обновление через git

Код живёт в приватном репозитории: https://github.com/M1NATON/vkturn-panel

```bash
# первый раз на сервере
git clone https://github.com/M1NATON/vkturn-panel.git ~/vkturn-panel
cd ~/vkturn-panel && bash install.sh

# обновления
cd ~/vkturn-panel && git pull && bash install.sh
systemctl restart vkturn-panel vkturn-bot
```

`install.sh` не трогает существующий `/opt/vkturn/config.json` — настройки
переживают обновления. Так как репозиторий приватный, на сервере нужен доступ:
проще всего personal access token (read-only, Settings → Developer settings →
Tokens) прямо в URL:
`git clone https://<TOKEN>@github.com/M1NATON/vkturn-panel.git`
