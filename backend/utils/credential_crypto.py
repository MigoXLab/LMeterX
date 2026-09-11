"""Authenticated encryption for A2A/MCP request headers.

Header values are write-only credentials from the browser's perspective.  The
database stores a JSON envelope so the existing MySQL JSON column remains
compatible, while the Backend decrypts the payload only when dispatching work
to an authenticated Engine.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

from cryptography.fernet import Fernet, InvalidToken

ENVELOPE_MARKER = "_lmeterx_encrypted_headers"
KEYRING_ENV = "AGENT_CREDENTIAL_ENCRYPTION_KEYS"
_TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class CredentialEncryptionError(RuntimeError):
    """Raised when credentials cannot be encrypted or decrypted safely."""


def _keyring() -> tuple[str, dict[str, Fernet]]:
    """Load ``key-id:fernet-key`` entries; the first key is used for writes."""
    raw = os.getenv(KEYRING_ENV, "").strip()
    if not raw and os.getenv("TESTING"):
        raw = f"test:{_TEST_KEY}"
    if not raw:
        raise CredentialEncryptionError(
            f"{KEYRING_ENV} is required before storing Agent request headers"
        )

    keys: dict[str, Fernet] = {}
    for entry in raw.split(","):
        key_id, separator, encoded_key = entry.strip().partition(":")
        if not separator or not key_id or not encoded_key:
            raise CredentialEncryptionError(
                f"{KEYRING_ENV} must use key-id:fernet-key entries"
            )
        if key_id in keys:
            raise CredentialEncryptionError(f"duplicate credential key id: {key_id}")
        try:
            keys[key_id] = Fernet(encoded_key.encode("ascii"))
        except ValueError as exc:
            raise CredentialEncryptionError(
                f"invalid Fernet key configured for key id {key_id!r}"
            ) from exc
    return next(iter(keys)), keys


def is_encrypted_headers(stored: object) -> bool:
    """Return whether a stored JSON value is an LMeterX encrypted envelope."""
    if not isinstance(stored, str) or not stored:
        return False
    try:
        value = json.loads(stored)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get(ENVELOPE_MARKER) == 1


def encrypt_headers(headers: Mapping[str, str]) -> str:
    """Serialize and encrypt headers into a MySQL-JSON-compatible envelope."""
    normalized = {str(key): str(value) for key, value in headers.items()}
    if not normalized:
        return "{}"
    active_key_id, keys = _keyring()
    plaintext = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    token = keys[active_key_id].encrypt(plaintext).decode("ascii")
    return json.dumps(
        {
            ENVELOPE_MARKER: 1,
            "algorithm": "fernet",
            "key_id": active_key_id,
            "header_names": list(normalized),
            "ciphertext": token,
        },
        separators=(",", ":"),
    )


def decrypt_headers(stored: object) -> dict[str, str]:
    """Decrypt an envelope, while accepting legacy plaintext JSON objects."""
    if stored is None or stored == "":
        return {}
    if not isinstance(stored, str):
        raise CredentialEncryptionError("stored Agent request headers are invalid")
    try:
        value = json.loads(stored)
    except json.JSONDecodeError as exc:
        raise CredentialEncryptionError(
            "stored Agent request headers are invalid"
        ) from exc
    if not isinstance(value, dict):
        raise CredentialEncryptionError(
            "stored Agent request headers must be an object"
        )

    if value.get(ENVELOPE_MARKER) != 1:
        # Backward-compatible read for records created before encrypted storage.
        return {str(key): str(item) for key, item in value.items()}

    key_id = value.get("key_id")
    token = value.get("ciphertext")
    if not isinstance(key_id, str) or not isinstance(token, str):
        raise CredentialEncryptionError("encrypted Agent request headers are malformed")
    _, keys = _keyring()
    cipher = keys.get(key_id)
    if cipher is None:
        raise CredentialEncryptionError(
            f"credential key id {key_id!r} is not configured"
        )
    try:
        plaintext = cipher.decrypt(token.encode("ascii"))
        headers = json.loads(plaintext.decode("utf-8"))
    except (InvalidToken, UnicodeError, json.JSONDecodeError) as exc:
        raise CredentialEncryptionError(
            "encrypted Agent request headers failed integrity verification"
        ) from exc
    if not isinstance(headers, dict):
        raise CredentialEncryptionError("decrypted Agent request headers are invalid")
    return {str(key): str(item) for key, item in headers.items()}


def get_header_names(stored: object) -> list[str]:
    """Read non-secret header names without decrypting modern envelopes."""
    if stored is None or stored == "":
        return []
    if not isinstance(stored, str):
        raise CredentialEncryptionError("stored Agent request headers are invalid")
    try:
        value = json.loads(stored)
    except json.JSONDecodeError as exc:
        raise CredentialEncryptionError(
            "stored Agent request headers are invalid"
        ) from exc
    if not isinstance(value, dict):
        raise CredentialEncryptionError(
            "stored Agent request headers must be an object"
        )
    if value.get(ENVELOPE_MARKER) != 1:
        return [str(key) for key in value]
    names = value.get("header_names")
    if isinstance(names, list) and all(isinstance(item, str) for item in names):
        return names
    # Compatibility for envelopes written before header_names was introduced.
    return list(decrypt_headers(stored))
