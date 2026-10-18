"""The settings page: defaults for new documents (kept with the data) and this PC's settings
(written to config.toml)."""
import tomllib

import pytest
from fastapi.testclient import TestClient

import clanki.app
from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import load_config
from fake_anki import FakeAnki
from make_pdf import make_pdf


@pytest.fixture
def anki():
    return FakeAnki()


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.delenv("CLANKI_DATA_DIR", raising=False)
    return {"config": tmp_path / "cfg" / "config.toml", "base": tmp_path / "cfg"}


def make(paths, anki):
    cfg = load_config(paths["config"], default_dir=paths["base"])
    connect = AnkiConnect(url=cfg.anki_url, transport=anki.transport())
    return TestClient(create_app(cfg, anki=connect)), connect


@pytest.fixture
def client(paths, anki):
    return make(paths, anki)[0]


def put(client, **body):
    return client.put("/api/settings", json=body)


def upload(client, name="vision"):
    return client.post("/api/documents", files={"file": (name + ".pdf", make_pdf([["x"]]), "application/pdf")}).json()


def test_defaults_for_new_documents(client, anki):
    s = put(client, default_deck="MVST1B", default_tags=["NHB", "year2"]).json()
    assert s["defaults"] == {"deck": "MVST1B", "tags": ["NHB", "year2"], "profile": "medical_ukmla"}
    doc = upload(client)
    assert doc["tags"] == ["NHB", "year2"] and doc["deck"] == ""
    client.post("/api/documents/%s/notes" % doc["id"], json={"type": "qa", "front": "F", "back": "B"})
    client.post("/api/documents/%s/send" % doc["id"])
    [n] = anki.notes.values()
    assert n["deckName"] == "MVST1B"  # the document has no deck of its own


def test_this_pcs_settings_go_to_config_toml(client, paths):
    r = put(client, anki_url="http://127.0.0.1:9999", port=8800, data_dir=str(paths["base"] / "data2"))
    assert r.status_code == 200, r.text
    assert r.json()["restart"] is True
    saved = tomllib.loads(paths["config"].read_text(encoding="utf-8"))
    assert saved == {"anki_url": "http://127.0.0.1:9999", "port": 8800, "data_dir": str(paths["base"] / "data2")}
    cfg = load_config(paths["config"], default_dir=paths["base"])
    assert (cfg.anki_url, cfg.port) == ("http://127.0.0.1:9999", 8800)


def test_the_anki_address_applies_at_once(paths, anki):
    client, connect = make(paths, anki)
    r = put(client, anki_url="http://127.0.0.1:9999").json()
    assert r["restart"] is False and connect.url == "http://127.0.0.1:9999"
    assert r["machine"]["anki_url"] == "http://127.0.0.1:9999"


def test_existing_config_lines_are_kept(paths, anki):
    paths["base"].mkdir(parents=True)
    paths["config"].write_text('default_deck = "Old deck"\nsoffice = "C:/LO/soffice.exe"\n', encoding="utf-8")
    client, _ = make(paths, anki)
    put(client, port=8711)
    assert tomllib.loads(paths["config"].read_text(encoding="utf-8")) == {
        "default_deck": "Old deck", "soffice": "C:/LO/soffice.exe", "port": 8711}


def test_libreoffice_is_reported_and_its_path_checked(client, monkeypatch, tmp_path):
    fake = tmp_path / "soffice"
    fake.write_text("")
    monkeypatch.setattr(clanki.app.convert, "find_soffice", lambda configured=None: fake)
    assert client.get("/api/settings").json()["machine"]["soffice_found"] == str(fake)
    assert put(client, soffice=str(fake)).json()["machine"]["soffice"] == str(fake)
    assert put(client, soffice=str(tmp_path / "missing.exe")).status_code == 422


@pytest.mark.parametrize("body", [{"port": 80}, {"port": 70000}, {"anki_url": "localhost:8765"}, {"default_profile": "nope"},
                                  {"data_dir": "relative/path"}, {"unknown": 1}])
def test_bad_settings_are_refused(client, body):
    assert put(client, **body).status_code == 422


def test_the_third_party_notice_is_accepted_once_and_remembered(paths, anki):
    client, _ = make(paths, anki)
    assert client.get("/api/settings").json()["llm_notice_accepted"] is False
    assert client.post("/api/settings/llm-notice").json()["llm_notice_accepted"] is True
    again, _ = make(paths, anki)
    assert again.get("/api/settings").json()["llm_notice_accepted"] is True
