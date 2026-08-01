"""UpCloud API 1.3 client + multi-account manager.

Per akun trial: maks 12 CPU core + 24 GB RAM (total seluruh VPS).
Strategi: tiap akun buat 1 VPS 12-core/24GB, 9 thread XMRig.
Auth via API token (Bearer).
"""
import logging
import re
import time

import requests

API_BASE = "https://api.upcloud.com/1.3"
log = logging.getLogger(__name__)


class UpCloudClient:
    def __init__(self, token: str, timeout: int = 30, label: str = ""):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self.label = label

    def _req(self, method: str, path: str, **kw):
        kw.setdefault("timeout", self._timeout)
        kw.setdefault("headers", self._headers)
        r = requests.request(method, API_BASE + path, **kw)
        if r.status_code >= 400:
            raise UpCloudError(f"UpCloud {self.label} {method} {path} -> "
                               f"{r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    # ---------- discovery ----------
    def plans(self):
        return self._req("GET", "/plan").get("plans", {}).get("plan", [])

    def pick_plan(self, cores: int, ram_gb: int) -> dict:
        best = None
        for p in self.plans():
            cn = p.get("core_number", 0) or int(re.match(r"(\d+)xCPU", p.get("name", "0xCPU")).group(1))
            rm = p.get("memory_amount", 0) or int(re.match(r"\d+xCPU-(\d+)GB", p.get("name", "0xCPU-0GB")).group(1)) * 1024
            if cn == cores and rm == ram_gb * 1024:
                best = p
                break
            if cn >= cores and rm >= ram_gb * 1024:
                if best is None or p.get("price", 1e9) < best.get("price", 1e9):
                    best = p
        if best is None:
            raise UpCloudError(f"Tidak ada plan >= {cores} core / {ram_gb} GB")
        return best

    def ubuntu_template(self, version: str = "22.04") -> dict:
        data = self._req("GET", "/storage/template")
        for t in data.get("storages", {}).get("storage", []):
            if "ubuntu" in t.get("title", "").lower() and version in t.get("title", ""):
                return t
        raise UpCloudError(f"Template Ubuntu {version} tidak ditemukan")

    # ---------- servers ----------
    def create_server(self, *, title, hostname, zone, plan, template_uuid,
                      ssh_key, cloud_init_b64) -> dict:
        # auto-upload SSH key dulu biar pasti terdaftar
        self._ensure_ssh_key_registered(ssh_key)
        payload = {
            "server": {
                "zone": zone,
                "title": title,
                "hostname": hostname,
                "metadata": "yes",
                "plan": plan,
                "storage_devices": {"storage_device": [{
                    "action": "clone",
                    "storage": template_uuid,
                    "title": f"{title}-disk",
                    "size": 25,
                    "tier": "maxiops",
                }]},
                "login_user": {
                    "username": "root",
                    "ssh_keys": {"ssh_key": [ssh_key]},
                    "create_password": "no",
                },
                "user_data": cloud_init_b64,
            }
        }
        return self._req("POST", "/server", json=payload).get("server", {})

    def delete_server(self, uuid: str):
        return self._req("DELETE", f"/server/{uuid}?storages=1")

    def stop_server(self, uuid: str, timeout_s: int = 120):
        return self._req("POST", f"/server/{uuid}/stop",
                         json={"stop_server": {"stop_type": "soft",
                                               "timeout": timeout_s}})

    def start_server(self, uuid: str):
        return self._req("POST", f"/server/{uuid}/start")

    def get_server(self, uuid: str) -> dict:
        return self._req("GET", f"/server/{uuid}").get("server", {})

    def _ensure_ssh_key_registered(self, public_key: str):
        """Auto-register SSH key via create_server dry-run / POST /ssh_key.

        UpCloud ga ada endpoint resmi buat register SSH key.
        Tapi create_server() nerima public key mentah — jadi ini safe.
        """
        # Coba POST /1.3/ssh_key (endpoint undocumented)
        import requests
        try:
            r = requests.post(
                API_BASE + "/ssh_key",
                headers=self._headers,
                json={"ssh_key": {"key": public_key, "title": "mining-bot-auto"}},
                timeout=self._timeout // 2,
            )
            log.info("SSH key register: %s (%s)", r.status_code, self.label)
        except Exception:
            pass  # fallback: key tetap dipakai di payload



class Accounts:
    """Manager multi-account UpCloud — sekarang pake API token."""

    def __init__(self, accounts_cfg: list[dict]):
        self.clients = []
        for a in accounts_cfg:
            token = a.get("token", "")
            if not token or token.startswith("YOUR_"):
                continue  # skip placeholder
            self.clients.append(UpCloudClient(
                token=token, label=a.get("label", "")
            ))

    def all(self):
        return self.clients

    def first(self):
        if not self.clients:
            raise UpCloudError("Tidak ada akun UpCloud yang terkonfigurasi")
        return self.clients[0]

    def __len__(self):
        return len(self.clients)


class UpCloudError(RuntimeError):
    pass
