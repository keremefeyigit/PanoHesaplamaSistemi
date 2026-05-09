"""
web/backend/api/routes/share.py
=================================
Admin'in sefer verilerini kurumlarla paylaşması / geri alması.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import require_admin
from db.mock_db import (
    share_session_with_org, revoke_session_from_org,
    get_organization, get_all_sessions,
)

router = APIRouter()


class ShareRequest(BaseModel):
    session_id: str
    organization_id: str


@router.post("/")
async def share_session(body: ShareRequest, admin: dict = Depends(require_admin)):
    if not get_organization(body.organization_id):
        raise HTTPException(404, "Kurum bulunamadı")
    record = share_session_with_org(
        body.session_id, body.organization_id, admin["id"]
    )
    return {"message": "Paylaşıldı", "record": record}


@router.delete("/")
async def revoke_share(body: ShareRequest, _: dict = Depends(require_admin)):
    ok = revoke_session_from_org(body.session_id, body.organization_id)
    if not ok:
        raise HTTPException(404, "Paylaşım kaydı bulunamadı")
    return {"message": "Paylaşım kaldırıldı"}


@router.get("/sessions")
async def shared_session_summary(_: dict = Depends(require_admin)):
    """Admin için tüm sefer + hangi kurumlarla paylaşıldığı listesi."""
    return get_all_sessions()
