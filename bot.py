"""Telegram-бот v3: постоянная панель кнопок, QR по запросу, свои звонки юзеров."""
import io
import logging
import time

import qrcode
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import core
import vkcalls

logging.basicConfig(level=logging.INFO)

BTN_ACCESS = "🔑 Мой доступ"
BTN_HELP = "📱 Инструкция"
BTN_STATUS = "🔄 Мой статус"
BTN_ADMIN = "👑 Админка"

WELCOME = """
🛰 <b>VPN через ВК-звонки</b>

Работает, даже когда остальное заблокировано: трафик идёт через звонки VK.
Кнопки всегда внизу экрана 👇
"""

INSTRUCTION = """
📱 <b>Как подключиться:</b>

1. Установи <b>TestFlight</b> из App Store
2. Открой в нём ссылку и установи приложение: {tf}
3. Нажми «🔑 Мой доступ» внизу экрана и скопируй ссылку
4. В приложении: Settings → Import from connection link → вставь
5. Нажми <b>Connect</b>

🛡 <b>Создай свой звонок</b> (1 раз, живёт вечно):
6. В приложении: Settings → включи <b>Use VK account (cookie) auth</b> → войди в ВК
7. Нажми <b>Get VK call URL</b> — твой звонок встанет первым в списке

После этого ты работаешь через собственный звонок и ни от чего не зависишь.
"""


def cfg():
    return core.load_config()


def is_admin(user_id):
    return user_id in cfg().get("admin_ids", [])


def qr_bytes(link):
    img = qrcode.make(link)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def main_rkb(admin=False):
    rows = [[BTN_ACCESS], [BTN_HELP, BTN_STATUS]]
    if admin:
        rows.append([BTN_ADMIN])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton("📞 Добавить звонок", callback_data="a_addlink")],
        [InlineKeyboardButton("⚡ Авто-звонок (токен)", callback_data="a_newcall"),
         InlineKeyboardButton("📊 Статистика", callback_data="a_stats")],
    ])


def admin_back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← Админка", callback_data="a_menu")]])


def find_user(tg_id):
    for ip, u in core.load_users().items():
        if u.get("tg_id") == tg_id:
            return ip, u
    return None, None


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME, parse_mode="HTML",
        reply_markup=main_rkb(is_admin(update.effective_user.id)),
    )


async def do_access(reply, tg, ctx):
    """Выдача доступа. reply — callable для отправки ответа."""
    ip, u = find_user(tg.id)
    created = False
    if not u:
        try:
            res = core.add_peer(
                f"@{tg.username}" if tg.username else f"tg:{tg.id}", created_by="bot"
            )
        except Exception as e:
            await reply(f"Не получилось создать доступ: {e}")
            return
        users = core.load_users()
        users[res["ip"]]["tg_id"] = tg.id
        core.save_users(users)
        ip, link, created = res["ip"], res["link"], True
    else:
        link = u["link"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📷 Показать QR", callback_data=f"qr:{ip}"),
    ]])
    await reply(
        ("✅ <b>Доступ готов!</b>" if created else "У тебя уже есть доступ 👌")
        + "\n\nСкопируй ссылку и вставь в приложении: Settings → Import from connection link\n\n"
        + f"<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    if created:
        for admin in cfg().get("admin_ids", []):
            try:
                await ctx.bot.send_message(
                    admin,
                    f"🆕 Новый пользователь: @{tg.username or tg.id} → {ip}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Отключить", callback_data=f"revoke:{ip}")
                    ]]),
                )
            except Exception:
                pass


async def do_status(reply, tg):
    ip, u = find_user(tg.id)
    if not u:
        await reply("У тебя ещё нет доступа. Жми «🔑 Мой доступ» 👇")
        return
    peers = {p["ip"]: p for p in core.list_peers()}
    p = peers.get(ip, {})
    hs = p.get("latest_handshake") or 0
    online = bool(hs) and (time.time() - hs) < 300
    rx = round((p.get("rx") or 0) / 1e6, 1)
    tx = round((p.get("tx") or 0) / 1e6, 1)
    await reply(
        f"🔄 <b>Твой статус</b>\n\nIP: <code>{ip}</code>\n"
        f"Состояние: {'🟢 онлайн' if online else '⚪️ не в сети'}\n"
        f"Трафик: ⬇ {rx} МБ · ⬆ {tx} МБ",
        parse_mode="HTML",
    )


