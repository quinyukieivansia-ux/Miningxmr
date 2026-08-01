"""Telegram bot: pusat kendali mining.

Perintah:
  /start         - panel utama
  /deploy <n>    - buat n VPS baru (default 1)
  /status        - status semua VPS + hashrate
  /earnings      - estimasi pendapatan
  /balance       - saldo DOGE real-time (Unmineable)
  /workers       - daftar worker + hashrate (Unmineable)
  /restart <uuid> - restart VPS
  /stop <uuid>   - stop VPS
  /remove <uuid> - hapus VPS
  /help          - daftar perintah
"""
import asyncio
import logging
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

log = logging.getLogger(__name__)


def _fmt_servers(servers) -> str:
    if not servers:
        return "Belum ada VPS. Kirim /deploy 1"
    lines = []
    for s in servers:
        status = s.get("status", "?")
        ip = s.get("ip", "-")
        hr = s.get("hashrate_khs", 0)
        lines.append(
            f"• `{s.get('uuid', '')[:8]}` {s.get('worker','')} "
            f"[{status}] {ip} — {hr:.0f} KH/s"
        )
    return "\n".join(lines)


class MiningBot:
    def __init__(self, token: str, admin_chat_id: int, store, provisioner,
                 monitor, ssh_key_path: str, unmineable_api=None,
                 accounts=None):
        self.token = token
        self.admin_chat_id = admin_chat_id
        self.store = store
        self.provisioner = provisioner
        self.monitor = monitor
        self.ssh_key_path = ssh_key_path
        self.unmineable = unmineable_api
        self.accounts = accounts
        self.app = Application.builder().token(token).build()
        self._register_handlers()

    # ---------------- handlers ----------------
    def _register_handlers(self):
        a = self.app
        a.add_handler(CommandHandler("start", self.cmd_start))
        a.add_handler(CommandHandler("deploy", self.cmd_deploy))
        a.add_handler(CommandHandler("status", self.cmd_status))
        a.add_handler(CommandHandler("earnings", self.cmd_earnings))
        a.add_handler(CommandHandler("balance", self.cmd_balance))
        a.add_handler(CommandHandler("workers", self.cmd_workers))
        a.add_handler(CommandHandler("restart", self.cmd_restart))
        a.add_handler(CommandHandler("stop", self.cmd_stop))
        a.add_handler(CommandHandler("remove", self.cmd_remove))
        a.add_handler(CommandHandler("help", self.cmd_help))
        a.add_handler(CallbackQueryHandler(self.on_button))

    async def _guard(self, update: Update) -> bool:
        uid = update.effective_user.id if update.effective_user else None
        log.info("GUARD: uid=%s admin=%s", uid, self.admin_chat_id)
        if uid != self.admin_chat_id:
            await update.message.reply_text("Lu bukan admin. Pergi.")
            return False
        return True

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        log.info("START dipanggil oleh %s", update.effective_user.id if update.effective_user else None)
        if not await self._guard(update):
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Deploy VPS (1)", callback_data="deploy:1")],
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("💰 Pendapatan", callback_data="earnings")],
            [InlineKeyboardButton("👛 Saldo DOGE", callback_data="balance"),
             InlineKeyboardButton("⛏️ Workers", callback_data="workers")],
            [InlineKeyboardButton("🔄 Restart VPS", callback_data="restart"),
             InlineKeyboardButton("⏹️ Stop VPS", callback_data="stop")],
            [InlineKeyboardButton("🗑️ Hapus VPS", callback_data="remove")],
        ])
        try:
            await update.message.reply_text(
                "🤖 *Mining Control Center*\n\n"
                "📦 *Deploy:* /deploy 12\n"
                "📊 *Pantau:* /status /earnings\n"
                "👛 *Saldo:* /balance /workers\n"
                "⚙️ *Kelola:* /restart UUID /stop UUID /remove UUID\n\n"
                "_Ketujuh command di atas udah ready — tinggal isi credential (UpCloud + wallet)._",
                parse_mode="Markdown", reply_markup=kb,
            )
            log.info("START reply OK")
        except Exception as e:
            log.exception("START reply GAGAL: %s", e)

    async def cmd_deploy(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE, chat_id: int = None):
        log.info("DEPLOY dipanggil, args=%s", ctx.args)
        if update.effective_user:
            if not await self._guard(update):
                return
        chat_id = chat_id or update.effective_chat.id
        args = ctx.args
        count = int(args[0]) if args and args[0].isdigit() else 1
        clients = self.accounts.all() if self.accounts else []
        count = max(1, min(count, len(clients)))
        if count == 0:
            await ctx.bot.send_message(
                chat_id,
                "❌ Tidak ada akun UpCloud terkonfigurasi. "
                "Isi `upcloud.accounts` di config.json."
            )
            return
        msg = await ctx.bot.send_message(
            chat_id,
            f"⏳ Bikin {count} VPS ({self.provisioner.cores}-core/{self.provisioner.ram_gb}GB)...\n"
            f"Miner: XMRig RandomX ({self.provisioner.threads} threads)\n"
            f"Bisa makan 2-5 menit per VPS."
        )
        try:
            loop = asyncio.get_running_loop()
            created, ok = await loop.run_in_executor(
                None, self.provisioner.provision, count
            )
        except Exception as e:
            await msg.edit_text(f"❌ Gagal: {e}")
            return

        ok = [c for c in created if "uuid" in c]
        err = [c for c in created if "error" in c]
        text = f"✅ {len(ok)}/{count} VPS dibuat.\n\n" + _fmt_servers(self.store.list_servers())
        if err:
            text += "\n\n❌ Gagal:\n" + "\n".join(f"• {c['worker']}: {c['error']}" for c in err)
        await msg.edit_text(text, parse_mode="Markdown")

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE, chat_id: int = None):
        log.info("STATUS dipanggil")
        if update.effective_user:
            if not await self._guard(update):
                return
        chat_id = chat_id or (update.effective_chat.id if update.effective_chat else None)
        if not chat_id:
            return
        servers = self.store.list_servers()
        if not servers:
            await ctx.bot.send_message(chat_id, "Belum ada VPS. /deploy 1 dulu.")
            return
        msg = await ctx.bot.send_message(chat_id, "⏳ Cek status semua VPS...")
        loop = asyncio.get_running_loop()
        for s in servers:
            if s.get("ip"):
                try:
                    info = await loop.run_in_executor(
                        None, self.monitor.miner_status, s["ip"], self.ssh_key_path
                    )
                    s["status"] = info["status"]
                    s["hashrate_khs"] = info["hashrate_khs"]
                except Exception as e:
                    s["status"] = f"err:{e}"
        await msg.edit_text("📊 *Status VPS*\n\n" + _fmt_servers(servers),
                            parse_mode="Markdown")

    async def cmd_earnings(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE, chat_id: int = None):
        log.info("EARNINGS dipanggil")
        if update.effective_user:
            if not await self._guard(update):
                return
        chat_id = chat_id or (update.effective_chat.id if update.effective_chat else None)
        if not chat_id:
            return
        servers = self.store.list_servers()
        total_khs = sum(s.get("hashrate_khs", 0) for s in servers)
        est = self.monitor.estimate_daily_doge(total_khs)
        await ctx.bot.send_message(
            chat_id,
            "💰 *Pendapatan (estimasi kasar)*\n\n"
            f"Total hashrate: `{total_khs:.0f} KH/s`\n"
            f"Estimasi: `{est:.2f} DOGE/hari`\n\n"
            "_Angka ini estimasi lokal. Buat angka real, daftarkan worker di "
            "pool dan pakai API pool. Dan inget: CPU mining DOGE di cloud "
            "kemungkinan besar rugi dibanding biaya VPS._",
            parse_mode="Markdown",
        )

    async def cmd_remove(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._guard(update):
            return
        args = ctx.args
        if not args:
            await update.message.reply_text("Format: /remove <uuid>")
            return
        uuid = args[0]
        s = self.store.get(uuid)
        if not s:
            await update.message.reply_text("UUID ga ketemu. Cek /status")
            return
        await update.message.reply_text(f"⏳ Hapus {uuid}...")
        try:
            loop = asyncio.get_running_loop()
            # pakai akun pertama yang available buat hapus
            client = self.accounts.first() if self.accounts else None
            if not client:
                await update.message.reply_text("❌ Tidak ada akun UpCloud.")
                return
            await loop.run_in_executor(None, client.delete_server, uuid)
            self.store.remove_server(uuid)
            await update.message.reply_text(f"✅ {uuid} dihapus.")
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal hapus: {e}")

    # ---------------- fitur baru: balance / workers / restart / stop ----------------
    async def cmd_balance(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        log.info("BALANCE dipanggil")
        if not await self._guard(update):
            return
        if not self.unmineable:
            await update.message.reply_text("Wallet belum di-set di config. Isi `mining.wallet_address`.")
            return
        stats = self.unmineable.wallet_stats()
        if "error" in stats:
            await update.message.reply_text(f"❌ Gagal ambil saldo: {stats['error']}")
            return
        bal = stats.get("balance", 0)
        unpaid = stats.get("unpaid", 0)
        hr = stats.get("hashrate", 0)
        # konversi DOGE -> USD kasar (harga ~$0.15, bisa outdated)
        usd = (bal + unpaid) * 0.15
        await update.message.reply_text(
            "👛 *Saldo DOGE (Unmineable)*\n\n"
            f"• Balance: `{bal:.8f} DOGE`\n"
            f"• Unpaid: `{unpaid:.8f} DOGE`\n"
            f"• Total: `{bal + unpaid:.8f} DOGE` (~${usd:.2f})\n"
            f"• Hashrate: `{hr/1000:.2f} KH/s`\n\n"
            "_Data dari api.unmineable.com. Harga DOGE pake asumsi $0.15._",
            parse_mode="Markdown",
        )

    async def cmd_workers(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        log.info("WORKERS dipanggil")
        if not await self._guard(update):
            return
        if not self.unmineable:
            await update.message.reply_text("Wallet belum di-set di config.")
            return
        workers = self.unmineable.workers()
        if not workers:
            await update.message.reply_text("Belum ada worker aktif.")
            return
        lines = []
        for w in workers[:20]:
            key = w.get("key", "?")
            hr = w.get("hashrate", 0) / 1000  # H/s -> KH/s
            lines.append(f"• `{key}` — {hr:.2f} KH/s")
        await update.message.reply_text(
            "⛏️ *Worker Aktif (Unmineable)*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    async def _vps_action(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                          action: str):
        """Generic: /restart atau /stop VPS by UUID."""
        if not await self._guard(update):
            return
        args = ctx.args
        if not args:
            await update.message.reply_text(f"Format: /{action} <uuid>")
            return
        uuid = args[0]
        s = self.store.get(uuid)
        if not s:
            await update.message.reply_text("UUID ga ketemu. Cek /status")
            return
        await update.message.reply_text(f"⏳ {action.upper()} {uuid}...")
        try:
            loop = asyncio.get_running_loop()
            client = self.accounts.first() if self.accounts else None
            if not client:
                await update.message.reply_text("❌ Tidak ada akun UpCloud.")
                return
            if action == "restart":
                # UpCloud ga punya restart langsung: stop -> start
                await loop.run_in_executor(None, client.stop_server, uuid)
                await loop.run_in_executor(None, client.start_server, uuid)
            else:
                await loop.run_in_executor(None, client.stop_server, uuid)
            await update.message.reply_text(f"✅ {action.upper()} {uuid} sukses.")
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal {action}: {e}")

    async def cmd_restart(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await self._vps_action(update, ctx, "restart")

    async def cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await self._vps_action(update, ctx, "stop")

    # ---------------- alert & laporan harian ----------------
    async def alert_vps_down(self, server: dict, info: dict):
        """Kirim alert ke admin kalau VPS mati/error."""
        try:
            await self.app.bot.send_message(
                self.admin_chat_id,
                f"🚨 *ALERT: VPS Mati!*\n\n"
                f"• Worker: `{server.get('worker','?')}`\n"
                f"• UUID: `{server.get('uuid','')[:8]}`\n"
                f"• IP: `{server.get('ip','-')}`\n"
                f"• Status: `{info.get('status')}`\n"
                f"• Hashrate: `{info.get('hashrate_khs',0):.0f} KH/s`\n\n"
                f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"Balikin pake: `/restart {server.get('uuid','')[:8]}`",
                parse_mode="Markdown",
            )
        except Exception as e:
            log.exception("gagal kirim alert: %s", e)

    async def send_daily_report(self):
        """Laporan harian rekap."""
        servers = self.store.list_servers()
        total_khs = sum(s.get("hashrate_khs", 0) for s in servers)
        est = self.monitor.estimate_daily_doge(total_khs)
        active = sum(1 for s in servers if s.get("status") == "running")
        msg = (
            "📊 *Laporan Harian Mining*\n\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"• VPS aktif: `{active}/{len(servers)}`\n"
            f"• Total hashrate: `{total_khs:.0f} KH/s`\n"
            f"• Estimasi: `{est:.4f} DOGE/hari`\n\n"
        )
        if self.unmineable:
            stats = self.unmineable.wallet_stats()
            if "error" not in stats:
                msg += f"• Saldo: `{stats.get('balance',0):.8f} DOGE`\n"
        await self.app.bot.send_message(self.admin_chat_id, msg, parse_mode="Markdown")

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📖 *Perintah Mining Bot*\n\n"
            "/deploy N — bikin N VPS (1 per akun)\n"
            "/status — status + hashrate\n"
            "/earnings — estimasi pendapatan\n"
            "/balance — saldo DOGE (Unmineable)\n"
            "/workers — daftar worker\n"
            "/restart UUID — restart VPS\n"
            "/stop UUID — stop VPS\n"
            "/remove UUID — hapus VPS\n"
            "/help — ini",
            parse_mode="Markdown",
        )

    async def on_button(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""
        chat_id = q.message.chat_id if q.message else q.from_user.id
        log.info("BUTTON: %s dari %s", data, q.from_user.id if q.from_user else None)
        if data.startswith("deploy:"):
            n = int(data.split(":", 1)[1])
            ctx.args = [str(n)]
            await self.cmd_deploy(update, ctx, chat_id=chat_id)
        elif data == "status":
            await self.cmd_status(update, ctx, chat_id=chat_id)
        elif data == "earnings":
            await self.cmd_earnings(update, ctx, chat_id=chat_id)
        elif data == "balance":
            # tombol balance: panggil cmd_balance via send_message manual
            await self.cmd_balance(update, ctx)
        elif data == "workers":
            await self.cmd_workers(update, ctx)
        elif data == "restart":
            # prompt user: minta UUID
            await ctx.bot.send_message(
                chat_id, "Format: `/restart <UUID>`\nContoh: `/restart abcd1234`",
                parse_mode="Markdown")
        elif data == "stop":
            await ctx.bot.send_message(
                chat_id, "Format: `/stop <UUID>`\nContoh: `/stop abcd1234`",
                parse_mode="Markdown")
        elif data == "remove":
            await ctx.bot.send_message(
                chat_id, "Format: `/remove <UUID>`\nContoh: `/remove abcd1234`",
                parse_mode="Markdown")

    # ---------------- lifecycle ----------------
    async def run(self):
        # run_polling handle initialize + start + polling + idle sekaligus
        await self.app.run_polling(allowed_updates=Update.ALL_TYPES)
