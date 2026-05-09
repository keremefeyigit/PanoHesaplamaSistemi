"""
web/backend/api/routes/stream.py
==================================
Canlı görüntü ve tespit akışı.

İki endpoint:
  GET /api/stream/sse        — Server-Sent Events: anlık tespit JSON akışı
  GET /api/stream/frame      — MJPEG: kameranın JPEG kareleri (simüle)
  GET /api/stream/calibrate  — Tek kare + simüle hesaplama sonucu
"""
from __future__ import annotations

import asyncio
import base64
import io
import math
import random
import time
from typing import AsyncGenerator

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.deps import get_current_user

router = APIRouter()
rng = random.Random()

# ─── Simüle Kare Üretici ─────────────────────────────────────────────────────

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def _generate_mock_frame(
    width: int = 960,
    height: int = 540,
    detection: dict | None = None,
) -> bytes:
    """
    Simüle bir kamera karesi üretir.
    Gerçek kamera bağlıyken bu fonksiyon gerçek kare ile değiştirilir.
    """
    if not _CV2_AVAILABLE:
        # cv2 yoksa 1×1 siyah JPEG döndür
        return b""

    # Koyu gri arka plan + simüle yol çizgileri
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (30, 32, 35)

    # Yol çizgisi efekti
    offset = int(time.time() * 60) % height
    for y in range(-height, height, 80):
        y_pos = (y + offset) % height
        cv2.line(frame, (width // 2 - 5, y_pos), (width // 2 - 5, y_pos + 40), (80, 80, 80), 2)
        cv2.line(frame, (width // 2 + 5, y_pos), (width // 2 + 5, y_pos + 40), (80, 80, 80), 2)

    if detection:
        x1, y1, x2, y2 = detection["bbox"]
        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 230, 100), 2)
        # Köşe çentikleri (profesyonel görünüm)
        tick = 15
        for cx, cy, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
            cv2.line(frame, (cx, cy), (cx + dx*tick, cy), (0, 230, 100), 3)
            cv2.line(frame, (cx, cy), (cx, cy + dy*tick), (0, 230, 100), 3)

        # Label arka plan
        label = f"{detection['class_label']} {detection['confidence']:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), (0, 230, 100), -1)
        cv2.putText(frame, label, (x1 + 4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 1, cv2.LINE_AA)

        # Mesafe ve alan göstergesi
        info = f"D:{detection['distance_m']:.1f}m  {detection['width_m']:.1f}x{detection['height_m']:.1f}m"
        cv2.putText(frame, info, (x1, y2 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1, cv2.LINE_AA)

    # Zaman damgası
    ts = time.strftime("%H:%M:%S")
    cv2.putText(frame, f"SIM {ts}", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1, cv2.LINE_AA)
    cv2.putText(frame, "CANLI IZLEME", (width - 140, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 180, 80), 1, cv2.LINE_AA)

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return jpeg.tobytes()


def _random_detection() -> dict:
    """Rastgele simüle tespit verisi üretir."""
    classes = ["tabela", "pano", "megalight", "raket", "afis"]
    cls = rng.choice(classes)
    x1 = rng.randint(150, 500)
    y1 = rng.randint(100, 300)
    w = rng.randint(120, 280)
    h = rng.randint(60, 160)
    dist = round(rng.uniform(8.0, 60.0), 1)
    real_w = round(rng.uniform(1.5, 5.0), 2)
    real_h = round(rng.uniform(0.8, 2.5), 2)
    return {
        "class_label": cls,
        "confidence": round(rng.uniform(0.6, 0.97), 3),
        "bbox": [x1, y1, x1 + w, y1 + h],
        "distance_m": dist,
        "width_m": real_w,
        "height_m": real_h,
        "area_m2": round(real_w * real_h, 3),
        "gps_lat": round(39.9208 + rng.uniform(-0.005, 0.005), 6),
        "gps_lon": round(32.8541 + rng.uniform(-0.005, 0.005), 6),
        "timestamp": time.time(),
        "method": rng.choice(["similar_triangles", "disparity", "combined"]),
    }


# ─── SSE: Tespit Metadata Akışı ──────────────────────────────────────────────

async def _detection_event_generator() -> AsyncGenerator[str, None]:
    """Saniyede ~1 tespit yayınlar (simülasyon)."""
    det = None
    frame_n = 0
    while True:
        frame_n += 1
        # Her ~3 saniyede yeni tespit
        if frame_n % 3 == 0:
            det = _random_detection()
            import json
            yield f"data: {json.dumps(det)}\n\n"
        await asyncio.sleep(1)


@router.get("/sse")
async def detection_sse(user: dict = Depends(get_current_user)):
    """Server-Sent Events akışı — anlık tespit JSON'ları."""
    return StreamingResponse(
        _detection_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── MJPEG: Video Akışı ──────────────────────────────────────────────────────

async def _mjpeg_generator() -> AsyncGenerator[bytes, None]:
    """MJPEG formatında JPEG kareleri yayınlar (15 FPS simülasyon)."""
    det = _random_detection()
    frame_n = 0
    while True:
        frame_n += 1
        if frame_n % 45 == 0:   # her 3 saniyede tespit değiştir
            det = _random_detection()
        frame = _generate_mock_frame(detection=det)
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        await asyncio.sleep(1 / 15)   # 15 FPS


@router.get("/frame")
async def video_stream(user: dict = Depends(get_current_user)):
    """MJPEG akışı — tarayıcıda <img src="/api/stream/frame"> ile kullanılır."""
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ─── Kalibrasyon Test Endpoint'i ─────────────────────────────────────────────

class CalibrateRequest(BaseModel):
    pixel_width: int
    known_real_width_m: float = 3.0
    focal_length_px: float = 850.0


@router.post("/calibrate")
async def calibrate_test(body: CalibrateRequest, _: dict = Depends(get_current_user)):
    """
    Kullanıcı arayüzden piksel genişliği girince anlık mesafe hesaplar.
    D = (W × f) / P
    """
    if body.pixel_width <= 0:
        return {"error": "Piksel genişliği 0'dan büyük olmalı"}
    D = (body.known_real_width_m * body.focal_length_px) / body.pixel_width
    W_back = (D * body.pixel_width) / body.focal_length_px
    return {
        "distance_m": round(D, 3),
        "real_width_m": round(W_back, 3),
        "formula": f"D = ({body.known_real_width_m} × {body.focal_length_px}) / {body.pixel_width}",
        "pixel_width": body.pixel_width,
    }