async def admin_users(q):
    peers = core.list_peers()
    if not peers:
        await q.edit_message_text("Пользователей нет", reply_markup=admin_back_kb())
        return
    rows = [
        [InlineKeyboardButton(
            f"❌ {p['ip']} — {p['name'] or 'без имени'}", callback_data=f"revoke:{p['ip']}"
        )]
        for p in peers
    ]
    rows.append([InlineKeyboardButton("← Админка", callback_data="a_menu")])
    await q.edit_message_text(
        "👥 <b>Пользователи</b>\nНажми на пользователя, чтобы отключить:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def admin_revoke(q, ip):
    try:
        core.remove_peer(ip)
        await q.edit_message_text(f"✅ {ip} отключён", reply_markup=admin_back_kb())
    except Exception as e:
        await q.edit_message_text(f"Ошибка: {e}", reply_markup=admin_back_kb())


async def admin_stats(q):
    peers = core.list_peers()
    now = time.time()
    online = sum(1 for p in peers if p.get("latest_handshake") and now - p["latest_handshake"] < 300)
    rx = sum(p.get("rx") or 0 for p in peers)
    tx = sum(p.get("tx") or 0 for p in peers)
    c = cfg()
    links = c.get("vk_links") or []
    n_links = len(links) if isinstance(links, list) else (1 if links else 0)
    has_token = bool((c.get("vk_access_token") or "").strip())
    await q.edit_message_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {len(peers)}\n"
        f"🟢 Онлайн сейчас: {online}\n"
        f"📦 Трафик суммарно: ⬇ {rx / 1e9:.1f} ГБ · ⬆ {tx / 1e9:.1f} ГБ\n"
        f"📞 Звонков в пуле: {n_links}\n"
        f"🔑 VK token: {'задан ✅' if has_token else 'не задан ❌'}",
        parse_mode="HTML",
        reply_markup=admin_back_kb(),
    )


async def admin_newcall(q):
    fresh = vkcalls.ensure_links(core.load_config(), core.save_config)
    if fresh:
        await q.edit_message_text(
            f"⚡ Звонок создан и стал первым в пуле:\n<code>{fresh}</code>",
            parse_mode="HTML",
            reply_markup=admin_back_kb(),
        )
    else:
        await q.edit_message_text(
            "Не получилось: нет vk_access_token или ошибка ВК.\n"
            "Можно и вручную — просто пришли ссылку на звонок в этот чат.",
            reply_markup=admin_back_kb(),
        )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    text = (update.message.text or "").strip()

    if text == BTN_ACCESS:
        await do_access(update.message.reply_text, tg, ctx)
        return
    if text == BTN_HELP:
        await update.message.reply_text(
            INSTRUCTION.format(tf=cfg().get("testflight_url", "")), parse_mode="HTML"
        )
        return
    if text == BTN_STATUS:
        await do_status(update.message.reply_text, tg)
        return
    if text == BTN_ADMIN:
        if is_admin(tg.id):
            await update.message.reply_text("👑 <b>Админка</b>", parse_mode="HTML", reply_markup=admin_kb())
        return

    # Админ прислал ссылку на звонок — добавить в пул
    if is_admin(tg.id):
        link = core.normalize_call_link(text)
        if link:
            n, refreshed = core.add_link_to_pool(link)
            await update.message.reply_text(
                f"📞 Звонок добавлен первым в пул (всего {n}).\n"
                f"Ссылки {refreshed} пользователей обновлены под новый пул — "
                f"им достаточно переимпортировать ссылку в один тап.",
                reply_markup=admin_back_kb(),
            )
            return

    await update.message.reply_text("Жми кнопки внизу 👇", reply_markup=main_rkb(is_admin(tg.id)))


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    tg = q.from_user

    if data.startswith("qr:"):
        ip = data.split(":", 1)[1]
        my_ip, u = find_user(tg.id)
        if ip != my_ip and not is_admin(tg.id):
            await q.answer("Недоступно", show_alert=True)
            return
        entry = u if ip == my_ip else core.load_users().get(ip, {})
        link = (entry or {}).get("link")
        if not link:
            await q.answer("Ссылка не найдена", show_alert=True)
            return
        await q.message.reply_photo(
            qr_bytes(link),
            caption="Наведи камеру айфона 📷",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑 Скрыть QR", callback_data="qr_del")
            ]]),
        )
        return

    if data == "qr_del":
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    if data == "help_i":
        await q.message.reply_text(
            INSTRUCTION.format(tf=cfg().get("testflight_url", "")), parse_mode="HTML"
        )
        return

    if not is_admin(tg.id):
        return
    if data == "a_menu":
        await q.edit_message_text("👑 <b>Админка</b>", parse_mode="HTML", reply_markup=admin_kb())
    elif data == "a_users":
        await admin_users(q)
    elif data == "a_stats":
        await admin_stats(q)
    elif data == "a_newcall":
        await admin_newcall(q)
    elif data == "a_addlink":
        await q.edit_message_text(
            "📞 Просто пришли в этот чат ссылку на звонок (vk.ru/call/join/…).\n"
            "Добавлю её первой в пул и обновлю сохранённые ссылки всех пользователей.",
            reply_markup=admin_back_kb(),
        )
    elif data.startswith("revoke:"):
        await admin_revoke(q, data.split(":", 1)[1])


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("👑 <b>Админка</b>", parse_mode="HTML", reply_markup=admin_kb())


async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    peers = core.list_peers()
    if not peers:
        await update.message.reply_text("Пользователей нет")
        return
    lines = [f"{p['ip']} — {p['name'] or 'без имени'}" for p in peers]
    await update.message.reply_text("👥 Пользователи:\n" + "\n".join(lines))


async def cmd_revoke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("Формат: /revoke 10.8.0.5")
        return
    ip = ctx.args[0]
    try:
        core.remove_peer(ip)
        await update.message.reply_text(f"✅ {ip} отключён")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


def main():
    token = cfg().get("bot_token", "")
    if not token:
        raise SystemExit("Заполни bot_token в config.json")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
