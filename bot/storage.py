"""Persistensi data (daftar server) dalam JSON."""
import json
from pathlib import Path


class Store:
    def __init__(self, data_dir: str):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.servers_path = self.dir / "servers.json"
        self.servers = self._load(self.servers_path, [])

    def _load(self, p: Path, default):
        try:
            return json.loads(p.read_text()) if p.exists() else default
        except Exception:
            return default

    def _flush(self):
        self.servers_path.write_text(
            json.dumps(self.servers, indent=2, ensure_ascii=False)
        )

    def add_server(self, server: dict):
        self.servers.append(server)
        self._flush()

    def update_server(self, uuid: str, **fields):
        for s in self.servers:
            if s.get("uuid") == uuid:
                s.update(fields)
                break
        self._flush()

    def remove_server(self, uuid: str):
        self.servers = [s for s in self.servers if s.get("uuid") != uuid]
        self._flush()

    def get(self, uuid: str):
        for s in self.servers:
            if s.get("uuid") == uuid:
                return s
        return None

    def list_servers(self):
        return list(self.servers)
