"""Entry point mining bot — multi-account.

Pake run_polling langsung + apscheduler buat watcher.
"""
import json
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update

from .monitor import MinerMonitor, UnmineableAPI
from .provisioner import Provisioner
from .storage import Store
from .telegram_bot import MiningBot
from .upcloud import Accounts
from .watcher import MinerWatcher

log = logging.getLogger(__name__)


def load_config(path: str = "config.json") -> dict:
    p = Path(path)
    if not p.exists():
        p = Path("config.example.json")
    return json.loads(p.read_text())


def _check_wrapper(w: MinerWatcher):
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(w._check_all())
    loop.close()


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.json")

    tg = cfg["telegram"]
    mn = cfg["mining"]
    sc = cfg["scaling"]
    vs = cfg.get("vps_specs", {})
    paths = cfg["paths"]

    # multi-account
    accounts = Accounts(cfg["upcloud"]["accounts"])

    store = Store(paths["data_dir"])

    provisioner = Provisioner(
        store=store,
        accounts=accounts,
        ssh_key_path=paths["ssh_key"],
        bot_token=tg["token"],
        chat_id=tg["admin_chat_id"],
        pool=mn["pool_address"],
        wallet=mn["wallet_address"],
        algo=mn.get("algorithm", "rx"),
        zone=vs.get("zone", "sg-sin1"),
        cores=vs.get("cores", 4),
        ram_gb=vs.get("ram_gb", 8),
        threads=vs.get("threads", 3),
    )

    monitor = MinerMonitor()
    unmineable = UnmineableAPI(coin=mn.get("coin", "DOGE"),
                               wallet=mn["wallet_address"])

    bot = MiningBot(
        token=tg["token"],
        admin_chat_id=tg["admin_chat_id"],
        store=store,
        provisioner=provisioner,
        accounts=accounts,
        monitor=monitor,
        ssh_key_path=paths["ssh_key"],
        unmineable_api=unmineable,
    )

    # watcher via scheduler
    w = MinerWatcher(
        bot=bot, store=store, monitor=monitor,
        ssh_key_path=paths["ssh_key"],
        check_interval=sc.get("check_interval", 300),
        daily_report_hour=8,
    )
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: _check_wrapper(w), "interval",
                      seconds=w.check_interval, id="watcher", replace_existing=True)
    scheduler.start()
    log.info("Scheduler watcher dimulai (interval=%ds)", w.check_interval)

    log.info("Akun UpCloud: %d", len(accounts))
    bot.app.run_polling(allowed_updates=["message", "callback_query"])
    scheduler.shutdown()


if __name__ == "__main__":
    main()
