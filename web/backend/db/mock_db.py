"""
web/backend/db/mock_db.py
==========================
Geliştirme aşamasında PostgreSQL yerine kullanılan in-memory veri deposu.
Gerçek DB bağlantısı hazır olduğunda bu modülün yerine database_manager.py geçecek.

Seed verisi: 2 kurum, 50 simüle tespit, 1 admin kullanıcı.
"""
from __future__ import annotations

import math
import random
import time
import uuid
from datetime import datetime, timezone

from core.security import hash_password

# ─── Kullanıcılar ─────────────────────────────────────────────────────────────
_USERS: dict[str, dict] = {
    "admin@tabela.local": {
        "id": "usr-admin-001",
        "email": "admin@tabela.local",
        "password_hash": hash_password("admin123"),
        "full_name": "Sistem Yöneticisi",
        "role": "admin",
        "organization_id": None,
        "is_active": True,
    },
    "izleme@ankara-bld.local": {
        "id": "usr-org-001",
        "email": "izleme@ankara-bld.local",
        "password_hash": hash_password("ankara123"),
        "full_name": "Ankara Belediyesi İzleyici",
        "role": "viewer",
        "organization_id": "org-001",
        "is_active": True,
    },
}

# ─── Organizasyonlar ──────────────────────────────────────────────────────────
_ORGANIZATIONS: dict[str, dict] = {
    "org-001": {
        "id": "org-001",
        "name": "Ankara Büyükşehir Belediyesi",
        "slug": "ankara-buyuksehir",
        "contact_email": "reklam@ankara.bel.tr",
        "is_active": True,
        "plan": "free",
        "created_at": "2026-01-15T08:00:00Z",
        "detection_count": 0,
        "shared_session_count": 0,
    },
    "org-002": {
        "id": "org-002",
        "name": "İstanbul Büyükşehir Belediyesi",
        "slug": "istanbul-buyuksehir",
        "contact_email": "reklam@ibb.istanbul",
        "is_active": True,
        "plan": "free",
        "created_at": "2026-02-10T09:30:00Z",
        "detection_count": 0,
        "shared_session_count": 0,
    },
}

# ─── Simüle Tespitler ─────────────────────────────────────────────────────────
rng = random.Random(42)

SIGN_CLASSES = ["tabela", "pano", "megalight", "raket", "afis"]
# Ankara merkezi civarında noktalar
ANKARA_CENTER = (39.9208, 32.8541)

def _rand_coord(center: tuple[float, float], radius_deg: float = 0.05) -> tuple[float, float]:
    lat = center[0] + rng.uniform(-radius_deg, radius_deg)
    lon = center[1] + rng.uniform(-radius_deg, radius_deg)
    return round(lat, 6), round(lon, 6)

_DETECTIONS: list[dict] = []
_SESSIONS: list[dict] = []

def _seed_data():
    session_id = "ses-mock-001"
    _SESSIONS.append({
        "id": session_id,
        "vehicle_id": "34-ABC-001",
        "started_at": "2026-05-01T08:00:00Z",
        "ended_at": "2026-05-01T12:30:00Z",
        "total_km": 45.3,
        "organization_id": None,
    })

    base_ts = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc).timestamp()
    for i in range(60):
        lat, lon = _rand_coord(ANKARA_CENTER)
        cls = rng.choice(SIGN_CLASSES)
        w = round(rng.uniform(1.5, 6.0), 2)
        h = round(rng.uniform(0.8, 3.0), 2)
        dist = round(rng.uniform(8.0, 80.0), 1)
        conf = round(rng.uniform(0.55, 0.98), 3)
        ts = base_ts + i * 210   # her ~3.5 dk bir tespit

        _DETECTIONS.append({
            "id": f"det-{i:04d}",
            "session_id": session_id,
            "detected_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "class_label": cls,
            "confidence": conf,
            "distance_m": dist,
            "real_width_m": w,
            "real_height_m": h,
            "area_m2": round(w * h, 3),
            "sign_lat": lat,
            "sign_lon": lon,
            "vehicle_lat": round(lat - 0.002, 6),
            "vehicle_lon": round(lon - 0.001, 6),
            "source_camera": rng.choice(["wide", "narrow"]),
            "measurement_method": rng.choice(["similar_triangles", "disparity", "combined"]),
            "thumbnail_path": None,
            "is_shared_with": [],   # ["org-001"] gibi
        })

_seed_data()

