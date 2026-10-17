"""Settings from config.toml in the per-user app folder (%APPDATA%\\clanki on Windows)."""
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

import platformdirs

from .ankiconnect import DEFAULT_URL


@dataclass
class Config:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8710
    anki_url: str = DEFAULT_URL
    soffice: str | None = None
    default_deck: str = "Default"


def app_dir() -> Path:
    return Path(platformdirs.user_data_dir("clanki", appauthor=False, roaming=True))


def load_config(config_path: Path | None = None, default_dir: Path | None = None) -> Config:
    """data_dir comes from CLANKI_DATA_DIR, else config.toml, else the app folder; pointing it
    at a synced folder (e.g. OneDrive) shares documents and cards between PCs."""
    base = default_dir or app_dir()
    path = config_path or base / "config.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data_dir = os.environ.get("CLANKI_DATA_DIR") or raw.pop("data_dir", None) or base
    raw.pop("data_dir", None)
    unknown = set(raw) - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError("unknown settings in %s: %s" % (path, ", ".join(sorted(unknown))))
    return Config(data_dir=Path(data_dir), **raw)
