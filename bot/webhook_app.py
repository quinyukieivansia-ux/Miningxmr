"""Webhook-based mining bot — stable, no polling loop issues.

Pakai Flask sebagai webhook receiver + ngrok untuk expose ke internet.
Telegram mengirim update langsung ke webhook → handler jalan.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from flask import Flask, request

from .monitor import MinerMonitor, UnmineableAPI
from .provisioner import Provisioner
from .storage import Store
from .telegram_bot import MiningBot
from .upcloud import UpCloudClient
from .watcher import MinerWatcher

from telegram import Update
from telegram.ext import Application

log = logging.getLogger(__name__)

flask_app = Flask(__name__)

# global state — diinisialisasi di main
bot = None
tg_app = None
watcher = None
monitor = None
store = None
cfg = None


@flask_app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    if token != cfg["telegram"]["token"][-16:]:
        return "nope", 403
    data = request.get_json(force=True)
    update = Update.de_json(data, tg_app.bot)
    asyncio.run_coroutine_threadsafe(
        tg_app.update_queue.put(update),
        tg_app.loop,
    )
    return "ok", 200


def _set_webhook():
    """Set webhook ke ngrok URL."""
    import requests
    # ambil ngrok URL
    r = requests.get("http://localhost:4040/api/tunnels", timeout=10)
    tunnels = r.json().get("tunnels", [])
    public_url = next((t["public_url"] for t in tunnels if t["proto"] == "https"), None)
    if not public_url:
        log.error("ngrok tunnel tidak ditemukan")
        return
    wh_url = f"{public_url}/webhook/{cfg['telegram']['token'][-16:]}"
    r2 = requests.get(
        f"https://api.telegram.org/bot{cfg['telegram']['token']}/setWebhook",
        params={"url": wh_url, "drop_pending_updates": True},
        timeout=15,
    )
    log.info("webhook set: %s -> %s", wh_url, r2.json())


def start_ngrok():
    """Start ngrok di background."""
    import subprocess
    proc = subprocess.Popen(
        ["ngrok", "http", "8080", "--log=stdout"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import time
    time.sleep(3)
    return proc


def start_watcher():
    """Jalankan watcher dalam thread executor."""
    import asyncio
    loop = asyncio.new_event_loop()

    async def run_watcher():
        # dikit delay biar bot ready
        await asyncio.sleep(10)
        while True:
            try:
                await watcher._check_all()
            except Exception:
                pass
            await asyncio.sleep(watcher.check_interval)

    import threading
    t = threading.Thread(target=lambda: loop.run_until_complete(run_watcher()), daemon=True)
    t.start()


def main():
    global bot, tg_app, watcher, monitor, store, cfg

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # load config
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    p = Path(config_path)
    if not p.exists():
        p = Path("config.json")
    cfg = json.loads(p.read_text())

    tg = cfg["telegram"]
    uc = cfg["upcloud"]
    mn = cfg["mining"]
    sc = cfg["scaling"]
    paths = cfg["paths"]

    store = Store(paths["data_dir"])

    def client_factory():
        return UpCloudClient(uc["username"], uc["password"])

    provisioner = Provisioner(
        store=store,
        ssh_key_path=paths["ssh_key"],
        bot_token=tg["token"],
        chat_id=tg["admin_chat_id"],
        pool=mn["pool_address"],
        wallet=mn["wallet_address"],
        algo=mn.get("algorithm", "rx"),
        threads=mn.get("threads", 16),
    )
    provisioner.client_factory = client_factory

    monitor = MinerMonitor()
    unmineable = UnmineableAPI(coin=mn.get("coin", "DOGE"), wallet=mn["wallet_address"])

    bot = MiningBot(
        token=tg["token"],
        admin_chat_id=tg["admin_chat_id"],
        store=store,
        provisioner=provisioner,
        monitor=monitor,
        ssh_key_path=paths["ssh_key"],
        unmineable_api=unmineable,
    )

    tg_app = bot.app

    watcher = MinerWatcher(
        bot=bot,
        store=store,
        monitor=monitor,
        ssh_key_path=paths["ssh_key"],
        check_interval=sc.get("check_interval", 300),
        daily_report_hour=8,
    )

    # start ngrok + webhook + watcher
    ngrok_proc = start_ngrok()
    _set_webhook()
    start_watcher()

    log.info("Flask webhook mulai di :8080 — bot online!")
    flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

    ngrok_proc.terminate()


if __name__ == "__main__":
    main()
