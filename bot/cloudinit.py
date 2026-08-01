"""Template cloud-init yang di-inject ke tiap VPS.

- Install XMRig (RandomX) untuk Unmineable, atau cpuminer (scrypt) untuk Zpool
- Resource cap: CPU 80% (max-threads-hint + CPUQuota), RAM 90% (MemoryMax)
- Auto-start mining via systemd dengan restart otomatis
- Laporan ke Telegram setelah boot
"""
import base64

# ---------- Unmineable: XMRig (RandomX) ----------
XM_RIG_CLOUD_INIT = r"""#cloud-config
package_update: true

packages:
  - git
  - build-essential
  - cmake
  - libuv1-dev
  - libssl-dev
  - libhwloc-dev
  - curl

runcmd:
  - git clone --depth=1 https://github.com/xmrig/xmrig.git /opt/xmrig
  - cd /opt/xmrig && mkdir -p build && cd build && cmake .. -DWITH_HWLOC=ON > /var/log/xmrig-cmake.log 2>&1 && make -j$(nproc) > /var/log/xmrig-make.log 2>&1
  - test -x /opt/xmrig/build/xmrig && echo XMRIG_BUILD_OK || echo XMRIG_BUILD_FAIL
  - |
    cat > /opt/xmrig/config.json <<'EOC'
    {{
        "autosave": true,
        "cpu": {{
            "enabled": true,
            "huge-pages": true,
            "hw-aes": null,
            "priority": null,
            "max-threads-hint": 80,
            "asm": true
        }},
        "pools": [
            {{
                "algo": "rx",
                "coin": null,
                "url": "rx.unmineable.com:3333",
                "user": "{WALLET}.{WORKER}",
                "pass": "x",
                "tls": false,
                "keepalive": true,
                "nicehash": false
            }}
        ],
        "api": {{
            "id": null,
            "worker-id": "{WORKER}",
            "enabled": true,
            "bind": ["0.0.0.0:8080"],
            "access-token": "seagull",
            "restricted": true
        }}
    }}
    EOC
  - |
    cat > /opt/start_miner.sh <<'EOF'
    #!/bin/bash
    exec /opt/xmrig/build/xmrig -c /opt/xmrig/config.json
    EOF
  - chmod +x /opt/start_miner.sh
  - |
    cat > /etc/systemd/system/miner.service <<'EOF'
    [Unit]
    Description=XMRig Unmineable
    After=network-online.target
    Wants=network-online.target
    [Service]
    Type=simple
    User=root
    WorkingDirectory=/opt
    ExecStart=/opt/start_miner.sh
    Restart=always
    RestartSec=15
    LimitNOFILE=65536
    MemoryMax=90%
    MemoryHigh=85%
    CPUQuota=80%
    [Install]
    WantedBy=multi-user.target
    EOF
  - systemctl daemon-reload
  - systemctl enable miner.service
  - systemctl start miner.service
  - |
    curl -s -X POST https://api.telegram.org/bot{BOT_TOKEN}/sendMessage \
      -d chat_id={CHAT_ID} \
      -d "text=✅ VPS $(hostname) online — XMRig starting (hashrate dalam 1-2 menit)" \
      -d parse_mode=HTML || true
"""

ZPOOL_CLOUD_INIT = r"""#cloud-config
package_update: true

packages:
  - git
  - build-essential
  - autoconf
  - automake
  - libtool
  - pkg-config
  - libssl-dev
  - libcurl4-openssl-dev
  - jq
  - curl

runcmd:
  - git clone --depth=1 https://github.com/tpruvot/cpuminer-multi.git /opt/cpuminer
  - cd /opt/cpuminer && ./build.sh > /var/log/cpuminer-build.log 2>&1 || true
  - test -x /opt/cpuminer/cpuminer && echo BUILD_OK || echo BUILD_FAIL
  - |
    cat > /opt/start_miner.sh <<'EOF'
    #!/bin/bash
    exec /opt/cpuminer/cpuminer -a {ALGO} \
      -o {POOL} \
      -u {WALLET}.{WORKER} \
      -p c=DOGE \
      --threads={THREADS} \
      --cpu-affinity=0xFFFFFFFF \
      --retries=9999 \
      --retry-pause=10
    EOF
  - chmod +x /opt/start_miner.sh
  - |
    cat > /etc/systemd/system/miner.service <<'EOF'
    [Unit]
    Description=cpuminer Zpool
    After=network-online.target
    Wants=network-online.target
    [Service]
    Type=simple
    User=root
    WorkingDirectory=/opt
    ExecStart=/opt/start_miner.sh
    Restart=always
    RestartSec=15
    LimitNOFILE=65536
    MemoryMax=90%
    MemoryHigh=85%
    CPUQuota=80%
    [Install]
    WantedBy=multi-user.target
    EOF
  - systemctl daemon-reload
  - systemctl enable miner.service
  - systemctl start miner.service
  - |
    curl -s -X POST https://api.telegram.org/bot{BOT_TOKEN}/sendMessage \
      -d chat_id={CHAT_ID} \
      -d "text=✅ VPS $(hostname) online — cpuminer ({ALGO}) starting" \
      -d parse_mode=HTML || true
"""


def build_cloud_init(*, pool: str, wallet: str, worker: str, threads: int,
                     bot_token: str, chat_id: str, algo: str = "rx") -> str:
    if algo == "rx":
        script = XM_RIG_CLOUD_INIT.format(
            WALLET=wallet, WORKER=worker, THREADS=threads,
            BOT_TOKEN=bot_token, CHAT_ID=chat_id,
        )
    else:
        script = ZPOOL_CLOUD_INIT.format(
            ALGO=algo, POOL=pool, WALLET=wallet, WORKER=worker, THREADS=threads,
            BOT_TOKEN=bot_token, CHAT_ID=chat_id,
        )
    return base64.b64encode(script.encode()).decode()
