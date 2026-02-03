"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """
    Request body for LDAP login.
    """

    username: str = Field(..., description="AD/LDAP username")
    password: str = Field(..., description="Password")


class UserInfo(BaseModel):
    """
    Basic user info returned after authentication.
    """

    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None


class LoginResponse(BaseModel):
    """
    Response payload after login.
    """

    access_token: str
    token_type: str = "bearer"
    user: UserInfo
