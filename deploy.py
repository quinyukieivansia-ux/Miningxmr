#!/usr/bin/env python3
"""Deployment: install deps, init config, buat systemd service, start."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kw)

def main():
    print("== Mining Bot Deploy ==")
    # 1. python deps
    run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])

    # 2. config
    cfg = ROOT / "config.json"
    if not cfg.exists():
        shutil.copy(ROOT / "config.example.json", cfg)
        print(f"[!] Edit dulu: {cfg} — isi token bot, chat id, API key UpCloud, wallet.")
        sys.exit(1)

    data = json.loads(cfg.read_text())
    if "YOUR_" in json.dumps(data):
        print("[!] Masih ada placeholder di config.json. Isi dulu.")
        sys.exit(1)

    # 3. systemd unit
    unit = f"""[Unit]
Description=Mining Bot Control Center
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={Path.home().name}
WorkingDirectory={ROOT}
ExecStart={sys.executable} -m bot.main
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    (ROOT / "mining-bot.service").write_text(unit)
    print(f"Unit: {ROOT / 'mining-bot.service'} — install dengan:")
    print(f"  sudo cp {ROOT / 'mining-bot.service'} /etc/systemd/system/")
    print("  sudo systemctl daemon-reload && sudo systemctl enable --now mining-bot")

if __name__ == "__main__":
    main()
