"""
web/backend/api/routes/detections.py
======================================
Tespit verisi listeleme, filtreleme, istatistik.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from core.deps import get_current_user
from db.mock_db import (
    get_all_detections, get_detection_count,
    get_class_distribution, get_dashboard_stats,
    get_all_sessions,
)

router = APIRouter()


@router.get("/")
async def list_detections(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    class_filter: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Admin tüm tespitleri görür, viewer paylaşılan sefer tespitlerini görür."""
    org_id = None if user["role"] == "admin" else user.get("organization_id")
    return {
        "total": get_detection_count(class_filter),
        "items": get_all_detections(limit, offset, class_filter, org_id),
    }


@router.get("/stats/dashboard")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    return get_dashboard_stats()


@router.get("/stats/distribution")
async def class_distribution(user: dict = Depends(get_current_user)):
    return get_class_distribution()


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    sessions = get_all_sessions()
    if user["role"] == "admin":
        return sessions
    # Viewer: sadece kendisiyle paylaşılmış sefer
    org_id = user.get("organization_id")
    return [s for s in sessions if org_id in s.get("shared_with_orgs", [])]
