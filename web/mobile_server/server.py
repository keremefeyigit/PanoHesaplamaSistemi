"""
web/mobile_server/server.py
============================
FastAPI + WebSocket sunucusu — iPhone kamera akışı ile tabela ölçümü.

Mimari:
    iPhone Safari → HTTPS → WebSocket /ws/stream
        → base64 JPEG frame → YOLO (veya mock) → DistanceCalculator
        → sonuç JSON → iPhone overlay

    REST: GET/DELETE /api/measurements → SQLite

Çalıştırma:
    python web/mobile_server/server.py            # HTTP  (sadece PC tarayıcı testi)
    python web/mobile_server/server.py --https    # HTTPS (iPhone için — ilk seferinde sertifika üretir)

⚠️  iPhone için HTTPS zorunlu: Safari, HTTP üzerinden kameraya izin vermez.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Proje root'u path'e ekle ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mobile_server")

# ── Yollar ────────────────────────────────────────────────────────────────────
STATIC_DIR  = Path(__file__).parent / "static"
DB_PATH     = Path(__file__).parent / "measurements.db"
THUMB_DIR   = Path(__file__).parent / "thumbnails"
CERT_DIR    = Path(__file__).parent / "certs"

STATIC_DIR.mkdir(exist_ok=True)
THUMB_DIR.mkdir(exist_ok=True)
CERT_DIR.mkdir(exist_ok=True)

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Tabela Ölçüm Sistemi", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/thumbnails", StaticFiles(directory=str(THUMB_DIR)), name="thumbnails")

# ── SQLite ────────────────────────────────────────────────────────────────────
def init_db() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT,
            width_m     REAL,
            height_m    REAL,
            area_m2     REAL,
            distance_m  REAL,
            confidence  REAL,
            latitude    REAL,
            longitude   REAL,
            note        TEXT,
            thumb_path  TEXT,
            saved_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
        )
    """)
    con.commit()
    con.close()
    logger.info("SQLite DB hazır: %s", DB_PATH)

init_db()

# ── YOLO / Mock Detector ──────────────────────────────────────────────────────

class _MockDetector:
    """YOLO yüklü değilken çalışan sahte tespit — formüller gerçek."""
    def detect(self, frame: np.ndarray, distance_m: float):
        h, w = frame.shape[:2]
        # Görüntü merkezinde makul boyutlu bir bounding box
        margin_x, margin_y = int(w * 0.15), int(h * 0.20)
        bbox = (margin_x, margin_y, w - margin_x, h - margin_y)
        return [{
            "bbox":       bbox,
            "label":      "tabela [MOCK]",
            "confidence": 0.72,
        }]

    @property
    def mode(self): return "mock"


class _YOLODetector:
    def __init__(self):
        from ultralytics import YOLO  # type: ignore
        self._model = YOLO("yolov8n.pt")
        self._model.to("cpu")

    def detect(self, frame: np.ndarray, distance_m: float):
        results = self._model.predict(
            frame, conf=0.25, iou=0.45, imgsz=640, verbose=False
        )
        out = []
        for r in results:
            for i in range(len(r.boxes)):
                xyxy = r.boxes.xyxy[i].cpu().numpy().astype(int)
                out.append({
                    "bbox":       tuple(int(v) for v in xyxy),
                    "label":      r.names[int(r.boxes.cls[i])],
                    "confidence": float(r.boxes.conf[i]),
                })
        return out

    @property
    def mode(self): return "yolo"


def _build_detector():
    try:
        det = _YOLODetector()
        logger.info("YOLO detektörü yüklendi ✅")
        return det
    except Exception as e:
        logger.warning("YOLO yüklenemedi (%s) → mock modu aktif", e)
        return _MockDetector()

detector = _build_detector()

# ── DistanceCalculator ────────────────────────────────────────────────────────
try:
    from config import config as sys_config
    from core.distance_calculator import DistanceCalculator, _real_dimension
    calc = DistanceCalculator(sys_config.cameras)
    focal_px = sys_config.cameras.wide.focal_length_px
    logger.info("DistanceCalculator yüklendi (f=%.0fpx)", focal_px)
except Exception as e:
    logger.warning("DistanceCalculator yüklenemedi: %s → basit formül kullanılacak", e)
    calc = None
    focal_px = 850.0

def _compute_dimensions(bbox: tuple, distance_m: float, img_shape: tuple) -> tuple[float, float]:
    """Bounding box piksellerinden gerçek boyut hesapla."""
    x1, y1, x2, y2 = bbox
    px_w = max(x2 - x1, 1)
    px_h = max(y2 - y1, 1)
    real_w = (distance_m * px_w) / focal_px
    real_h = (distance_m * px_h) / focal_px
    return round(real_w, 3), round(real_h, 3)

# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        return JSONResponse({"error": "index.html bulunamadı"}, status_code=404)
    return FileResponse(str(html_path))

@app.get("/api/measurements")
async def list_measurements():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM measurements ORDER BY saved_at DESC LIMIT 200"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.delete("/api/measurements/{mid}")
async def delete_measurement(mid: int):
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM measurements WHERE id = ?", (mid,))
    con.commit()
    con.close()
    return {"ok": True}

# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    client = ws.client
    logger.info("WebSocket bağlandı: %s", client)
    current_distance = 5.0

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            # ── Mesafe güncelleme ──────────────────────────────────────────
            if mtype == "set_distance":
                current_distance = float(msg.get("distance_m", current_distance))
                await ws.send_text(json.dumps({"type": "ack", "message": f"📏 Mesafe: {current_distance}m"}))

            # ── Kare işleme ───────────────────────────────────────────────
            elif mtype == "frame":
                t0 = time.perf_counter()
                dist = float(msg.get("distance_m", current_distance))

                # base64 → numpy
                b64 = msg["frame"].split(",", 1)[-1]
                img_bytes = base64.b64decode(b64)
                arr = np.frombuffer(img_bytes, dtype=np.uint8)

                try:
                    import cv2
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                except ImportError:
                    # cv2 yoksa PIL kullan
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(img_bytes))
                    frame = np.array(img)[:, :, ::-1]  # RGB→BGR

                if frame is None:
                    continue

                img_h, img_w = frame.shape[:2]
                raw_dets = detector.detect(frame, dist)

                detections = []
                for d in raw_dets:
                    w_m, h_m = _compute_dimensions(d["bbox"], dist, frame.shape)
                    detections.append({
                        "bbox":       list(d["bbox"]),
                        "label":      d["label"],
                        "confidence": round(d["confidence"], 3),
                        "width_m":    w_m,
                        "height_m":   h_m,
                        "area_m2":    round(w_m * h_m, 3),
                        "distance_m": dist,
                    })

                elapsed_ms = str(round((time.perf_counter() - t0) * 1000))
                await ws.send_text(json.dumps({
                    "type":          "result",
                    "processing_ms": elapsed_ms,
                    "img_w":         img_w,
                    "img_h":         img_h,
                    "detections":    detections,
                    "mode":          detector.mode,
                }))

            # ── Kaydet ────────────────────────────────────────────────────
            elif mtype == "save":
                thumb_path = None
                thumb_b64 = msg.get("thumb_b64", "")
                if thumb_b64:
                    try:
                        b64data = thumb_b64.split(",", 1)[-1]
                        fname = f"thumb_{int(time.time()*1000)}.jpg"
                        fpath = THUMB_DIR / fname
                        fpath.write_bytes(base64.b64decode(b64data))
                        thumb_path = f"/thumbnails/{fname}"
                    except Exception:
                        pass

                w_m = float(msg.get("width_m", 0))
                h_m = float(msg.get("height_m", 0))

                con = sqlite3.connect(DB_PATH)
                cur = con.execute(
                    """INSERT INTO measurements
                       (label, width_m, height_m, area_m2, distance_m,
                        confidence, latitude, longitude, note, thumb_path)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        msg.get("label", "tabela"),
                        w_m, h_m, round(w_m * h_m, 3),
                        msg.get("distance_m"), msg.get("confidence"),
                        msg.get("latitude"),   msg.get("longitude"),
                        msg.get("note", ""),   thumb_path,
                    )
                )
                con.commit()
                new_id = cur.lastrowid
                con.close()
                logger.info("Kaydedildi #%d: %.2f×%.2fm @ GPS(%.5f,%.5f)",
                            new_id, w_m, h_m,
                            msg.get("latitude") or 0, msg.get("longitude") or 0)
                await ws.send_text(json.dumps({
                    "type":    "saved",
                    "message": f"#{new_id} kaydedildi — {w_m:.2f}×{h_m:.2f}m",
                    "id":      new_id,
                }))

    except WebSocketDisconnect:
        logger.info("WebSocket kapandı: %s", client)
    except Exception as e:
        logger.error("WebSocket hata: %s", e, exc_info=True)

# ── HTTPS Sertifika ───────────────────────────────────────────────────────────

def ensure_cert() -> tuple[Path, Path]:
    """Self-signed sertifika oluşturur (iPhone için HTTPS zorunlu)."""
    cert = CERT_DIR / "cert.pem"
    key  = CERT_DIR / "key.pem"
    if cert.exists() and key.exists():
        return cert, key
    logger.info("Sertifika üretiliyor (openssl)…")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(key), "-out", str(cert),
        "-days", "365", "-nodes",
        "-subj", "/C=TR/ST=Ankara/O=PanoHesap/CN=localhost",
    ], check=True, capture_output=True)
    logger.info("Sertifika hazır: %s", cert)
    return cert, key

# ── Giriş noktası ─────────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--https", action="store_true", help="HTTPS modunda çalıştır (iPhone için)")
    parser.add_argument("--host",  default="0.0.0.0",  help="Bind adresi")
    parser.add_argument("--port",  default=8765, type=int, help="Port")
    args = parser.parse_args()

    local_ip = _get_local_ip()
    proto     = "https" if args.https else "http"

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║   Tabela Ölçüm Sistemi — Mobil Sunucu           ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Mod        : {'HTTPS (iPhone ✅)' if args.https else 'HTTP (sadece PC)'}")
    print(f"  PC         : {proto}://localhost:{args.port}")
    print(f"  iPhone URL : {proto}://{local_ip}:{args.port}")
    print()
    if args.https:
        print("  ⚠️  iPhone'da ilk açılışta 'Güvenilmeyen sertifika' uyarısı çıkar.")
        print("     Safari → Gelişmiş → Devam Et'e tıkla.")
        print()

    ssl_kwargs = {}
    if args.https:
        cert, key = ensure_cert()
        ssl_kwargs = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        log_level="info",
        app_dir=str(Path(__file__).parent),
        **ssl_kwargs,
    )
