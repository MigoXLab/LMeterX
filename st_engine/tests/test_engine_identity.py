import pytest

from utils.engine_identity import resolve_engine_id

ENGINE_ID_ENV_KEYS = (
    "ENGINE_ID",
    "ENGINE_POD_NAME",
    "ENGINE_ID_FALLBACK",
    "HOSTNAME",
)


def clear_engine_identity_env(monkeypatch):
    for key in ENGINE_ID_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (
            {
                "ENGINE_ID": "explicit-engine",
                "ENGINE_POD_NAME": "engine-pod",
                "ENGINE_ID_FALLBACK": "fallback-engine",
                "HOSTNAME": "container-hostname",
            },
            "explicit-engine",
        ),
        (
            {
                "ENGINE_POD_NAME": "engine-pod",
                "ENGINE_ID_FALLBACK": "fallback-engine",
                "HOSTNAME": "container-hostname",
            },
            "engine-pod",
        ),
        (
            {
                "ENGINE_ID_FALLBACK": "fallback-engine",
                "HOSTNAME": "container-hostname",
            },
            "fallback-engine",
        ),
        ({"HOSTNAME": "container-hostname"}, "container-hostname"),
    ],
)
def test_resolve_engine_id_precedence(monkeypatch, env, expected):
    clear_engine_identity_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert resolve_engine_id() == expected


def test_resolve_engine_id_strips_whitespace(monkeypatch):
    clear_engine_identity_env(monkeypatch)
    monkeypatch.setenv("HOSTNAME", "  container-hostname  ")

    assert resolve_engine_id() == "container-hostname"


def test_resolve_engine_id_uses_local_fallback(monkeypatch):
    clear_engine_identity_env(monkeypatch)

    assert resolve_engine_id() == "engine-local"


def test_resolve_engine_id_rejects_values_longer_than_database_column(monkeypatch):
    clear_engine_identity_env(monkeypatch)
    monkeypatch.setenv("ENGINE_ID", "e" * 65)

    with pytest.raises(ValueError, match="ENGINE_ID must not exceed 64 characters"):
        resolve_engine_id()
