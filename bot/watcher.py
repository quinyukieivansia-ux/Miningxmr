"""Watcher background: alert VPS mati + laporan harian otomatis.

- Tiap N menit: cek status semua VPS via SSH. Kalau ada yang mati/error
  -> kirim alert ke Telegram.
- Tiap jam tertentu: kirim laporan rekap (hashrate + pendapatan).
"""
import asyncio
import logging
from datetime import datetime

log = logging.getLogger(__name__)


class MinerWatcher:
    def __init__(self, bot, store, monitor, ssh_key_path: str,
                 check_interval: int = 300,
                 daily_report_hour: int = 8):
        self.bot = bot
        self.store = store
        self.monitor = monitor
        self.ssh_key_path = ssh_key_path
        self.check_interval = check_interval
        self.daily_report_hour = daily_report_hour
        self._last_report_day = None

    async def run(self):
        """Loop utama watcher (jalan parallel dengan bot polling)."""
        while True:
            try:
                await self._check_all()
            except Exception as e:
                log.exception("watcher check error: %s", e)
            await asyncio.sleep(self.check_interval)

    async def _check_all(self):
        servers = self.store.list_servers()
        if not servers:
            return

        # cek status tiap VPS via SSH (non-blocking via executor)
        loop = asyncio.get_running_loop()
        for s in servers:
            if not s.get("ip"):
                continue
            try:
                info = await loop.run_in_executor(
                    None, self.monitor.miner_status, s["ip"], self.ssh_key_path
                )
                prev = s.get("status")
                s["status"] = info["status"]
                s["hashrate_khs"] = info.get("hashrate_khs", 0)

                # alert kalau sebelumnya ok -> sekarang mati/error
                if info["status"] in ("stopped", "ssh_error"):
                    if prev in ("running", "starting", None):
                        await self.bot.alert_vps_down(s, info)
            except Exception as e:
                log.warning("gagal cek %s: %s", s.get("ip"), e)

        # laporan harian
        now = datetime.now()
        if now.hour == self.daily_report_hour and self._last_report_day != now.date():
            self._last_report_day = now.date()
            await self.bot.send_daily_report()
