"""Monitoring: hashrate via SSH, status pool, pendapatan real-time Unmineable.

Unmineable API (tanpa API key, public):
  GET https://api.unmineable.com/v1/coin/{COIN}/wallet/{WALLET}
  -> { balance, unpaidBalance, ... }

  GET https://api.unmineable.com/v1/coin/{COIN}/wallet/{WALLET}/workers
  -> { workers: [{ key, hashrate, ... }] }
"""
import re
from datetime import datetime

import paramiko
import requests

UNMINEABLE_API = "https://api.unmineable.com/v1"


def _ssh_exec(host: str, key_path: str, command: str, timeout: int = 20):
    """Jalankan command di VPS via SSH, return (rc, stdout, stderr)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username="root", key_filename=key_path, timeout=timeout)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        rc = stdout.channel.recv_exit_status()
        return rc, stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")
    finally:
        client.close()


class UnmineableAPI:
    """Client API Unmineable — cek saldo & worker tanpa key."""

    def __init__(self, coin: str = "DOGE", wallet: str = None):
        self.coin = coin.upper()
        self.wallet = wallet

    def wallet_stats(self, wallet: str = None):
        """Saldo + stats wallet."""
        w = wallet or self.wallet
        if not w:
            return {"error": "wallet belum di-set"}
        try:
            r = requests.get(
                f"{UNMINEABLE_API}/coin/{self.coin}/wallet/{w}",
                timeout=15,
            )
            if r.status_code == 200:
                d = r.json().get("data", {})
                return {
                    "balance": d.get("balance", 0),
                    "unpaid": d.get("unpaidBalance", 0),
                    "total_hashes": d.get("totalHashes", 0),
                    "hashrate": d.get("hashrate", 0),
                    "source": "unmineable",
                }
            return {"error": f"HTTP {r.status_code}", "source": "unmineable"}
        except Exception as e:
            return {"error": str(e), "source": "unmineable"}

    def workers(self, wallet: str = None):
        """Daftar worker aktif + hashrate masing-masing."""
        w = wallet or self.wallet
        if not w:
            return []
        try:
            r = requests.get(
                f"{UNMINEABLE_API}/coin/{self.coin}/wallet/{w}/workers",
                timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("data", {}).get("workers", [])
        except Exception:
            pass
        return []


class MinerMonitor:
    """Wrapper monitor yang dipakai bot (biar interface konsisten)."""

    def miner_status(self, host: str, key_path: str) -> dict:
        """Cek status miner via SSH. Return dict berisi hashrate & status."""
        try:
            rc, out, err = _ssh_exec(
                host, key_path,
                "systemctl is-active miner.service; "
                "systemctl show miner.service -p ActiveEnterTimestamp --value; "
                "tail -n 200 /var/log/syslog 2>/dev/null | grep -i 'accepted\\|KH/s\\|MH/s\\|H/s' | tail -n 3",
            )
        except Exception as e:
            return {"status": "ssh_error", "hashrate_khs": 0.0, "error": str(e)}

        lines = out.strip().splitlines()
        active = lines[0].strip() if lines else "unknown"

        # parse hashrate dari output cpuminer/xmrig
        hashrate = 0.0
        for line in lines:
            m = re.search(r"([\d.]+)\s*(?:KH/s|MH/s|GH/s|H/s)", line)
            if m:
                val = float(m.group(1))
                unit = m.group(2)
                if "GH/s" in unit:
                    hashrate = val * 1_000_000
                elif "MH/s" in unit:
                    hashrate = val * 1000
                elif "KH/s" in unit:
                    hashrate = val
                else:
                    hashrate = val / 1000
                break

        if active != "active":
            return {"status": "stopped", "hashrate_khs": 0.0, "active": active}
        return {"status": "running", "hashrate_khs": hashrate, "active": active}

    def estimate_daily_doge(self, hashrate_khs: float) -> float:
        """Estimasi kasar pendapatan harian (DOGE)."""
        # RandomX DOGE via Unmineable: ~1.2x estimasi scrypt.
        # Angka ini kasar — API Unmineable jauh lebih akurat.
        difficulty = 15_000_000_000.0
        coin_per_block = 10_000.0
        seconds_per_day = 86400
        hashes_per_sec = hashrate_khs * 1000.0
        shares_per_day = (hashes_per_sec * seconds_per_day) / (difficulty * 2 ** 32)
        return shares_per_day * coin_per_block