# ─── Paylaşım tablosu ────────────────────────────────────────────────────────
_SHARED: list[dict] = []   # {session_id, org_id, shared_at}

# ─── Erişim Fonksiyonları ─────────────────────────────────────────────────────

def get_user_by_email(email: str) -> dict | None:
    return _USERS.get(email)


def get_user_by_id(user_id: str) -> dict | None:
    return next((u for u in _USERS.values() if u["id"] == user_id), None)


def get_all_organizations() -> list[dict]:
    orgs = list(_ORGANIZATIONS.values())
    for org in orgs:
        shared_session_ids = {s["session_id"] for s in _SHARED if s["org_id"] == org["id"]}
        org["detection_count"] = sum(
            1 for d in _DETECTIONS if d["session_id"] in shared_session_ids
        )
        org["shared_session_count"] = len(shared_session_ids)
    return orgs


def get_organization(org_id: str) -> dict | None:
    return _ORGANIZATIONS.get(org_id)


def create_organization(name: str, slug: str, contact_email: str = "") -> dict:
    org_id = f"org-{uuid.uuid4().hex[:8]}"
    org = {
        "id": org_id,
        "name": name,
        "slug": slug,
        "contact_email": contact_email,
        "is_active": True,
        "plan": "free",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "detection_count": 0,
        "shared_session_count": 0,
    }
    _ORGANIZATIONS[org_id] = org
    return org


def delete_organization(org_id: str) -> bool:
    if org_id in _ORGANIZATIONS:
        del _ORGANIZATIONS[org_id]
        return True
    return False


def get_all_detections(
    limit: int = 100,
    offset: int = 0,
    class_filter: str | None = None,
    org_id: str | None = None,
) -> list[dict]:
    dets = _DETECTIONS
    if class_filter:
        dets = [d for d in dets if d["class_label"] == class_filter]
    if org_id:
        shared_session_ids = {s["session_id"] for s in _SHARED if s["org_id"] == org_id}
        dets = [d for d in dets if d["session_id"] in shared_session_ids]
    return dets[offset: offset + limit]


def get_detection_count(class_filter: str | None = None) -> int:
    if class_filter:
        return sum(1 for d in _DETECTIONS if d["class_label"] == class_filter)
    return len(_DETECTIONS)


def get_class_distribution() -> dict[str, int]:
    dist: dict[str, int] = {}
    for d in _DETECTIONS:
        dist[d["class_label"]] = dist.get(d["class_label"], 0) + 1
    return dist


def get_shared_sessions_for_org(org_id: str) -> list[str]:
    return [s["session_id"] for s in _SHARED if s["org_id"] == org_id]


def share_session_with_org(session_id: str, org_id: str, shared_by: str) -> dict:
    # Zaten paylaşılmışsa güncelleme yapma
    existing = next(
        (s for s in _SHARED if s["session_id"] == session_id and s["org_id"] == org_id),
        None,
    )
    if existing:
        return existing
    record = {
        "id": uuid.uuid4().hex,
        "session_id": session_id,
        "org_id": org_id,
        "shared_by": shared_by,
        "shared_at": datetime.now(timezone.utc).isoformat(),
    }
    _SHARED.append(record)
    return record


def revoke_session_from_org(session_id: str, org_id: str) -> bool:
    global _SHARED
    before = len(_SHARED)
    _SHARED = [s for s in _SHARED if not (s["session_id"] == session_id and s["org_id"] == org_id)]
    return len(_SHARED) < before


def get_all_sessions() -> list[dict]:
    result = []
    for s in _SESSIONS:
        shared_orgs = [sh["org_id"] for sh in _SHARED if sh["session_id"] == s["id"]]
        det_count = sum(1 for d in _DETECTIONS if d["session_id"] == s["id"])
        result.append({**s, "shared_with_orgs": shared_orgs, "detection_count": det_count})
    return result


def get_dashboard_stats() -> dict:
    return {
        "total_detections": len(_DETECTIONS),
        "total_organizations": len(_ORGANIZATIONS),
        "total_sessions": len(_SESSIONS),
        "class_distribution": get_class_distribution(),
        "avg_distance_m": round(
            sum(d["distance_m"] for d in _DETECTIONS) / max(len(_DETECTIONS), 1), 2
        ),
        "avg_area_m2": round(
            sum(d["area_m2"] for d in _DETECTIONS) / max(len(_DETECTIONS), 1), 3
        ),
    }
