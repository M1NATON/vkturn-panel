"""Мини-панель: дашборд, пользователи, QR, настройки, автосоздание звонков.

Разработчик: @M1NATON
"""
import functools
import hashlib
import io
import time
import urllib.parse

import qrcode
from flask import Flask, abort, redirect, render_template_string, request, send_file, session

import core
import vkcalls

app = Flask(__name__)


def cfg():
    return core.load_config()


def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if not session.get("ok"):
            return redirect("/login")
        return f(*a, **kw)
    return wrapper


STYLE = """
*{box-sizing:border-box}
body{background:#0f1115;color:#e6e8ee;font-family:-apple-system,'SF Pro Text',system-ui,sans-serif;margin:0;min-height:100vh}
.wrap{max-width:680px;margin:auto;padding:20px 16px 48px}
h1{font-size:22px;margin:6px 0 16px;display:flex;justify-content:space-between;align-items:center}
h1 a{font-size:13px;color:#9aa1b2;text-decoration:none;font-weight:400}
.card{background:#171a21;border:1px solid #262b36;border-radius:14px;padding:16px;margin:12px 0}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.stats{display:flex;gap:10px;margin:4px 0 14px}
.stat{flex:1;background:#171a21;border:1px solid #262b36;border-radius:14px;padding:12px;text-align:center}
.stat b{display:block;font-size:20px;margin-bottom:2px}
.stat span{color:#9aa1b2;font-size:12px}
.add{display:flex;gap:8px;margin:0 0 16px}
input,textarea{padding:12px;border-radius:10px;border:1px solid #303746;background:#0c0e12;color:#e6e8ee;font-size:15px;flex:1;outline:none}
input:focus,textarea:focus{border-color:#4a7dff}
button,.btn{background:#33507e;color:#fff;border:none;border-radius:10px;padding:11px 16px;font-size:14px;font-weight:600;text-decoration:none;display:inline-block;cursor:pointer;white-space:nowrap}
button:active,.btn:active{transform:scale(.97)}
button:hover,.btn:hover{background:#3d5c90}
.ghost{background:#22262f}
.ghost:hover{background:#2a2f3a}
.danger{background:#472a2d;color:#ff9a9a}
.danger:hover{background:#553035}
.ava{width:42px;height:42px;border-radius:50%;background:#26324b;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:17px;flex:none}
.name{font-weight:600;font-size:16px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#9aa1b2;font-size:13px}
.pill{font-size:12px;padding:3px 10px;border-radius:999px}
.on{background:#1c3328;color:#63d69a}
.off{color:#8a8f9c;background:#22262f}
.dim{color:#9aa1b2;font-size:13px;line-height:1.55}
.ok{background:#16301f;color:#7be3b0;padding:12px;border-radius:10px;font-size:13px;word-break:break-all;margin:8px 0}
.err{background:#371a1d;color:#ff9a9a;padding:12px;border-radius:10px;font-size:13px;word-break:break-all;margin:8px 0}
a{color:#6f9dff}
.login{display:flex;min-height:100vh;align-items:center;justify-content:center}
.login form{background:#171a21;border:1px solid #262b36;padding:30px;border-radius:16px;width:320px;text-align:center}
.login input,.login button{width:100%;margin-top:12px}
.qr{background:#fff;padding:14px;border-radius:16px;width:280px;height:280px;margin:10px auto;display:block}
textarea{width:100%;height:130px;font-size:12px;margin-top:12px}
"""

