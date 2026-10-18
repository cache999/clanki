"""LLM API keys: an environment variable wins (development, tests); otherwise the OS credential
store (Windows Credential Manager), filled from the Settings dialog. Keys never go in files
that clanki writes."""
import os
import platform

import keyring

SERVICE = "clanki"
ENV_VARS = {"deepseek": "DEEPSEEK_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class KeyStoreError(Exception):
    pass


def _env_var(provider: str) -> str:
    if provider not in ENV_VARS:
        raise ValueError("unknown provider: %s" % provider)
    return ENV_VARS[provider]


def _in_wsl() -> bool:
    return "WSL_DISTRO_NAME" in os.environ or "microsoft" in platform.release().lower()


def store_available() -> bool:
    """False in WSL with the system keyring: GNOME Keyring there pops up an unlock prompt or hangs,
    so keys come from the environment variable instead."""
    if not _in_wsl():
        return True
    module = type(keyring.get_keyring()).__module__
    return not module.startswith(("keyring.backends.SecretService", "keyring.backends.libsecret",
                                  "keyring.backends.fail", "keyring.backends.chainer"))


def _stored(provider: str) -> str | None:
    if not store_available():
        return None
    try:
        return keyring.get_password(SERVICE, provider)
    except Exception:  # no usable credential store (e.g. WSL without a secret service)
        return None


def get_key(provider: str) -> str | None:
    return os.environ.get(_env_var(provider)) or _stored(provider) or None


def key_status(provider: str) -> dict:
    env = os.environ.get(_env_var(provider))
    key, source = (env, "env") if env else (_stored(provider), "keyring")
    store = store_available()
    if not key:
        return {"set": False, "source": None, "hint": None, "store": store}
    return {"set": True, "source": source, "hint": "…" + key[-4:], "store": store}


def set_key(provider: str, key: str) -> None:
    var = _env_var(provider)
    key = key.strip()
    if not key:
        raise ValueError("empty key")
    if not store_available():
        raise KeyStoreError("There is no credential store in WSL: set the %s environment variable instead "
                            "(see the README)" % var)
    try:
        keyring.set_password(SERVICE, provider, key)
    except Exception as e:
        raise KeyStoreError("No credential store on this system: set the %s environment "
                            "variable instead" % var) from e


def delete_key(provider: str) -> None:
    _env_var(provider)
    if not store_available():
        return
    try:
        keyring.delete_password(SERVICE, provider)
    except Exception:
        pass
