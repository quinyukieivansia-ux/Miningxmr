#!/usr/bin/env python3
"""
fleet_history.py - Simpan snapshot metrik ke history biar bisa dibuat grafik tren.
Baca dashboard/data/metrics.json, append ringkasan per host ke
dashboard/data/history.jsonl (satu baris JSON per snapshot).

Auto-trim: simpan maksimal MAX_POINTS snapshot terakhir per host biar file tidak membengkak.

Dipanggil setelah collect, mis. via cron:
    */5 * * * * cd /root/fleet && ./fleet collect && python3 fleet_history.py
"""
import os
import json
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS = os.path.join(HERE, "dashboard", "data", "metrics.json")
HISTORY = os.path.join(HERE, "dashboard", "data", "history.jsonl")
MAX_POINTS = 2016  # ~7 hari kalau interval 5 menit (12/jam * 24 * 7)


def main():
    if not os.path.exists(METRICS):
        print("metrics.json belum ada. Jalankan ./fleet collect dulu.")
        return

    data = json.load(open(METRICS))
    hosts = data.get("hosts", [])
    ts = int(time.time())

    # Susun satu snapshot ringkas
    snapshot = {
        "t": ts,
        "hosts": {}
    }
    for h in hosts:
        name = h.get("name", "?")
        snapshot["hosts"][name] = {
            "online": 1 if h.get("online") else 0,
            "ram": _num(h.get("ram_pct")),
            "disk": _num(str(h.get("disk_pct", "0")).rstrip("%")),
            "load": _num(h.get("load1")),
        }

    # Append snapshot
    with open(HISTORY, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    # Auto-trim: pertahankan MAX_POINTS baris terakhir
    _trim()
    print(f"Snapshot tersimpan ({len(hosts)} host) @ {ts}")


def _num(v):
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None


def _trim():
    if not os.path.exists(HISTORY):
        return
    with open(HISTORY) as f:
        lines = f.readlines()
    if len(lines) > MAX_POINTS:
        with open(HISTORY, "w") as f:
            f.writelines(lines[-MAX_POINTS:])


if __name__ == "__main__":
    main()