LOGIN_PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>VK TURN — вход</title><style>""" + STYLE + """</style></head><body class=login>
<form method=post>
<h2 style="margin:0 0 2px">VK TURN</h2>
<div class=dim>панель управления</div>
<input type=password name=password placeholder="Пароль" autofocus>
<button>Войти</button><div class=err>{{ error }}</div></form></body></html>"""

PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>VK TURN панель</title><style>""" + STYLE + """</style></head><body><div class=wrap>
<h1>VK TURN <a href="/settings">настройки</a></h1>
<div class=stats>
<div class=stat><b>{{ total }}</b><span>пользователей</span></div>
<div class=stat><b style="color:#63d69a">{{ online }}</b><span>онлайн</span></div>
<div class=stat><b>{{ traffic }}</b><span>трафик</span></div>
</div>
<form class=add method=post action="/add">
<input name=name placeholder="Имя пользователя" required>
<button>+ Добавить</button></form>
{% for p in peers %}
<div class=card>
<div class=row>
<div class=row style="gap:12px;flex-wrap:nowrap">
<div class=ava>{{ p.avatar }}</div>
<div><div class=name>{{ p.name or "без имени" }}</div>
<div class=mono>{{ p.ip }}</div></div>
</div>
<span class="pill {{ 'on' if p.online else 'off' }}">{{ 'онлайн' if p.online else p.ago }}</span>
</div>
<div class=dim style="margin:10px 0">{{ p.rx_mb }} МБ получено · {{ p.tx_mb }} МБ отправлено</div>
<div class=row>
{% if p.link %}<a class=btn href="/link/{{ p.ip }}">Ссылка + QR</a>{% else %}<span class=dim>ссылка не создана панелью</span>{% endif %}
<form method=post action="/revoke" onsubmit="return confirm('Отключить {{ p.name or p.ip }}?')" style="margin:0">
<input type=hidden name=ip value="{{ p.ip }}">
<button class=danger>Отключить</button></form>
</div></div>
{% else %}<div class=card dim>Пользователей пока нет — добавь первого выше.</div>{% endfor %}
<div class=dim style="margin-top:20px">Разработчик: @M1NATON</div>
</div></body></html>"""

LINK_PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Ссылка — {{ name }}</title><style>""" + STYLE + """</style></head><body><div class=wrap style="text-align:center">
<h1 style="justify-content:center">{{ name or "Пользователь" }}</h1>
<div class=dim>{{ ip }}</div>
<div class=card>
<div class=dim>Наведи камеру айфона на QR — или скопируй ссылку и вставь в приложении:<br>Settings → Import from connection link<br><br>Для надёжности создай свой вечный звонок: Settings → Use VK account (cookie) auth → Get VK call URL</div>
<img class=qr src="/qr/{{ ip }}.png" alt=qr>
<textarea readonly id=lnk onclick="this.select()">{{ link }}</textarea>
<button style="width:100%" onclick="navigator.clipboard.writeText(document.getElementById('lnk').value);this.textContent='Скопировано'">Скопировать ссылку</button>
</div>
<a class="btn ghost" href="/">← назад</a>
</div></body></html>"""

SETTINGS_PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Настройки</title><style>""" + STYLE + """</style></head><body><div class=wrap>
<h1>Настройки <a href="/">← назад</a></h1>
{% if ok %}<div class=ok>Звонок создан и стал первым в пуле:<br>{{ ok }}</div>{% endif %}
{% if err %}<div class=err>{{ err }}</div>{% endif %}
{% if saved %}<div class=ok>Сохранено.</div>{% endif %}
<div class=card>
<div class=name style="margin-bottom:6px">Автосоздание звонков</div>
<div class=dim style="margin-bottom:10px">С токеном панель сама создаёт свежий звонок при каждой выдаче доступа и держит пул из N последних ссылок. Руками править не нужно.</div>
<form method=post>
<div class=dim>VK access token — {{ "задан" if has_token else "не задан" }}</div>
<input type=password name=vk_access_token placeholder="vk1.a.… (пусто — не менять)" style="width:100%">
<div class=dim style="margin-top:12px">Размер пула звонков</div>
<input type=number name=vk_links_target value="{{ target }}" min=1 max=10 style="width:100%">
<div class=dim style="margin-top:12px">Адрес сервера для ссылок (IP:порт)</div>
<input name=peer_address value="{{ peer_address }}" style="width:100%">
<div class=dim style="margin-top:12px">Пул звонков (одна на строку; первая — основная)</div>
<textarea name=vk_links>{{ links }}</textarea>
<button style="width:100%">Сохранить</button>
</form>
<form method=post action="/calls/new" style="margin:8px 0 0">
<button class=ghost style="width:100%">Создать звонок сейчас</button>
</form>
</div>
<div class="card dim">
<b>Как получить токен (один раз, с айфона):</b><br>
1. В Safari войди в ВК под отдельным (burner) аккаунтом.<br>
2. Открой ссылку: <a href="{{ oauth_url }}">{{ oauth_url }}</a><br>
3. Нажми «Continue as» → после редиректа скопируй из адресной строки текст между <b>access_token=</b> и <b>&</b>.<br>
4. Вставь выше и сохрани. Токен живёт ~год; если создание перестанет работать — повтори.
</div>
</div></body></html>"""


def humanize(seconds):
    if seconds < 90:
        return "только что"
    if seconds < 3600:
        return f"{seconds // 60} мин. назад"
    if seconds < 86400:
        return f"{seconds // 3600} ч. назад"
    return f"{seconds // 86400} дн. назад"


