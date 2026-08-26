"""Общая логика: ключи WireGuard, правка wg0.conf, генерация ссылок vkturnproxy://"""
import base64
import fcntl
import json
import os
import re
import subprocess
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("VKTURN_CONFIG", os.path.join(BASE_DIR, "config.json"))
USERS_PATH = os.path.join(BASE_DIR, "users.json")
LOCK_PATH = os.path.join(BASE_DIR, ".lock")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


@contextmanager
def locked():
    with open(LOCK_PATH, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def run(cmd):
    return subprocess.run(
        cmd, shell=True, check=True, capture_output=True, text=True,
        executable="/bin/bash",
    ).stdout.strip()


def wg_genkey():
    priv = run("wg genkey")
    pub = run(f"echo '{priv}' | wg pubkey")
    return priv, pub


def read_conf(path):
    with open(path) as f:
        return f.read()


def write_conf(path, text):
    with open(path, "w") as f:
        f.write(text)


def parse_peers(conf_text):
    peers = []
    for block in re.split(r"\n\s*\n", conf_text):
        if "[Peer]" not in block:
            continue
        name_m = re.search(r"#\s*user:\s*(.+)", block)
        pub_m = re.search(r"PublicKey\s*=\s*(\S+)", block)
        ip_m = re.search(r"AllowedIPs\s*=\s*(\S+)", block)
        if pub_m and ip_m:
            peers.append({
                "name": name_m.group(1).strip() if name_m else "",
                "public_key": pub_m.group(1),
                "allowed_ip": ip_m.group(1),
            })
    return peers


def next_ip(conf_text, subnet):
    used = {int(m) for m in re.findall(re.escape(subnet) + r"\.(\d+)", conf_text)}
    for i in range(2, 255):
        if i not in used:
            return f"{subnet}.{i}"
    raise RuntimeError("Подсеть туннеля заполнена")


def syncconf(cfg):
    run(f"wg syncconf {cfg['wg_interface']} <(wg-quick strip {cfg['wg_interface']})")


def vk_links_value(cfg):
    """Один или несколько звонков. Несколько ссылок = запас: если одна сломается,
    приложение продолжит работать через остальные. Формат приложения — one per line."""
    links = cfg.get("vk_links")
    if isinstance(links, list) and links:
        return "\n".join(links)
    return cfg.get("vk_link", "")


def build_link(cfg, private_key, tunnel_address):
    payload = {
        "settings": {
            "dnsServers": cfg["dns_servers"],
            "numConnections": cfg["num_connections"],
            "peerAddress": cfg["peer_address"],
            "peerPublicKey": cfg["server_public_key"],
            "presharedKey": "",
            "privateKey": private_key,
            "tunnelAddress": tunnel_address,
            "useDTLS": True,
            "useSrtp": cfg.get("use_srtp", True),
            "useUDP": False,
            "useWrap": False,
            "useWrapA": False,
            "vkLink": vk_links_value(cfg),
            "wrapKeyHex": "",
        },
        "type": "connection",
        "version": 1,
    }
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return f"vkturnproxy://import?data={data}"


def load_users():
    if os.path.exists(USERS_PATH):
        with open(USERS_PATH) as f:
            return json.load(f)
    return {}


def save_users(users):
    with open(USERS_PATH, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def add_peer(name, created_by="panel"):
    cfg = load_config()
    try:
        import vkcalls
        vkcalls.ensure_links(cfg, save_config)
    except Exception:
        pass  # сбой ВК не должен ломать выдачу доступа
    with locked():
        conf_text = read_conf(cfg["wg_conf"])
        ip = next_ip(conf_text, cfg["subnet"])
        priv, pub = wg_genkey()
        block = f"\n# user: {name}\n[Peer]\nPublicKey = {pub}\nAllowedIPs = {ip}/32\n"
        write_conf(cfg["wg_conf"], conf_text.rstrip() + "\n" + block)
        syncconf(cfg)
        link = build_link(cfg, priv, f"{ip}/{cfg.get('subnet_mask', 24)}")
        users = load_users()
        users[ip] = {
            "name": name, "public_key": pub, "link": link,
            "created_by": created_by, "created_at": int(__import__("time").time()),
        }
        save_users(users)
        return {"ip": ip, "public_key": pub, "link": link, "name": name}


def remove_peer(ip):
    cfg = load_config()
    with locked():
        conf_text = read_conf(cfg["wg_conf"])
        pattern = re.compile(
            r"\n?# user:[^\n]*\n\[Peer\]\n(?:[^\n]*\n)*?AllowedIPs\s*=\s*"
            + re.escape(ip) + r"/32\s*\n?"
        )
        new_text, n = pattern.subn("\n", conf_text)
        if n == 0:
            raise RuntimeError(f"Пир {ip} не найден в конфиге")
        write_conf(cfg["wg_conf"], new_text)
        syncconf(cfg)
        users = load_users()
        users.pop(ip, None)
        save_users(users)


def wg_stats(cfg):
    try:
        out = run(f"wg show {cfg['wg_interface']} dump")
    except Exception:
        return {}
    stats = {}
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 7:
            stats[parts[0]] = {
                "latest_handshake": int(parts[4]),
                "rx": int(parts[5]),
                "tx": int(parts[6]),
            }
    return stats


def list_peers():
    cfg = load_config()
    peers = parse_peers(read_conf(cfg["wg_conf"]))
    stats = wg_stats(cfg)
    users = load_users()
    for p in peers:
        ip = p["allowed_ip"].split("/")[0]
        p["ip"] = ip
        u = users.get(ip, {})
        if not p["name"]:
            p["name"] = u.get("name", "")
        p["link"] = u.get("link", "")
        s = stats.get(p["public_key"], {})
        p["latest_handshake"] = s.get("latest_handshake", 0)
        p["rx"] = s.get("rx", 0)
        p["tx"] = s.get("tx", 0)
    return peers
