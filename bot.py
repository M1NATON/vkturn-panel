"""Telegram-бот v2: кнопочный интерфейс для пользователей и админа."""
import io
import logging
import time

import qrcode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import core
import vkcalls

logging.basicConfig(level=logging.INFO)

WELCOME = """
🛰 <b>VPN через ВК-звонки</b>

Работает, даже когда остальное заблокировано: трафик идёт через звонки VK.
Жми кнопку ниже 👇
"""

INSTRUCTION = """
📱 <b>Как подключиться:</b>

1. Установи <b>TestFlight</b> из App Store
2. Открой в нём ссылку и установи приложение: {tf}
3. Вернись сюда и нажми «🔑 Мой доступ»
4. Скопируй ссылку, в приложении: Settings → Import from connection link → вставь
5. Нажми <b>Connect</b>

Или просто наведи камеру айфона на QR-код.
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


def user_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Мой доступ", callback_data="get")],
        [InlineKeyboardButton("📱 Инструкция", callback_data="help"),
         InlineKeyboardButton("🔄 Мой статус", callback_data="status")],
    ])


def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← Меню", callback_data="menu")]])


def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton("📞 Создать звонок", callback_data="a_newcall"),
         InlineKeyboardButton("📊 Статистика", callback_data="a_stats")],
    ])


def admin_back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← Админка", callback_data="a_menu")]])


def find_user(tg_id):
    for ip, u in core.load_users().items():
        if u.get("tg_id") == tg.id:
            return ip, u
    return None, None


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode="HTML", reply_markup=user_kb())


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


async def give_access(q, ctx):
    tg = q.from_user
    ip, u = find_user(tg.id)
    created = False
    if not u:
        try:
            res = core.add_peer(
                f"@{tg.username}" if tg.username else f"tg:{tg.id}", created_by="bot"
            )
        except Exception as e:
            await q.edit_message_text(f"Не получилось создать доступ: {e}", reply_markup=back_kb())
            return
        users = core.load_users()
        users[res["ip"]]["tg_id"] = tg.id
        core.save_users(users)
        ip, link, created = res["ip"], res["link"], True
    else:
        link = u["link"]
    await q.edit_message_text(
        ("✅ <b>Доступ готов!</b>" if created else "У тебя уже есть доступ 👌")
        + "\n\nСсылка ниже — скопируй её в приложение (Settings → Import from connection link):",
        parse_mode="HTML",
    )
    await q.message.reply_text(f"<code>{link}</code>", parse_mode="HTML", reply_markup=back_kb())
    await q.message.reply_photo(qr_bytes(link))
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


async def show_status(q):
    ip, u = find_user(q.from_user.id)
    if not u:
        await q.edit_message_text(
            "У тебя ещё нет доступа. Жми «🔑 Мой доступ» 👇", reply_markup=user_kb()
        )
        return
    peers = {p["ip"]: p for p in core.list_peers()}
    p = peers.get(ip, {})
    hs = p.get("latest_handshake") or 0
    online = bool(hs) and (time.time() - hs) < 300
    rx = round((p.get("rx") or 0) / 1e6, 1)
    tx = round((p.get("tx") or 0) / 1e6, 1)
    await q.edit_message_text(
        f"🔄 <b>Твой статус</b>\n\nIP: <code>{ip}</code>\n"
        f"Состояние: {'🟢 онлайн' if online else '⚪️ не в сети'}\n"
        f"Трафик: ⬇ {rx} МБ · ⬆ {tx} МБ",
        parse_mode="HTML",
        reply_markup=back_kb(),
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
            f"📞 Звонок создан и стал первым в пуле:\n<code>{fresh}</code>",
            parse_mode="HTML",
            reply_markup=admin_back_kb(),
        )
    else:
        await q.edit_message_text(
            "Не получилось: нет vk_access_token или ошибка ВК.", reply_markup=admin_back_kb()
        )


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    tg = q.from_user

    if data == "menu":
        await q.edit_message_text(WELCOME, parse_mode="HTML", reply_markup=user_kb())
    elif data == "help":
        await q.edit_message_text(
            INSTRUCTION.format(tf=cfg().get("testflight_url", "")),
            parse_mode="HTML",
            reply_markup=back_kb(),
        )
    elif data == "status":
        await show_status(q)
    elif data == "get":
        await give_access(q, ctx)
    elif data == "a_menu" and is_admin(tg.id):
        await q.edit_message_text("👑 <b>Админка</b>", parse_mode="HTML", reply_markup=admin_kb())
    elif data == "a_users" and is_admin(tg.id):
        await admin_users(q)
    elif data == "a_stats" and is_admin(tg.id):
        await admin_stats(q)
    elif data == "a_newcall" and is_admin(tg.id):
        await admin_newcall(q)
    elif data.startswith("revoke:") and is_admin(tg.id):
        await admin_revoke(q, data.split(":", 1)[1])


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
    app.run_polling()


if __name__ == "__main__":
    main()
