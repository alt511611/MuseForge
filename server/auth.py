"""Supabase JWT authentication & role-based authorisation for MuseForge."""

import os
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

bearer_scheme = HTTPBearer(auto_error=False)


class AuthUser:
    def __init__(self, user_id: str, email: str, role: str = "user"):
        self.user_id = user_id
        self.email = email
        self.role = role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def _verify_token(token: str) -> AuthUser:
    """Validate a Supabase access token by calling the /auth/v1/user endpoint."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service not configured (missing SUPABASE_URL or SUPABASE_SERVICE_KEY).",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_SERVICE_KEY,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        )

    data = resp.json()
    user_id = data.get("id")
    email = data.get("email", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not extract user_id from token.",
        )

    # Pull role from app_metadata or user_metadata
    role = (
        data.get("app_metadata", {}).get("role")
        or data.get("user_metadata", {}).get("role")
        or "user"
    )
    return AuthUser(user_id=user_id, email=email, role=role)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthUser:
    """Require a valid Supabase access token. Raises 401 if missing/invalid."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _verify_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthUser]:
    """Return the authenticated user, or None if no token is provided."""
    if not credentials:
        return None
    try:
        return await _verify_token(credentials.credentials)
    except HTTPException:
        return None


async def get_current_admin(
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    """Require the authenticated user to have the 'admin' role."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user
