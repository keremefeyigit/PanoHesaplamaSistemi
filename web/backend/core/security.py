"""
web/backend/core/security.py
=============================
JWT tabanlı kimlik doğrulama ve yetkilendirme.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

import os
# ─── Sabitler (üretimde env-var ile override et) ──────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "tabela-super-secret-change-in-production-32chars!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8   # 8 saat

pwd_context = CryptContext(schemes=["md5_crypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Token'ı çöz ve payload'ı döndür. Geçersizse JWTError fırlatır."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
