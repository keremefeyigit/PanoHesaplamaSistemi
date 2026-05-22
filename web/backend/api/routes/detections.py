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
    models_path   = os.path.join(root_dir, "core", "models.py")
    config_path   = os.path.join(root_dir, "config.py")

    if os.path.exists(detector_path) and os.path.exists(config_path):
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        # 1) Önce root core/models.py'yi "root_core.models" adıyla yükle
        #    object_detector.py içindeki "from core.models import Detection"
        #    backend'in kendi "core" paketiyle çakışıyor; bu alias bunu çözer.
        spec_m = importlib.util.spec_from_file_location("core.models", models_path)
        mod_m  = importlib.util.module_from_spec(spec_m)
        sys.modules["core.models"] = mod_m          # önce kaydet (circular import önlemi)
        spec_m.loader.exec_module(mod_m)

        # 2) Şimdi object_detector'ı yükle — artık core.models çözümleniyor
        import config
        spec_od = importlib.util.spec_from_file_location("root_core.object_detector", detector_path)
        od_module = importlib.util.module_from_spec(spec_od)
        spec_od.loader.exec_module(od_module)
        detector = od_module.ObjectDetector(config.config.detector)
        print("✓ ObjectDetector başarıyla yüklendi.")
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

def _fallback_contour_detection(img_cv):
    """
    OpenCV tabanlı kontur tespit fallback'i.
    YOLO model hiçbir şey bulamazsa, görüntüdeki en büyük dikdörtgensel bölgeyi bulur.
    Pano/tabela genellikle en büyük düz yüzeydir.
    """
    h, w = img_cv.shape[:2]
    
    # Gri tonlama + blur + kenar tespiti
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Adaptive threshold + Canny edge detection
    edges = cv2.Canny(blurred, 30, 100)
    
    # Morfolojik işlemler - kenarları birleştir
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.erode(edges, kernel, iterations=1)
    
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # Minimum boyut: Görüntünün en az %5'i kadar alan kaplamalı
    min_area = (h * w) * 0.05
    img_area = h * w
    
    best = None
    best_area = 0
    best_poly = None
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        
        # Konveks kabuk ve yaklaşık poligon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        
        # Minimum bounding rect
        x, y, bw, bh = cv2.boundingRect(cnt)
        rect_area = bw * bh
        
        # Dikdörtgensellik oranı - pano genellikle dikdörtgendir
        rectangularity = area / (rect_area + 1e-6)
        
        # En az %40 dikdörtgensel ve makul aspect ratio
        aspect_ratio = max(bw, bh) / (min(bw, bh) + 1e-6)
        if rectangularity > 0.4 and aspect_ratio < 10 and area > best_area:
            best_area = area
            best = (x, y, x + bw, y + bh)
            best_poly = approx.reshape(-1, 2)
    
    if best is None:
        # Hiçbir dikdörtgen bulunamadıysa, en büyük konturu kullan
        cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        if area > min_area:
            x, y, bw, bh = cv2.boundingRect(cnt)
            best = (x, y, x + bw, y + bh)
            best_area = area
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            best_poly = approx.reshape(-1, 2)
    
    if best is None:
        return None
    
    return {
        "bbox": best,
        "area": best_area,
        "polygon": best_poly,
        "confidence": 0.60,  # Kontur tespiti için sabit güven skoru
        "class_label": "Pano",
        "method": "contour",
    }


