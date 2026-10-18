"""Settings from config.toml in the per-user app folder (%APPDATA%\\clanki on Windows)."""
import json
import os
import re
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
    config_path: Path | None = None  # the config.toml this came from, for the settings page to update


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
    return Config(data_dir=Path(data_dir), config_path=path, **raw)


def save_config(path: Path, updates: dict) -> None:
    """Set keys in config.toml (None removes one), leaving its other lines and comments alone."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    for key, value in updates.items():
        at = next((i for i, line in enumerate(lines) if re.match(r"\s*%s\s*=" % re.escape(key), line)), None)
        new = None if value is None else "%s = %s" % (key, value if isinstance(value, int) else json.dumps(value, ensure_ascii=False))
        if at is None and new is not None:
            lines.append(new)
        elif at is not None:
            lines[at:at + 1] = [new] if new is not None else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
