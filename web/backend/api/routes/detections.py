"""
web/backend/api/routes/detections.py
======================================
Tespit verisi listeleme, yükleme, istatistik.
"""
from fastapi import APIRouter, Depends, Query, File, UploadFile, Form, HTTPException
from typing import Optional, List
import uuid
import time
import math
from datetime import datetime, timezone
import cv2
import numpy as np

from core.deps import get_current_user
from db.mock_db import (
    get_all_detections, get_detection_count,
    get_class_distribution, get_dashboard_stats,
    get_all_sessions, _DETECTIONS, share_session_with_org, get_user_by_email
)

router = APIRouter()

detector = None
try:
    import sys, os, importlib.util
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
    
    detector_path = os.path.join(root_dir, "core", "object_detector.py")
    config_path = os.path.join(root_dir, "config.py")

    if os.path.exists(detector_path) and os.path.exists(config_path):
        import sys
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
            
        import config
        # Backend içinde "core" paketi olduğu için import çakışması oluyor, mutlak yoldan yüklüyoruz.
        spec = importlib.util.spec_from_file_location("root_core.object_detector", detector_path)
        od_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(od_module)
        detector = od_module.ObjectDetector(config.default_config.detector)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Warning: ObjectDetector not loaded in backend: {e}")

@router.get("/")
async def list_detections(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    class_filter: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = None if user["role"] == "admin" else user.get("organization_id")
    return {
        "total": get_detection_count(class_filter),
        "items": get_all_detections(limit, offset, class_filter, org_id),
    }

@router.post("/process-image")
async def process_image(
    file: UploadFile = File(...),
    org_id: Optional[str] = Form(None),
    gps_lat: Optional[float] = Form(39.9208),
    gps_lon: Optional[float] = Form(32.8541)
):
    # Dummy user bypass since ui doesn't auth specifically yet
    user = get_user_by_email("admin@tabela.local")

    image_bytes = await file.read()
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_cv is None:
        return {"error": "Geçersiz resim formatı"}

    obj_class = "Bulunamadı"
    conf = 0.0
    width_m = 0.0
    height_m = 0.0
    distance_m = 0.0

    if detector:
        # Confidence düşük tutulabilir algılaması için
        detections, _ = detector.detect(img_cv, conf_threshold=0.1)
        if detections:
            largest = max(detections, key=lambda d: d.bbox.width * d.bbox.height)
            obj_class = largest.class_name
            conf = largest.confidence
            
            # Dinamik hesaplama: Pano genişliğini standart 3m baz alarak hesaplıyoruz
            f = 850.0 # Kamera odak uzaklığı (varsayım)
            W_real_assume = 3.0 # Çoğu pano minimum 3m genişliğindedir
            P = largest.bbox.width
            if P > 0:
                distance_m = round((W_real_assume * f) / P, 1)
                width_m = W_real_assume
                H_px = largest.bbox.height
                height_m = round((distance_m * H_px) / f, 2)
        else:
            raise HTTPException(status_code=422, detail="Resimde pano tespit edilemedi. Daha net veya yakın bir fotoğraf deneyin.")
    else:
        raise HTTPException(status_code=503, detail="Yapay zeka modeli arkaplanda yüklenemedi. Sunucu loglarını kontrol edin.")

    session_id = f"ses-web-{uuid.uuid4().hex[:6]}"
    session_exists = next((s for s in get_all_sessions() if s["id"] == session_id), None)
    if not session_exists:
        from db.mock_db import _SESSIONS
        _SESSIONS.append({
            "id": session_id,
            "vehicle_id": "Web-Upload",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "total_km": 0.0,
            "organization_id": org_id,
        })
    
    new_detection = {
        "id": f"det-{uuid.uuid4().hex[:6]}",
        "session_id": session_id,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "class_label": obj_class,
        "confidence": conf,
        "distance_m": distance_m,
        "real_width_m": width_m,
        "real_height_m": height_m,
        "area_m2": round(width_m * height_m, 3),
        "sign_lat": gps_lat,
        "sign_lon": gps_lon,
        "vehicle_lat": gps_lat,
        "vehicle_lon": gps_lon,
        "source_camera": "webcam",
        "measurement_method": "similar_triangles",
        "thumbnail_path": None,
        "is_shared_with": [org_id] if org_id else [],
    }
    
    _DETECTIONS.insert(0, new_detection)
    
    if org_id:
        share_session_with_org(session_id, org_id, user.get("id"))
    
    return {"message": "Başarılı", "detection": new_detection}

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
    org_id = user.get("organization_id")
    return [s for s in sessions if org_id in s.get("shared_with_orgs", [])]