@router.post("/process-image")
async def process_image(
    file: UploadFile = File(...),
    org_id: Optional[str] = Form(None),
    gps_lat: Optional[float] = Form(39.9208),
    gps_lon: Optional[float] = Form(32.8541)
):
    """
    Görüntüdeki pano/tabela tespiti ve ölçüm.
    
    3 kademeli tespit stratejisi:
    1) YOLO özel model — eğitilmiş sınıflarla (billboard, box)
    2) YOLO düşük güven — herhangi bir sınıf, çok düşük eşikle
    3) OpenCV kontur tespiti — en büyük dikdörtgensel bölge
    """
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
    calculated_area = 0.0
    largest_det = None
    detection_method = "none"
    fallback_result = None

    if detector:
        # ──── Kademe 1: YOLO özel model ile standart tespit ────
        try:
            detections = detector.detect(img_cv)
            print(f"[Kademe 1] YOLO tespit sonucu: {len(detections)} adet")
            for d in detections:
                print(f"  → {d.class_label} conf={d.confidence:.3f} area={d.area}px")
        except Exception as e:
            print(f"[Kademe 1] YOLO detect hatası: {e}")
            detections = []

        # Hedef sınıfları filtrele (ama çok katı olma)
        valid_classes = ["billboard"]
        try:
            if hasattr(config, "config") and config.config.detector.target_classes:
                valid_classes = config.config.detector.target_classes
        except Exception:
            pass
        
        filtered = [d for d in detections if d.class_label in valid_classes]
        
        if not filtered and detections:
            # Hedef sınıf yoksa ama başka tespitler varsa, hepsini kabul et
            print(f"[Kademe 1] Hedef sınıf bulunamadı, tüm {len(detections)} tespit kabul ediliyor")
            filtered = detections
        
        if filtered:
            largest = max(filtered, key=lambda d: d.area)
            largest_det = largest
            detection_method = "yolo_custom"
            print(f"[Kademe 1] ✓ Tespit bulundu: {largest.class_label} conf={largest.confidence:.3f}")
        else:
            # ──── Kademe 2: Çok düşük güven eşiğiyle tekrar dene ────
            print("[Kademe 2] Düşük güven eşiğiyle tekrar deneniyor...")
            try:
                from ultralytics import YOLO
                model = detector._load_model()
                results = model.predict(
                    img_cv,
                    conf=0.05,  # Çok düşük eşik
                    iou=0.3,
                    imgsz=640,
                    verbose=False,
                )
                
                all_dets = []
                for result in results:
                    boxes = result.boxes
                    if boxes is None:
                        continue
                    for i in range(len(boxes)):
                        cls_id = int(boxes.cls[i].item())
                        label = result.names[cls_id] if result.names else str(cls_id)
                        xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                        c = float(boxes.conf[i].item())
                        
                        poly = None
                        if getattr(result, "masks", None) is not None and result.masks.xy is not None:
                            if len(result.masks.xy) > i:
                                poly = result.masks.xy[i]
                        
                        from core.models import Detection as Det
                        all_dets.append(Det(
                            bbox=tuple(xyxy),
                            confidence=c,
                            class_label=label,
                            class_id=cls_id,
                            polygon=poly,
                        ))
                
                print(f"[Kademe 2] Düşük eşikle {len(all_dets)} tespit bulundu")
                for d in all_dets:
                    print(f"  → {d.class_label} conf={d.confidence:.3f} area={d.area}px")
                
                if all_dets:
                    largest = max(all_dets, key=lambda d: d.area)
                    largest_det = largest
                    detection_method = "yolo_low_conf"
                    print(f"[Kademe 2] ✓ Tespit bulundu: {largest.class_label} conf={largest.confidence:.3f}")
            except Exception as e:
                print(f"[Kademe 2] Hata: {e}")

        # ──── Kademe 3: OpenCV Kontur Tespiti (Fallback) ────
        if largest_det is None:
            print("[Kademe 3] YOLO başarısız, OpenCV kontur tespiti deneniyor...")
            fallback_result = _fallback_contour_detection(img_cv)
            if fallback_result:
                detection_method = "contour_fallback"
                print(f"[Kademe 3] ✓ Kontur tespiti başarılı: bbox={fallback_result['bbox']}")
            else:
                print("[Kademe 3] ✗ Kontur tespiti de başarısız")
    else:
        # Detector yüklenememiş — sadece OpenCV dene
        print("[Uyarı] YOLO modeli yüklü değil. OpenCV kontur tespiti deneniyor...")
        fallback_result = _fallback_contour_detection(img_cv)
        if fallback_result:
            detection_method = "contour_only"

    # ──── Sonuçları birleştir ────
    if largest_det is not None:
        raw_class = largest_det.class_label
        conf = largest_det.confidence
        
        # Sınıf İsimlerini Türkçe Terimlere Dönüştür
        class_map = {"billboard": "Pano", "box": "Pano"}
        obj_class = class_map.get(raw_class, raw_class.capitalize())
        
        f_cam = 850.0
        W_real_assume = 3.0
        P = largest_det.pixel_width
        if P > 0:
            distance_m = round((W_real_assume * f_cam) / P, 1)
            width_m = W_real_assume
            H_px = largest_det.pixel_height
            height_m = round((distance_m * H_px) / f_cam, 2)
            
            if largest_det.polygon is not None and len(largest_det.polygon) >= 3:
                try:
                    pts = np.array(largest_det.polygon, dtype=np.float32)
                    pixel_area = cv2.contourArea(pts)
                    scale = distance_m / f_cam
                    real_area = pixel_area * (scale ** 2)
                    calculated_area = round(real_area, 3)
                except Exception as e:
                    print(f"Warning: Hassas alan hesabı yapılamadı: {e}")
                    calculated_area = round(width_m * height_m, 3)
            else:
                calculated_area = round(width_m * height_m, 3)

    elif fallback_result is not None:
        x1, y1, x2, y2 = fallback_result["bbox"]
        obj_class = fallback_result["class_label"]
        conf = fallback_result["confidence"]
        
        P = x2 - x1
        H_px = y2 - y1
        f_cam = 850.0
        W_real_assume = 3.0
        if P > 0:
            distance_m = round((W_real_assume * f_cam) / P, 1)
            width_m = W_real_assume
            height_m = round((distance_m * H_px) / f_cam, 2)
            calculated_area = round(width_m * height_m, 3)
    else:
        raise HTTPException(
            status_code=422,
            detail="Resimde pano tespit edilemedi. Lütfen panonun tamamının göründüğü, "
                   "net ve yakın bir fotoğraf çekin. Işık koşullarının yeterli olduğundan emin olun."
        )

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
    
    bbox_list = None
    polygon_list = None
    
    if largest_det is not None:
        if largest_det.bbox is not None:
            bbox_list = [int(x) for x in largest_det.bbox]
        if largest_det.polygon is not None:
            try:
                if hasattr(largest_det.polygon, "tolist"):
                    polygon_list = largest_det.polygon.tolist()
                else:
                    polygon_list = [[float(p[0]), float(p[1])] for p in largest_det.polygon]
            except Exception:
                polygon_list = None
    elif fallback_result is not None:
        bbox_list = [int(x) for x in fallback_result["bbox"]]
        if fallback_result["polygon"] is not None:
            try:
                if hasattr(fallback_result["polygon"], "tolist"):
                    polygon_list = fallback_result["polygon"].tolist()
                else:
                    polygon_list = [[float(p[0]), float(p[1])] for p in fallback_result["polygon"]]
            except Exception:
                polygon_list = None
    
    # Tüm numeric değerleri native Python tiplerine dönüştür (numpy serialization fix)
    conf = float(conf)
    distance_m = float(distance_m)
    width_m = float(width_m)
    height_m = float(height_m)
    calculated_area = float(calculated_area)
    
    new_detection = {
        "id": f"det-{uuid.uuid4().hex[:6]}",
        "session_id": session_id,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "class_label": obj_class,
        "confidence": conf,
        "distance_m": distance_m,
        "real_width_m": width_m,
        "real_height_m": height_m,
        "area_m2": calculated_area,
        "sign_lat": gps_lat,
        "sign_lon": gps_lon,
        "vehicle_lat": gps_lat,
        "vehicle_lon": gps_lon,
        "source_camera": "webcam",
        "measurement_method": detection_method,
        "thumbnail_path": None,
        "is_shared_with": [org_id] if org_id else [],
        "bbox": bbox_list,
        "polygon": polygon_list,
    }
    
    _DETECTIONS.insert(0, new_detection)
    
    if org_id:
        share_session_with_org(session_id, org_id, user.get("id"))
    
    print(f"[Sonuç] Tespit: {obj_class} | Güven: {conf:.2f} | Yöntem: {detection_method} | Alan: {calculated_area}m²")
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
