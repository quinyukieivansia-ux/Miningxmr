# MiningXMR Bot 🤖⛏️

Bot Telegram untuk auto-provision VPS UpCloud + auto-install XMRig + mining DOGE via Unmineable.

## Fitur
- 🚀 **Auto-deploy VPS** — `/deploy 3` bikin 3 VPS 12-core/24GB di 3 akun trial UpCloud
- ⛏️ **Auto-install XMRig** — cloud-init otomatis pas VPS nyala
- 🔒 **Resource cap** — CPU 80%, RAM 90% (systemd + XMRig config)
- 👛 **Cek saldo DOGE** — `/balance` real-time dari Unmineable API
- 📊 **Monitoring** — `/status` hashrate, `/workers` daftar worker
- 🔔 **Alert VPS mati** — auto-cek tiap 5 menit + notifikasi ke Telegram
- 📈 **Laporan harian** — rekap otomatis jam 8 pagi
- 🎛️ **Kontrol penuh** — `/restart`, `/stop`, `/remove` dari chat

## Arsitektur
```
Telegram Bot (Control Center)
    ↓
Provisioning Engine (multi-account UpCloud)
    ↓
Cloud-init → XMRig (RandomX)
    ↓
Unmineable Pool → Payout DOGE
```

## Quick Start

### 1. Clone
```bash
git clone https://github.com/quinyukieivansia-ux/Miningxmr
cd Miningxmr
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Konfigurasi
Copy config:
```bash
cp config.example.json config.json
```

Isi `config.json`:
```json
{
  "telegram": {
    "token": "YOUR_BOT_TOKEN",
    "admin_chat_id": 123456789
  },
  "upcloud": {
    "accounts": [
      {"label": "utama", "token": "YOUR_UPCLOUD_API_TOKEN"}
    ]
  },
  "mining": {
    "wallet_address": "DOGE:YOUR_WALLET",
    "coin": "DOGE"
  }
}
```

### 4. Run
```bash
# PM2 (recommended)
pm2 start ecosystem.config.js

# atau langsung
python3 run.py
```

## Struktur Project
```
bot/
├── main.py          # Entry point
├── telegram_bot.py  # Handler command Telegram
├── upcloud.py       # Client API UpCloud (multi-account)
├── provisioner.py   # Orkestrasi provisioning
├── cloudinit.py     # Template cloud-init (XMRig + Zpool)
├── monitor.py       # Unmineable API + SSH monitoring
├── watcher.py       # Alert VPS mati + laporan harian
├── sshkeys.py       # Auto-generate SSH key
├── setup.py         # Validasi credential
├── storage.py       # Persistensi data (JSON)
└── webhook_app.py   # Opsional: webhook mode
```

## Command Bot
| Command | Fungsi |
|---------|--------|
| `/start` | Panel utama (7 tombol) |
| `/deploy N` | Bikin N VPS (1 per akun) |
| `/status` | Status + hashrate semua VPS |
| `/earnings` | Estimasi pendapatan |
| `/balance` | Saldo DOGE real-time |
| `/workers` | Daftar worker Unmineable |
| `/restart UUID` | Restart VPS |
| `/stop UUID` | Stop VPS |
| `/remove UUID` | Hapus VPS |
| `/setup` | Cek status credential |

## Disclaimer
Mining CPU di VPS cloud kemungkinan besar **tidak profitable** — biaya VPS > hasil mining. Project ini untuk edukasi & eksperimen otomasi DevOps.
