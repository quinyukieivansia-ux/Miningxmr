# Fleet Monitor

Tool ringan untuk **kelola, monitor, dan deploy ke banyak VPS sekaligus** dari satu controller. Dibangun di atas Ansible (tanpa agent di sisi VPS — cukup SSH).

Fitur:
- 🖥️ **Dashboard web** real-time: CPU/RAM/disk/uptime semua VPS dalam satu layar
- 📈 **Grafik history**: tren RAM/disk/load per VPS dari waktu ke waktu
- 🔔 **Alert Telegram**: notif otomatis kalau VPS down / RAM-disk penuh
- ⚡ **Manage massal**: jalankan perintah & deploy script ke semua VPS sekaligus

---

## 1. Prasyarat

Di server controller (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y ansible sshpass python3
```

## 2. Setup

```bash
git clone <URL-REPO-KAMU> fleet
cd fleet

# Salin file contoh, lalu isi data asli
cp inventory.ini.example inventory.ini
cp alert_config.ini.example alert_config.ini

# Proteksi file berisi rahasia (WAJIB)
chmod 600 inventory.ini alert_config.ini
chmod +x fleet
```

## 3. Daftarkan VPS

Edit `inventory.ini`, isi daftar VPS di bawah `[workers]`:

```ini
[workers]
vps1  ansible_host=203.0.113.10  ansible_user=root  ansible_password='passVPS1'
vps2  ansible_host=203.0.113.11  ansible_user=root  ansible_password='passVPS2'
```

> 💡 **Lebih aman**: pakai SSH key, bukan password. Generate `ssh-keygen -t ed25519`, sebar `ssh-copy-id root@IP`, lalu hapus `ansible_password` dari inventory.

## 4. Setup alert Telegram (opsional)

1. Bikin bot di [@BotFather](https://t.me/BotFather) → dapat token
2. Ambil chat ID kamu (chat ke [@userinfobot](https://t.me/userinfobot))
3. Isi `alert_config.ini`:

```ini
[telegram]
bot_token = TOKEN_DARI_BOTFATHER
owner_id = CHAT_ID_KAMU
```

## 5. Pakai

```bash
./fleet ping              # tes koneksi semua VPS
./fleet list              # daftar VPS terdaftar
./fleet health            # ringkasan CPU/RAM/disk (teks)
./fleet run 'uptime'      # jalankan perintah di semua VPS
./fleet deploy x.sh       # kirim & jalankan script ke semua VPS
./fleet collect           # tarik metrik → JSON (buat dashboard)
./fleet dashboard         # jalankan dashboard web di :8080
```

Buka dashboard di browser: `http://IP-CONTROLLER:8080`

## 6. Otomatisasi (cron)

Biar data selalu fresh + alert jalan sendiri, tambah ke `crontab -e`:

```cron
*/5 * * * * cd /root/fleet && ./fleet collect >/dev/null 2>&1 && python3 fleet_history.py >/dev/null 2>&1 && python3 fleet_alert.py >/dev/null 2>&1
```

---

## ⚠️ Keamanan

File berikut **TIDAK** ikut ke Git (sudah diblokir `.gitignore`) karena berisi rahasia:

| File | Isi |
|------|-----|
| `inventory.ini` | IP + password VPS |
| `alert_config.ini` | token bot Telegram |
| `dashboard/data/*` | metrik internal |

**Jangan pernah** hapus baris-baris itu dari `.gitignore`. Selalu `chmod 600` file rahasia.

## Struktur

```
fleet/
├── fleet                      # wrapper perintah utama
├── inventory.ini              # daftar VPS (rahasia, tidak di-commit)
├── alert_config.ini           # config Telegram (rahasia, tidak di-commit)
├── ansible.cfg
├── playbooks/
│   ├── health.yml             # cek kesehatan
│   ├── run-command.yml        # jalankan perintah
│   ├── deploy-script.yml      # deploy script
│   └── collect-metrics.yml    # kumpulkan metrik
├── fleet_history.py           # simpan snapshot history
├── fleet_alert.py             # alert Telegram
└── dashboard/
    ├── index.html             # dashboard utama
    ├── history.html           # grafik tren
    └── data/                  # metrik & history (tidak di-commit)
```
