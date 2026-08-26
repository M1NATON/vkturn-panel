"""Автосоздание ВК-звонков через VK API calls.start —
тот же механизм, что у кнопки «Get VK call URL» в iOS-приложении.
Звонки, созданные через API, живут бессрочно даже пустыми.
"""
import json
import urllib.parse
import urllib.request

API_VERSION = "5.276"
HOSTS = ["api.vk.ru", "api.vk.com"]

# Тот же OAuth-флоу, что использует приложение (client_id веб-приложения ВК, scope=calls).
OAUTH_URL = (
    "https://oauth.vk.ru/authorize?client_id=6287487"
    "&scope=calls&response_type=token"
)


def create_call(access_token):
    """Создаёт звонок от аккаунта токена. Возвращает join_link. Бросает RuntimeError."""
    if not access_token:
        raise RuntimeError("Не задан vk_access_token (⚙️ Настройки)")
    last_err = "no hosts tried"
    for host in HOSTS:
        qs = urllib.parse.urlencode({"v": API_VERSION, "access_token": access_token})
        url = "https://" + host + "/method/calls.start?" + qs
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                obj = json.loads(r.read().decode())
        except Exception as e:
            last_err = "network: %s" % e
            continue
        if "error" in obj:
            err = obj["error"]
            raise RuntimeError("VK error %s: %s" % (err.get("error_code"), err.get("error_msg")))
        link = (obj.get("response") or {}).get("join_link")
        if not link:
            raise RuntimeError("VK вернул неожиданный ответ: %s" % str(obj)[:200])
        return link
    raise RuntimeError(last_err)


def ensure_links(cfg, save_cfg):
    """Свежий звонок первым в пуле, пул укорочен до target.
    Никогда не бросает исключения: сбой ВК не должен ломать выдачу доступа."""
    token = (cfg.get("vk_access_token") or "").strip()
    if not token:
        return None
    try:
        target = max(1, int(cfg.get("vk_links_target", 3)))
        links = cfg.get("vk_links") or []
        if isinstance(links, str):
            links = [links]
        fresh = create_call(token)
        if fresh not in links:
            links = [fresh] + links
        cfg["vk_links"] = links[:target]
        save_cfg(cfg)
        return fresh
    except Exception:
        return None


if __name__ == "__main__":
    # Ручной прогон: python3 vkcalls.py  (создать звонок и обновить пул)
    import core

    c = core.load_config()
    fresh = ensure_links(c, core.save_config)
    print(fresh or "не создан (нет токена или ошибка ВК)")
