from pathlib import Path

from clanki.config import load_config


def test_defaults_when_no_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CLANKI_DATA_DIR", raising=False)
    cfg = load_config(config_path=tmp_path / "missing.toml", default_dir=tmp_path / "appdata")
    assert cfg.data_dir == tmp_path / "appdata"
    assert (cfg.host, cfg.port) == ("127.0.0.1", 8710)
    assert cfg.anki_url == "http://127.0.0.1:8765"
    assert cfg.soffice is None and cfg.default_deck == "Default"


def test_values_from_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CLANKI_DATA_DIR", raising=False)
    p = tmp_path / "config.toml"
    p.write_text('data_dir = "D:/OneDrive/clanki"\nport = 9000\nsoffice = "C:/LO/soffice.exe"\n'
                 'default_deck = "MVST1B"\n', encoding="utf-8")
    cfg = load_config(config_path=p, default_dir=tmp_path)
    assert cfg.data_dir == Path("D:/OneDrive/clanki")
    assert (cfg.port, cfg.soffice, cfg.default_deck) == (9000, "C:/LO/soffice.exe", "MVST1B")


def test_environment_overrides_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLANKI_DATA_DIR", str(tmp_path / "env"))
    cfg = load_config(config_path=tmp_path / "missing.toml", default_dir=tmp_path)
    assert cfg.data_dir == tmp_path / "env"
