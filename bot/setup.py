"""Validation & setup: cek credential, generate SSH key, tes API, kirim report ke Telegram.

Bisa dipanggil manual: python -m bot.setup
Atau otomatis dipanggil bot pas /start (kalau belum ada config valid).
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def run_setup(config_path: str = "config.json"):
    """Jalankan semua validasi credential. Return dict dengan hasil & saran."""
    p = Path(config_path)
    if not p.exists():
        p = Path("config.json")
    cfg = json.loads(p.read_text())

    results = {}

    # === 1. Telegram ===
    tg = cfg.get("telegram", {})
    import requests
    try:
        r = requests.get(f"https://api.telegram.org/bot{tg['token']}/getMe", timeout=15)
        results["telegram"] = {"ok": r.json().get("ok"), "bot": r.json().get("result", {}).get("username")}
        if not r.json().get("ok"):
            results["telegram"]["error"] = "Token tidak valid"
    except Exception as e:
        results["telegram"] = {"ok": False, "error": str(e)}

    # === 2. UpCloud accounts ===
    accounts_valid = []
    for a in cfg.get("upcloud", {}).get("accounts", []):
        token = a.get("token", "")
        if not token or token.startswith("YOUR_"):
            continue
        try:
            r2 = requests.get(
                "https://api.upcloud.com/1.3/account",
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
            ok = r2.status_code == 200
            accounts_valid.append({
                "label": a.get("label", "?"),
                "ok": ok,
                "status": r2.status_code,
                "error": r2.json().get("error", {}).get("error_message", "") if not ok else "",
            })
        except Exception as e:
            accounts_valid.append({"label": a.get("label", "?"), "ok": False, "error": str(e)})
    results["upcloud_accounts"] = accounts_valid
    results["upcloud_total_valid"] = sum(1 for a in accounts_valid if a["ok"])

    # === 3. SSH key ===
    try:
        from .sshkeys import ensure_ssh_key
        key_path = cfg.get("paths", {}).get("ssh_key", "~/.ssh/mining_bot_rsa")
        pub = ensure_ssh_key(key_path)
        results["ssh_key"] = {"ok": True, "generated": True, "length": len(pub)}
    except Exception as e:
        results["ssh_key"] = {"ok": False, "error": str(e)}

    # === 4. Wallet DOGE ===
    wallet = cfg.get("mining", {}).get("wallet_address", "")
    results["wallet"] = {
        "ok": bool(wallet) and not wallet.startswith("YOUR_"),
        "address": wallet[:20] + "..." if wallet else "(belum diisi)",
    }

    # === 5. Pool connection ===
    try:
        r3 = requests.get("https://api.unmineable.com/v1/coin/DOGE/stats", timeout=15)
        results["pool"] = {"ok": r3.status_code == 200}
    except Exception:
        results["pool"] = {"ok": False}

    return results


def format_report(results: dict) -> str:
    """Format hasil validasi ke text buat Telegram."""
    lines = ["📋 *Laporan Validasi Sistem*\n"]

    # Telegram
    tg = results["telegram"]
    lines.append(f"🔵 Telegram: {'✅' if tg.get('ok') else '❌'} {tg.get('bot', tg.get('error', ''))}")

    # UpCloud
    uc = results.get("upcloud_accounts", [])
    total = len(uc)
    valid = results.get("upcloud_total_valid", 0)
    lines.append(f"🟢 UpCloud: {valid}/{total} akun valid")
    for a in uc:
        icon = "✅" if a["ok"] else "❌"
        lines.append(f"  {icon} {a['label']}: {a.get('status','')} {a.get('error','')}")

    # SSH
    ssh = results["ssh_key"]
    lines.append(f"🔑 SSH Key: {'✅' if ssh.get('ok') else '❌'} {ssh.get('length','')} chars")

    # Wallet
    w = results["wallet"]
    lines.append(f"👛 Wallet: {'✅' if w.get('ok') else '⚠️'} {w['address']}")

    # Pool
    pool = results["pool"]
    lines.append(f"⛏️ Pool (Unmineable): {'✅' if pool.get('ok') else '❌'}")

    # Summary
    all_ok = (
        tg.get("ok")
        and valid > 0
        and ssh.get("ok")
        and w.get("ok")
        and pool.get("ok")
    )
    lines.append(f"\n{'✅ SEMUA SIAP — ketik /deploy 1 buat mulai!' if all_ok else '⚠️ Ada yang perlu diisi. Cek /help'}")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run_setup(sys.argv[1] if len(sys.argv) > 1 else "config.json")
    print(json.dumps(results, indent=2, ensure_ascii=False))
