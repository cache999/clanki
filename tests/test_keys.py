import keyring
import pytest
from keyring.backend import KeyringBackend

from clanki import keys
from fake_keyring import MemoryKeyring


class BrokenKeyring(KeyringBackend):  # what WSL without a secret service looks like
    priority = 1

    def get_password(self, service, username):
        raise RuntimeError("no secret service")

    def set_password(self, service, username, password):
        raise RuntimeError("no secret service")

    def delete_password(self, service, username):
        raise RuntimeError("no secret service")


@pytest.fixture
def memory(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    kr = MemoryKeyring()
    keyring.set_keyring(kr)
    yield kr
    keyring.set_keyring(old)


@pytest.fixture
def broken(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(BrokenKeyring())
    yield
    keyring.set_keyring(old)


def test_no_key_anywhere(memory):
    assert keys.get_key("deepseek") is None
    assert keys.key_status("deepseek") == {"set": False, "source": None, "hint": None, "store": True}


def test_environment_variable_wins(memory, monkeypatch):
    memory.set_password("clanki", "deepseek", "sk-stored-0000")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env-1234")
    assert keys.get_key("deepseek") == "sk-from-env-1234"
    assert keys.key_status("deepseek") == {"set": True, "source": "env", "hint": "…1234", "store": True}


def test_store_and_delete_in_credential_store(memory):
    keys.set_key("deepseek", "  sk-abcdef9876  ")
    assert keys.get_key("deepseek") == "sk-abcdef9876"
    assert keys.key_status("deepseek") == {"set": True, "source": "keyring", "hint": "…9876", "store": True}
    keys.delete_key("deepseek")
    assert keys.get_key("deepseek") is None
    keys.delete_key("deepseek")  # deleting twice is fine


def test_broken_credential_store_is_not_fatal(broken):
    assert keys.get_key("deepseek") is None
    with pytest.raises(keys.KeyStoreError, match="DEEPSEEK_API_KEY"):
        keys.set_key("deepseek", "sk-x")


def test_empty_and_unknown_keys_are_rejected(memory):
    with pytest.raises(ValueError):
        keys.set_key("deepseek", "   ")
    with pytest.raises(ValueError):
        keys.get_key("openai")


class HangingKeyring(KeyringBackend):  # GNOME Keyring in WSL: waits for an unlock prompt
    priority = 1

    def get_password(self, service, username):
        raise AssertionError("must not be asked")

    set_password = delete_password = get_password


@pytest.fixture
def wsl(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(keys, "store_available", lambda: False)
    old = keyring.get_keyring()
    keyring.set_keyring(HangingKeyring())
    yield
    keyring.set_keyring(old)


def test_without_a_credential_store_the_keyring_is_never_asked(wsl, monkeypatch):
    assert keys.get_key("deepseek") is None
    assert keys.key_status("deepseek") == {"set": False, "source": None, "hint": None, "store": False}
    with pytest.raises(keys.KeyStoreError, match="DEEPSEEK_API_KEY"):
        keys.set_key("deepseek", "sk-123")
    keys.delete_key("deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-9876")
    assert keys.key_status("deepseek")["hint"] == "…9876"


def test_wsl_with_the_system_keyring_has_no_store(monkeypatch):
    from keyring.backends import SecretService, fail
    monkeypatch.setattr(keys, "_in_wsl", lambda: True)
    for backend, available in ((SecretService.Keyring(), False), (fail.Keyring(), False), (MemoryKeyring(), True)):
        monkeypatch.setattr(keyring, "get_keyring", lambda b=backend: b)
        assert keys.store_available() is available
    monkeypatch.setattr(keys, "_in_wsl", lambda: False)
    monkeypatch.setattr(keyring, "get_keyring", lambda: SecretService.Keyring())
    assert keys.store_available()  # a Linux desktop's keyring works
