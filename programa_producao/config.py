"""Leitura e gravação da configuração do usuário (pasta de rede monitorada, etc)."""
import json
import os
from pathlib import Path

APP_NAME = "ProgramaProducao"

DEFAULT_CONFIG = {
    "root_path": r"\\192.168.1.10\DatabaseFolder\PDF",
    "refresh_seconds": 10,
    "window_geometry": "",
}


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME


def _config_file() -> Path:
    return _config_dir() / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = _config_file()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    with _config_file().open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
