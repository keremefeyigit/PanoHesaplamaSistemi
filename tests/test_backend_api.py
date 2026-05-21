"""
tests/test_backend_api.py
==========================
FastAPI backend rotaları için entegrasyon/birim testleri.
"""

from fastapi.testclient import TestClient
import numpy as np
import pytest
from unittest.mock import MagicMock

# Set sys.path to prioritize backend directory
import sys
import os

original_path = list(sys.path)
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_dir = os.path.join(root_dir, "web", "backend")
sys.path.insert(0, backend_dir)

# Import main first to let it override sys.modules["core.models"] with root's core.models
from main import app
from core.models import Detection

# Restore original path to prevent leak into other test files
sys.path = original_path

# Clean up module cache to prevent shadowing of other test modules
for mod_name in list(sys.modules.keys()):
    if mod_name == "core" or mod_name.startswith("core."):
        del sys.modules[mod_name]

client = TestClient(app)

def test_health_endpoint():
    """/api/health endpoint'inin düzgün çalıştığını doğrular."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "tabela-backend"}

def test_process_image_no_detections(monkeypatch):
    """Resimde pano bulunamadığında 422 hata kodu döndüğünü doğrular."""
    # Mock detector
    mock_detector = MagicMock()
    mock_detector.detect.return_value = []
    
    # detections modülündeki detector nesnesini mock ile değiştir
    from api.routes import detections as detections_route
    monkeypatch.setattr(detections_route, "detector", mock_detector)
    
    # 10x10 geçerli bir resim verisi
    import cv2
    _, img_encoded = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))
    img_bytes = img_encoded.tobytes()
    files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
    
    response = client.post("/api/detections/process-image", files=files)
    assert response.status_code == 422
    assert "Resimde pano tespit edilemedi" in response.json()["detail"]

def test_process_image_with_detection_and_polygon(monkeypatch):
    """Pano tespit edildiğinde ve poligon maskesi olduğunda alanın doğru hesaplandığını doğrular."""
    # Sahte bir Detection nesnesi (poligon maskeli)
    mock_detection = Detection(
        bbox=(50, 50, 150, 150),  # Genişlik: 100px, Yükseklik: 100px
        confidence=0.95,
        class_label="billboard",
        class_id=1,
        polygon=[[50, 50], [150, 50], [150, 150], [50, 150]], # 100x100 kare
        source_camera="wide"
    )
    
    mock_detector = MagicMock()
    mock_detector.detect.return_value = [mock_detection]
    
    from api.routes import detections as detections_route
    monkeypatch.setattr(detections_route, "detector", mock_detector)
    
    # 1x1 piksel siyah bir resim (geçerli bir resim verisi sağlamak için)
    import cv2
    _, img_encoded = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))
    img_bytes = img_encoded.tobytes()
    
    files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
    response = client.post("/api/detections/process-image", files=files)
    
    assert response.status_code == 200
    res_data = response.json()
    assert "detection" in res_data
    det = res_data["detection"]
    assert det["class_label"] == "Tabela"
    assert det["confidence"] == 0.95
    # f = 850, W_real_assume = 3.0, P = 100
    # distance_m = (3.0 * 850) / 100 = 25.5
    assert det["distance_m"] == 25.5
    # scale = 25.5 / 850.0 = 0.03
    # pixel_area of 100x100 square is 10000
    # real_area = 10000 * (0.03 ** 2) = 10000 * 0.0009 = 9.0 m2
    assert det["area_m2"] == 9.0
