#!/usr/bin/env python3
"""
fleet_alert.py - Kirim alert Telegram kalau ada VPS bermasalah.
Baca dashboard/data/metrics.json, bandingkan dengan threshold di alert_config.ini.
Hanya kirim notif saat status BERUBAH (biar tidak spam).

Dipanggil setelah collect, mis. via cron:
    */5 * * * * cd /root/fleet && ./fleet collect && python3 fleet_alert.py
"""
import os
import json
import configparser
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "alert_config.ini")
METRICS = os.path.join(HERE, "dashboard", "data", "metrics.json")
STATE = os.path.join(HERE, ".alert_state.json")


def load_cfg():
    c = configparser.ConfigParser()
    c.read(CFG)
    return c


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "fleet-alert/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:
        print(f"Gagal kirim Telegram: {e}")
        return False


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            return {}
    return {}


def save_state(s):
    json.dump(s, open(STATE, "w"))


def check():
    cfg = load_cfg()
    token = cfg.get("telegram", "bot_token", fallback="").strip()
    chat_id = cfg.get("telegram", "owner_id", fallback="").strip()
    if not token or not chat_id:
        print("Token/owner_id belum diisi di alert_config.ini")
        return

    ram_max = cfg.getfloat("thresholds", "ram_pct", fallback=90)
    disk_max = cfg.getfloat("thresholds", "disk_pct", fallback=90)
    load_max = cfg.getfloat("thresholds", "load_per_core", fallback=2.0)

    if not os.path.exists(METRICS):
        print("metrics.json belum ada. Jalankan ./fleet collect dulu.")
        return

    data = json.load(open(METRICS))
    hosts = data.get("hosts", [])
    state = load_state()
    new_state = {}
    alerts = []

    for h in hosts:
        name = h.get("name", "?")
        problems = []

        if not h.get("online", False):
            problems.append("🔴 OFFLINE / unreachable")
        else:
            try:
                ram = float(h.get("ram_pct", 0) or 0)
                if ram >= ram_max:
                    problems.append(f"RAM tinggi: {ram:.0f}%")
            except ValueError:
                pass
            try:
                disk = float(str(h.get("disk_pct", "0")).rstrip("%") or 0)
                if disk >= disk_max:
                    problems.append(f"Disk hampir penuh: {disk:.0f}%")
            except ValueError:
                pass
            try:
                vcpus = float(h.get("vcpus", 1) or 1)
                load1 = float(h.get("load1", 0) or 0)
                per_core = load1 / max(vcpus, 1)
                if per_core >= load_max:
                    problems.append(f"Load tinggi: {load1} ({per_core:.1f}/core)")
            except ValueError:
                pass

        status_key = "|".join(problems) if problems else "ok"
        new_state[name] = status_key

        # Kirim alert hanya kalau status berubah dari sebelumnya
        prev = state.get(name, "ok")
        if problems and status_key != prev:
            alerts.append(f"⚠️ <b>{name}</b> ({h.get('ip','?')})\n   " + "\n   ".join(problems))
        elif not problems and prev != "ok":
            alerts.append(f"✅ <b>{name}</b> kembali normal")

    if alerts:
        msg = "🖥️ <b>Fleet Alert</b>\n\n" + "\n\n".join(alerts)
        if send_telegram(token, chat_id, msg):
            print(f"Alert terkirim: {len(alerts)} perubahan")
        else:
            print("Alert gagal terkirim")
    else:
        print("Semua normal, tidak ada alert.")

    save_state(new_state)


if __name__ == "__main__":
    check()
