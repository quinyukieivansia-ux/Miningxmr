"""Orkestrasi provisioning multi-account.

Tiap akun UpCloud trial maks 12 core + 24 GB RAM.
Strategi default: tiap akun 1 VPS 4-core/8GB, 3 thread XMRig (75% usage).
Kalau ada 3 akun = 3 VPS = total 12-core/24GB — optimal trial.
"""
import logging

log = logging.getLogger(__name__)


class Provisioner:
    def __init__(self, store, accounts, ssh_key_path: str, bot_token: str,
                 chat_id: int, pool: str, wallet: str, algo: str = "rx",
                 zone: str = "sg-sin1", cores: int = 4, ram_gb: int = 8,
                 threads: int = 3):
        self.store = store
        self.accounts = accounts  # Accounts instance
        self.ssh_key_path = ssh_key_path
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.pool = pool
        self.wallet = wallet
        self.algo = algo
        self.zone = zone
        self.cores = cores
        self.ram_gb = ram_gb
        self.threads = threads

    def _ssh_key(self) -> str:
        """Ambil public key SSH, generate otomatis kalau belum ada."""
        from .sshkeys import ensure_ssh_key
        return ensure_ssh_key(self.ssh_key_path)

    def provision(self, count: int = 1):
        """Bikin `count` VPS, distribusi round-robin ke semua akun.

        Tiap akun cuma bisa 1 VPS dengan spec trial (kalau spec > 6 core).
        Kalau count > jumlah akun → VPS tambahan gagal (trial limit).
        """
        from .cloudinit import build_cloud_init

        clients = self.accounts.all()
        if not clients:
            raise RuntimeError("Tidak ada akun UpCloud yang terkonfigurasi")

        spec = f"{self.cores}xCPU-{self.ram_gb}GB"
        created = []
        success = 0
        worker_base = len(self.store.list_servers())

        for i in range(count):
            client = clients[i % len(clients)]
            worker = f"w{worker_base + i}"
            cloud_init = build_cloud_init(
                pool=self.pool, wallet=self.wallet, worker=worker,
                threads=self.threads, bot_token=self.bot_token,
                chat_id=self.chat_id, algo=self.algo,
            )
            try:
                plan = client.pick_plan(self.cores, self.ram_gb)
                tmpl = client.ubuntu_template("22.04")
                ssh_key = self._ssh_key()
                srv = client.create_server(
                    title=f"mining-{worker}",
                    hostname=f"mining-{worker}",
                    zone=self.zone,
                    plan=plan["name"],
                    template_uuid=tmpl["uuid"],
                    ssh_key=ssh_key,
                    cloud_init_b64=cloud_init,
                )
                ip = ""
                try:
                    ip = srv["ip_addresses"]["ip_address"][0]["address"]
                except Exception:
                    pass
                rec = {
                    "uuid": srv["uuid"], "title": srv.get("title", ""),
                    "worker": worker, "ip": ip, "status": "starting",
                    "account": client.label, "spec": spec,
                    "created_at": srv.get("created", ""),
                }
                self.store.add_server(rec)
                created.append(rec)
                success += 1
                log.info("VPS dibuat: %s di %s (%s)", worker, client.label, spec)
            except Exception as e:
                log.error("Gagal bikin VPS %s di akun %s: %s",
                          worker, client.label, e)
                created.append({"error": str(e), "worker": worker,
                                "account": client.label})

        return created, success
