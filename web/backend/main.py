"""
web/backend/main.py
====================
FastAPI uygulama giriş noktası.

Çalıştırma (geliştirme):
    cd web/backend
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import auth, organizations, detections, stream, share

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlangıç ve kapanış işlemleri."""
    logger.info("Akıllı Tabela Backend başlıyor...")
    yield
    logger.info("Backend kapatılıyor.")


app = FastAPI(
    title="Akıllı Tabela Ölçüm Sistemi API",
    description="Tabela tespiti, ölçümü ve kurum yönetimi",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://159.65.115.194",
        "http://159.65.115.194:5173",
        "http://159.65.115.194:8000",
        "*",  # Geliştirme ortamı için tüm origin'lere izin ver
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Router'lar ───────────────────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(organizations.router, prefix="/api/organizations",  tags=["Organizations"])
app.include_router(detections.router,    prefix="/api/detections",     tags=["Detections"])
app.include_router(stream.router,        prefix="/api/stream",         tags=["Stream"])
app.include_router(share.router,         prefix="/api/share",          tags=["Share"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "tabela-backend"}

@app.get("/")
async def root():
    return {"message": "Akıllı Tabela Backend API Çalışıyor! Dokümantasyon için /docs adresine gidebilirsiniz."}
