"""
web/backend/api/routes/organizations.py
========================================
Kurum CRUD — Admin only.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import require_admin, get_current_user
from db.mock_db import (
    get_all_organizations, get_organization,
    create_organization, delete_organization,
)

router = APIRouter()


class OrgCreate(BaseModel):
    name: str
    slug: str
    contact_email: str = ""


@router.get("/")
async def list_organizations(user: dict = Depends(get_current_user)):
    """Admin tüm kurumları görür, viewer yalnızca kendi kurumunu."""
    orgs = get_all_organizations()
    if user["role"] == "admin":
        return orgs
    # Viewer sadece kendi kurumunu görebilir
    org_id = user.get("organization_id")
    return [o for o in orgs if o["id"] == org_id]


@router.post("/", status_code=201)
async def create_org(body: OrgCreate, _: dict = Depends(require_admin)):
    if get_organization(body.slug):
        raise HTTPException(400, "Bu slug zaten kullanılıyor")
    return create_organization(body.name, body.slug, body.contact_email)


@router.get("/{org_id}")
async def get_org(org_id: str, user: dict = Depends(get_current_user)):
    org = get_organization(org_id)
    if not org:
        raise HTTPException(404, "Kurum bulunamadı")
    # Viewer yalnızca kendi kurumunu görebilir
    if user["role"] == "viewer" and user.get("organization_id") != org_id:
        raise HTTPException(403, "Erişim yok")
    return org


@router.delete("/{org_id}", status_code=204)
async def remove_org(org_id: str, _: dict = Depends(require_admin)):
    if not delete_organization(org_id):
        raise HTTPException(404, "Kurum bulunamadı")
