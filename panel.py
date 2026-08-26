"""Мини-панель: список пользователей, добавление, QR, удаление."""
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


LOGIN_PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>VK TURN — вход</title><style>
body{background:#0f1115;color:#e7e9ee;font-family:-apple-system,system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
form{background:#191d26;padding:28px;border-radius:16px;width:300px}
input,button{width:100%;box-sizing:border-box;padding:12px;border-radius:10px;border:1px solid #2a3040;background:#0f1115;color:#e7e9ee;font-size:16px;margin-top:12px}
button{background:#4f7cff;border:none;font-weight:600}
.err{color:#ff7a7a;font-size:14px}</style></head><body>
<form method=post><b>VK TURN панель</b>
<input type=password name=password placeholder="Пароль" autofocus>
<button>Войти</button><div class=err>{{ error }}</div></form></body></html>"""

PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>VK TURN панель</title><style>
body{background:#0f1115;color:#e7e9ee;font-family:-apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:640px;margin:auto}
h1{font-size:20px}
.card{background:#191d26;border-radius:14px;padding:14px;margin:10px 0}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.name{font-weight:600;font-size:16px}
.dim{color:#8b93a7;font-size:13px}
button,.btn{background:#4f7cff;color:#fff;border:none;border-radius:10px;padding:9px 14px;font-size:14px;font-weight:600;text-decoration:none;display:inline-block;cursor:pointer}
.danger{background:#3a2230;color:#ff8f8f}
input{padding:10px;border-radius:10px;border:1px solid #2a3040;background:#0f1115;color:#e7e9ee;font-size:15px;flex:1}
form.inline{display:inline}form.add{display:flex;gap:8px;margin:14px 0}
.dot{color:#59d499}.off{color:#5a6172}</style></head><body>
<h1>🛰 VK TURN панель <a href="/settings" style="font-size:13px;color:#8b93a7;font-weight:400">⚙️ настройки</a></h1>
<form class=add method=post action="/add">
<input name=name placeholder="Имя пользователя" required>
<button>+ Добавить</button></form>
{% for p in peers %}
<div class=card>
<div class=row>
<div><div class=name>{{ p.name or "без имени" }}</div>
<div class=dim>{{ p.ip }}</div></div>
<div class="dim {{ 'dot' if p.online else 'off' }}">{{ p.ago }}</div></div>
<div class="dim" style="margin:6px 0">⬇ {{ p.rx_mb }} МБ · ⬆ {{ p.tx_mb }} МБ</div>
<div class=row>
{% if p.link %}<a class=btn href="/link/{{ p.ip }}">Ссылка + QR</a>{% else %}<span class=dim>ссылка не создана панелью</span>{% endif %}
<form class=inline method=post action="/revoke" onsubmit="return confirm('Отключить {{ p.name or p.ip }}?')">
<input type=hidden name=ip value="{{ p.ip }}">
<button class=danger>Удалить</button></form>
</div></div>
{% else %}<div class=card dim>Пользователей пока нет</div>{% endfor %}
</body></html>"""

LINK_PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Ссылка — {{ name }}</title><style>
body{background:#0f1115;color:#e7e9ee;font-family:-apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:640px;margin:auto;text-align:center}
img{width:260px;height:260px;border-radius:12px;background:#fff;padding:10px}
textarea{width:100%;box-sizing:border-box;height:140px;border-radius:10px;border:1px solid #2a3040;background:#191d26;color:#e7e9ee;font-size:12px;padding:10px;margin-top:12px}
a.btn{color:#4f7cff;display:block;margin-top:14px}</style></head><body>
<h2>{{ name }} <span style="color:#8b93a7">{{ ip }}</span></h2>
<p style="color:#8b93a7;font-size:14px">QR — навести камерой айфона. Либо скопировать ссылку и в приложении: Settings → Import from connection link.</p>
<img src="/qr/{{ ip }}.png" alt=qr>
<textarea readonly onclick="this.select()">{{ link }}</textarea>
<a class=btn href="/">← назад</a></body></html>"""


SETTINGS_PAGE = """<!doctype html><html lang=ru><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Настройки</title><style>
body{background:#0f1115;color:#e7e9ee;font-family:-apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:640px;margin:auto}
.card{background:#191d26;border-radius:14px;padding:14px;margin:10px 0}
input,textarea{width:100%;box-sizing:border-box;padding:10px;border-radius:10px;border:1px solid #2a3040;background:#0f1115;color:#e7e9ee;font-size:14px;margin-top:6px}
textarea{height:110px;font-size:12px}
button,.btn{background:#4f7cff;color:#fff;border:none;border-radius:10px;padding:10px 16px;font-size:14px;font-weight:600;text-decoration:none;display:inline-block;cursor:pointer;margin-top:10px}
.dim{color:#8b93a7;font-size:13px;line-height:1.5}
.ok{background:#16352a;color:#7be3b0;padding:10px;border-radius:10px;font-size:13px;word-break:break-all;margin:8px 0}
.err{background:#3a2230;color:#ff8f8f;padding:10px;border-radius:10px;font-size:13px;word-break:break-all;margin:8px 0}
a{color:#4f7cff;word-break:break-all}</style></head><body>
<h1>⚙️ Настройки</h1>
{% if ok %}<div class=ok>Звонок создан и стал первым в пуле:<br>{{ ok }}</div>{% endif %}
{% if err %}<div class=err>{{ err }}</div>{% endif %}
{% if saved %}<div class=ok>Сохранено.</div>{% endif %}
<div class=card>
<b>Автосоздание звонков</b>
<div class=dim style="margin:6px 0">С токеном панель сама создаёт свежий звонок при каждой выдаче доступа и держит пул из N последних ссылок. Руками больше ничего править не надо.</div>
<form method=post>
<div class=dim>VK access token — {{ "задан ✅" if has_token else "НЕ задан ❌" }}</div>
<input type=password name=vk_access_token placeholder="vk1.a.… (пусто — не менять)">
<div class=dim style="margin-top:10px">Размер пула звонков</div>
<input type=number name=vk_links_target value="{{ target }}" min=1 max=10>
<div class=dim style="margin-top:10px">Адрес сервера для ссылок (IP:порт)</div>
<input name=peer_address value="{{ peer_address }}">
<div class=dim style="margin-top:10px">Пул звонков (одна ссылка на строку; первая — основная)</div>
<textarea name=vk_links>{{ links }}</textarea>
<button>Сохранить</button>
</form>
<form method=post action="/calls/new" style="margin-top:4px">
<button>📞 Создать звонок сейчас</button>
</form>
</div>
<div class=card dim>
<b>Как получить токен (один раз, с айфона):</b><br>
1. В Safari войди в ВК под отдельным (burner) аккаунтом.<br>
2. Открой ссылку: <a href="{{ oauth_url }}">{{ oauth_url }}</a><br>
3. Нажми «Continue as» → после редиректа скопируй из адресной строки текст между <b>access_token=</b> и <b>&</b>.<br>
4. Вставь выше и сохрани. Токен живёт ~год; если создание перестанет работать — повтори.
</div>
<a class=btn href="/">← назад</a></body></html>"""


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


def humanize(seconds):
    if seconds < 90:
        return "только что"
    if seconds < 3600:
        return f"{seconds // 60} мин. назад"
    if seconds < 86400:
        return f"{seconds // 3600} ч. назад"
    return f"{seconds // 86400} дн. назад"


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
    for p in peers:
        hs = p.get("latest_handshake") or 0
        p["online"] = bool(hs) and (now - hs) < 300
        p["ago"] = humanize(now - hs) if hs else "не подключался"
        p["rx_mb"] = round((p.get("rx") or 0) / 1e6, 1)
        p["tx_mb"] = round((p.get("tx") or 0) / 1e6, 1)
    return render_template_string(PAGE, peers=peers)


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


if __name__ == "__main__":
    c = cfg()
    app.secret_key = hashlib.sha256(c["panel_password"].encode()).hexdigest()
    app.run(host="0.0.0.0", port=c.get("panel_port", 8808))
