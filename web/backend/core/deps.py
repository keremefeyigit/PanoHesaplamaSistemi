"""
web/backend/core/deps.py
=========================
FastAPI bağımlılık enjeksiyonu — mevcut kullanıcı, admin kontrolü.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from core.security import decode_token
from db.mock_db import get_user_by_email

bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Geçersiz veya süresi dolmuş token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        email: str = payload.get("sub", "")
        if not email:
            raise exc
    except JWTError:
        raise exc

    user = get_user_by_email(email)
    if not user or not user.get("is_active"):
        raise exc
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için admin yetkisi gerekli",
        )
    return user
