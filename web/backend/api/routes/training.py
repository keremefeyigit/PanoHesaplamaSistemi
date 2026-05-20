"""
web/backend/api/routes/training.py
====================================
YOLO eğitimi için veri yönetimi ve eğitim yönetimi endpoint'leri.

- Fotoğraf yükleme (raw images)
- Fotoğraf listeleme / silme
- Eğitim başlatma / durum sorgulama
"""
from __future__ import annotations

import os
import uuid
import shutil
import subprocess
import time
import json
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, File, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import cv2
import numpy as np

router = APIRouter()

# ─── Dizin Sabitleri ──────────────────────────────────────────────────────────
ROOT_DIR       = Path(__file__).resolve().parents[4]   # proje kökü
TRAINING_DIR   = ROOT_DIR / "training_data"
RAW_DIR        = TRAINING_DIR / "images" / "raw"
MODELS_DIR     = ROOT_DIR / "models"
TRAIN_LOG_FILE = TRAINING_DIR / "training_log.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Eğitim durumu (in-memory, process tabanlı) ───────────────────────────────
_training_process: Optional[subprocess.Popen] = None
_training_status: dict = {
    "state": "idle",          # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "image_count": 0,
    "log_lines": [],
    "model_ready": False,
    "error": None,
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


# ─── Yardımcı ─────────────────────────────────────────────────────────────────

def _count_raw_images() -> int:
    return len([f for f in RAW_DIR.iterdir() if f.suffix.lower() in ALLOWED_EXTENSIONS])


def _image_info(path: Path) -> dict:
    stat = path.stat()
    return {
        "filename": path.name,
        "size_kb": round(stat.st_size / 1024, 1),
        "uploaded_at": stat.st_mtime,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/images")
async def list_images():
    """Yüklenmiş ham eğitim fotoğraflarını listele."""
    images = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.suffix.lower() in ALLOWED_EXTENSIONS:
                images.append(_image_info(f))
    return {"total": len(images), "images": images}


@router.post("/upload")
async def upload_training_image(file: UploadFile = File(...)):
    """
    Eğitim fotoğrafı yükle.
    Otomatik olarak training_data/images/raw/ klasörüne kaydeder.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen format: {suffix}. JPG, PNG, WEBP kabul edilir.")

    unique_name = f"pano_{uuid.uuid4().hex[:8]}{suffix}"
    dest = RAW_DIR / unique_name

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Boş dosya yüklenemez.")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dosya 20 MB sınırını aşıyor.")

    # Geçerli resim mi kontrol et
    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Geçersiz resim dosyası.")

    with open(dest, "wb") as f_out:
        f_out.write(content)

    total = _count_raw_images()
    return {
        "message": "Fotoğraf başarıyla yüklendi.",
        "filename": unique_name,
        "size_kb": round(len(content) / 1024, 1),
        "total_images": total,
    }


@router.delete("/images/{filename}")
async def delete_image(filename: str):
    """Belirli bir eğitim fotoğrafını sil."""
    target = RAW_DIR / filename
    if not target.exists() or target.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Fotoğraf bulunamadı.")
    target.unlink()
    return {"message": f"{filename} silindi.", "total_images": _count_raw_images()}


@router.get("/images/{filename}/preview")
async def preview_image(filename: str):
    """Fotoğrafı önizleme için döndür."""
    target = RAW_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Fotoğraf bulunamadı.")
    return FileResponse(str(target))


@router.get("/status")
async def training_status():
    """Eğitim durumunu sorgula."""
    model_exists = (MODELS_DIR / "yolov8n_tabela.pt").exists()
    return {
        **_training_status,
        "total_images": _count_raw_images(),
        "model_ready": model_exists,
    }


@router.post("/start")
async def start_training(background_tasks: BackgroundTasks, epochs: int = Form(50)):
    """
    YOLO eğitimini başlat.
    Fotoğrafları otomatik olarak train/val setlerine böler,
    dataset.yaml oluşturur ve 'yolo train' komutunu çalıştırır.
    """
    global _training_status

    if _training_status["state"] == "running":
        raise HTTPException(status_code=409, detail="Eğitim zaten devam ediyor.")

    total = _count_raw_images()
    if total < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Eğitim için en az 5 fotoğraf gereklidir. Mevcut: {total}"
        )

    epochs = max(10, min(epochs, 300))

    background_tasks.add_task(_run_training, epochs)
    _training_status.update({
        "state": "running",
        "started_at": time.time(),
        "finished_at": None,
        "image_count": total,
        "log_lines": [f"Eğitim başlatıldı. {total} fotoğraf, {epochs} epoch."],
        "model_ready": False,
        "error": None,
    })

    return {"message": f"Eğitim başlatıldı! {total} fotoğraf, {epochs} epoch.", "epochs": epochs}


# ─── Arka Plan Eğitim Fonksiyonu ──────────────────────────────────────────────

def _run_training(epochs: int):
    """Arka planda YOLO eğitimini hazırlar ve çalıştırır."""
    global _training_status
    import random

    try:
        _log("Veri seti hazırlanıyor...")

        # Mevcut train/val klasörlerini temizle
        train_img = TRAINING_DIR / "datasets" / "train" / "images"
        train_lbl = TRAINING_DIR / "datasets" / "train" / "labels"
        val_img   = TRAINING_DIR / "datasets" / "val" / "images"
        val_lbl   = TRAINING_DIR / "datasets" / "val" / "labels"
        for d in [train_img, train_lbl, val_img, val_lbl]:
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)

        # Ham resimleri listele ve karıştır
        raw_images = sorted([
            f for f in RAW_DIR.iterdir()
            if f.suffix.lower() in ALLOWED_EXTENSIONS
        ])
        random.shuffle(raw_images)

        # %80 train, %20 val
        split_idx = max(1, int(len(raw_images) * 0.8))
        train_files = raw_images[:split_idx]
        val_files   = raw_images[split_idx:]

        # Auto-label: tüm resim = 1 pano (class 0), resmin tüm alanı
        # Kullanıcı yalnızca pano fotoğrafı yüklediğinden bu geçerli bir başlangıç
        def write_auto_label(img_path: Path, label_dir: Path):
            lbl_path = label_dir / (img_path.stem + ".txt")
            # YOLO formatı: class cx cy w h (normalize 0-1)
            # Resmin tamamı = pano
            lbl_path.write_text("0 0.5 0.5 1.0 1.0\n")

        for f in train_files:
            shutil.copy(f, train_img / f.name)
            write_auto_label(f, train_lbl)

        for f in val_files:
            shutil.copy(f, val_img / f.name)
            write_auto_label(f, val_lbl)

        _log(f"Train: {len(train_files)} | Val: {len(val_files)} resim")

        # dataset.yaml oluştur
        yaml_path = TRAINING_DIR / "dataset.yaml"
        yaml_content = f"""# YOLO Pano Dataset
path: {TRAINING_DIR / 'datasets'}
train: train/images
val:   val/images

nc: 1
names: ['pano']
"""
        yaml_path.write_text(yaml_content)
        _log("dataset.yaml oluşturuldu.")

        # YOLO eğitim komutu
        # Mevcut yolov8n.pt modelini fine-tune ediyoruz
        base_model = ROOT_DIR / "yolov8n.pt"
        if not base_model.exists():
            base_model = "yolov8n.pt"  # ultralytics otomatik indirir

        cmd = [
            "python", "-c",
            f"""
import sys
sys.path.insert(0, '{ROOT_DIR}')
from ultralytics import YOLO
model = YOLO('{base_model}')
results = model.train(
    data='{yaml_path}',
    epochs={epochs},
    imgsz=640,
    batch=4,
    name='pano_model',
    project='{TRAINING_DIR}/runs',
    device='cpu',
    workers=2,
    patience=15,
    save=True,
    verbose=True,
)
# En iyi modeli models/ klasörüne kopyala
import shutil
best = '{TRAINING_DIR}/runs/pano_model/weights/best.pt'
shutil.copy(best, '{MODELS_DIR}/yolov8n_tabela.pt')
print('MODEL_SAVED_OK')
"""
        ]

        _log("YOLO eğitimi başlıyor...")
        import subprocess
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT_DIR),
        )

        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                stripped = line.strip()
                if stripped:
                    _log(stripped)

        ret = proc.wait()

        if ret == 0 and (MODELS_DIR / "yolov8n_tabela.pt").exists():
            _training_status.update({
                "state": "done",
                "finished_at": time.time(),
                "model_ready": True,
            })
            _log("✅ Eğitim tamamlandı! Model kaydedildi: models/yolov8n_tabela.pt")
        else:
            raise RuntimeError(f"Eğitim başarısız. Çıkış kodu: {ret}")

    except Exception as exc:
        _training_status.update({
            "state": "error",
            "finished_at": time.time(),
            "error": str(exc),
        })
        _log(f"❌ Hata: {exc}")


def _log(msg: str):
    """Eğitim log listesine mesaj ekle (son 200 satır tutulur)."""
    global _training_status
    _training_status["log_lines"].append(msg)
    if len(_training_status["log_lines"]) > 200:
        _training_status["log_lines"] = _training_status["log_lines"][-200:]
