"""Telegram-бот: пользователи сами получают ссылки по /start, админ управляет."""
import io
import logging

import qrcode
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import core

logging.basicConfig(level=logging.INFO)

INSTRUCTION = """
📱 Как подключиться:
1. Установи TestFlight из App Store
2. Открой в нём ссылку и установи приложение: {tf}
3. Скопируй ссылку ниже, в приложении: Settings → Import from connection link → вставь
4. Нажми Connect

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


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    users = core.load_users()
    for ip, u in users.items():
        if u.get("tg_id") == tg.id:
            await update.message.reply_text(
                "У тебя уже есть доступ. Твоя ссылка:\n\n`" + u["link"] + "`",
                parse_mode="Markdown",
            )
            await update.message.reply_photo(qr_bytes(u["link"]))
            return
    try:
        res = core.add_peer(f"@{tg.username}" if tg.username else f"tg:{tg.id}", created_by="bot")
    except Exception as e:
        await update.message.reply_text(f"Не получилось создать доступ: {e}")
        return
    users = core.load_users()
    users[res["ip"]]["tg_id"] = tg.id
    core.save_users(users)
    await update.message.reply_text(
        INSTRUCTION.format(tf=cfg().get("testflight_url", ""))
        + "\nТвоя ссылка:\n\n`" + res["link"] + "`",
        parse_mode="Markdown",
    )
    await update.message.reply_photo(qr_bytes(res["link"]))
    for admin in cfg().get("admin_ids", []):
        try:
            await ctx.bot.send_message(
                admin, f"🆕 Новый пользователь: @{tg.username or tg.id} → {res['ip']}"
            )
        except Exception:
            pass


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
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.run_polling()


if __name__ == "__main__":
    main()
