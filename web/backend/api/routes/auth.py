"""
web/backend/api/routes/auth.py
================================
Giriş / token yenileme endpoint'leri.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from core.security import verify_password, create_access_token
from db.mock_db import get_user_by_email

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    organization_id: str | None


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı",
        )
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Hesap devre dışı")

    token = create_access_token({"sub": user["email"], "role": user["role"]})
    return TokenResponse(
        access_token=token,
        role=user["role"],
        full_name=user["full_name"],
        organization_id=user.get("organization_id"),
    )
