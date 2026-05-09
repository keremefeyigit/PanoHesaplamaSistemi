"""
core/models.py
==============
Paylaşılan veri modelleri — OpenCV veya YOLO gerektirmez.
Bu sayede birim testler donanım/paket olmadan çalışabilir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Detection:
    """Tek bir YOLO tespit sonucunu temsil eden veri sınıfı."""
    # Bounding box — piksel koordinatları (x_min, y_min, x_max, y_max)
    bbox: tuple[int, int, int, int]
    # Güven skoru [0.0 – 1.0]
    confidence: float
    # Sınıf etiketi
    class_label: str
    # Sınıf kimliği
    class_id: int
    # Takip kimliği (tracker etkinleştirilmişse)
    track_id: Optional[int] = None
    # Kaynak kamera ("wide" | "narrow")
    source_camera: str = "wide"
    # Tespit zamanı [Unix timestamp]
    timestamp: float = field(default_factory=time.time)

    @property
    def bbox_center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def pixel_width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def pixel_height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return self.pixel_width * self.pixel_height
