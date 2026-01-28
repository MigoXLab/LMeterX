"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import pytest

from service import auth_service
from utils.error_handler import ErrorMessages, ErrorResponse


def test_ensure_ldap_ready_requires_search_base_for_bind_dn(monkeypatch):
    monkeypatch.setattr(auth_service.settings, "LDAP_ENABLED", True)
    monkeypatch.setattr(auth_service.settings, "LDAP_SERVER", "ldap://example.com")
    monkeypatch.setattr(
        auth_service.settings, "LDAP_BIND_DN", "cn=service,dc=example,dc=com"
    )
    monkeypatch.setattr(auth_service.settings, "LDAP_BIND_PASSWORD", "secret")
    monkeypatch.setattr(auth_service.settings, "LDAP_SEARCH_BASE", "")
    monkeypatch.setattr(
        auth_service.settings,
        "LDAP_USER_DN_TEMPLATE",
        "uid={username},dc=example,dc=com",
    )

    with pytest.raises(ErrorResponse) as exc:
        auth_service._ensure_ldap_ready()

    assert exc.value.error == ErrorMessages.LDAP_CONFIG_INCOMPLETE
    assert exc.value.details == {"missing": ["LDAP_SEARCH_BASE"]}