def format_traffic(n):
    gb = n / 1e9
    return f"{gb:.1f} ГБ" if gb >= 0.1 else f"{round(n / 1e6)} МБ"


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == cfg()["panel_password"]:
            session["ok"] = True
            return redirect("/")
        error = "Неверный пароль"
    return render_template_string(LOGIN_PAGE, error=error)


@app.route("/")
@login_required
def index():
    peers = core.list_peers()
    now = int(time.time())
    online = 0
    total_bytes = 0
    for p in peers:
        hs = p.get("latest_handshake") or 0
        p["online"] = bool(hs) and (now - hs) < 300
        online += 1 if p["online"] else 0
        p["ago"] = humanize(now - hs) if hs else "не подключался"
        p["rx_mb"] = round((p.get("rx") or 0) / 1e6, 1)
        p["tx_mb"] = round((p.get("tx") or 0) / 1e6, 1)
        total_bytes += (p.get("rx") or 0) + (p.get("tx") or 0)
        name = (p.get("name") or "").strip()
        p["avatar"] = name[0].upper() if name else "?"
    return render_template_string(
        PAGE, peers=peers, total=len(peers), online=online,
        traffic=format_traffic(total_bytes),
    )


@app.route("/add", methods=["POST"])
@login_required
def add():
    name = request.form.get("name", "").strip() or "без имени"
    core.add_peer(name, created_by="panel")
    return redirect("/")


@app.route("/revoke", methods=["POST"])
@login_required
def revoke():
    try:
        core.remove_peer(request.form.get("ip", ""))
    except Exception as e:
        return f"Ошибка: {e}", 400
    return redirect("/")


@app.route("/qr/<ip>.png")
@login_required
def qr(ip):
    u = core.load_users().get(ip)
    if not u or not u.get("link"):
        abort(404)
    img = qrcode.make(u["link"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/link/<ip>")
@login_required
def link(ip):
    u = core.load_users().get(ip)
    if not u or not u.get("link"):
        abort(404)
    return render_template_string(LINK_PAGE, ip=ip, name=u.get("name", ""), link=u["link"])


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    c = core.load_config()
    saved = False
    if request.method == "POST":
        token = request.form.get("vk_access_token", "").strip()
        if token:
            c["vk_access_token"] = token
        try:
            c["vk_links_target"] = max(1, int(request.form.get("vk_links_target") or 3))
        except ValueError:
            pass
        c["peer_address"] = request.form.get("peer_address", "").strip()
        c["vk_links"] = [
            l.strip() for l in request.form.get("vk_links", "").splitlines() if l.strip()
        ]
        core.save_config(c)
        saved = True
    links = c.get("vk_links") or []
    if isinstance(links, str):
        links = [links]
    return render_template_string(
        SETTINGS_PAGE,
        has_token=bool((c.get("vk_access_token") or "").strip()),
        target=c.get("vk_links_target", 3),
        peer_address=c.get("peer_address", ""),
        links="\n".join(links),
        oauth_url=vkcalls.OAUTH_URL,
        ok=request.args.get("ok", ""),
        err=request.args.get("err", ""),
        saved=saved,
    )


@app.route("/calls/new", methods=["POST"])
@login_required
def new_call():
    c = core.load_config()
    try:
        fresh = vkcalls.create_call((c.get("vk_access_token") or "").strip())
        links = c.get("vk_links") or []
        if isinstance(links, str):
            links = [links]
        if fresh not in links:
            links = [fresh] + links
        c["vk_links"] = links[: max(1, int(c.get("vk_links_target", 3)))]
        core.save_config(c)
        return redirect("/settings?ok=" + urllib.parse.quote(fresh))
    except Exception as e:
        return redirect("/settings?err=" + urllib.parse.quote(str(e)))


if __name__ == "__main__":
    c = cfg()
    if not c.get("panel_password") or c["panel_password"] == "СМЕНИ_ПАРОЛЬ":
        print("=" * 60)
        print("ВНИМАНИЕ: panel_password не задан (стоит заглушка).")
        print("Задай его в config.json — иначе в панель войдёт кто угодно.")
        print("=" * 60)
    app.secret_key = hashlib.sha256(c["panel_password"].encode()).hexdigest()
    from waitress import serve
    serve(app, host="0.0.0.0", port=c.get("panel_port", 8808), threads=8)
