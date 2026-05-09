"""
core/object_detector.py
========================
ObjectDetector — YOLOv8/v10 tabanlı tabela tespiti.

Geniş ve dar açı kameralardan gelen kareleri alır, üzerinde YOLO çalıştırır,
tespit edilen nesnelerin bounding box koordinatlarını ve güven skorlarını döndürür.
Jetson Orin üzerinde TensorRT ile çalışacak şekilde tasarlanmıştır.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import DetectorConfig
# Detection modeli cv2-bağımsız modelden import edilir
from core.models import Detection  # noqa: F401 (re-export)


logger = logging.getLogger(__name__)


class ObjectDetector:
    """
    YOLOv8/v10 modeli üzerinden nesne tespiti yapan sınıf.

    Hem geniş hem dar açı kamera karelerini kabul eder.
    Model ilk çağrıda lazy-load edilir.

    Kullanım:
        detector = ObjectDetector(config.detector)
        detections = detector.detect(wide_frame, camera="wide")
    """

    def __init__(self, cfg: DetectorConfig) -> None:
        self._cfg = cfg
        self._model = None           # Lazy initialization
        self._frame_count = 0        # Frame skip sayacı
        logger.info("ObjectDetector oluşturuldu. Model: %s", cfg.model_path)

    # ─── Ana Tespit Metodu ────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        camera: str = "wide",
        use_tracker: bool = False,
    ) -> list[Detection]:
        """
        Verilen karede tabela tespiti yapar.

        Args:
            frame:       BGR formatında OpenCV karesi.
            camera:      Kamera etiketi ("wide" | "narrow").
            use_tracker: True ise ByteTrack/BotSort ile takip kimliği atar.

        Returns:
            Detection nesnelerinin listesi.
        """
        model = self._load_model()
        self._frame_count += 1

        t0 = time.perf_counter()
        if use_tracker:
            results = model.track(
                frame,
                conf=self._cfg.confidence_threshold,
                iou=self._cfg.iou_threshold,
                imgsz=self._cfg.img_size,
                persist=True,
                tracker=self._cfg.tracker,
                verbose=False,
            )
        else:
            results = model.predict(
                frame,
                conf=self._cfg.confidence_threshold,
                iou=self._cfg.iou_threshold,
                imgsz=self._cfg.img_size,
                verbose=False,
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        detections = self._parse_results(results, camera, use_tracker)
        logger.debug(
            "[%s] %d tespit, %.1f ms", camera, len(detections), elapsed_ms
        )
        return detections

    def detect_dual(
        self,
        wide_frame: np.ndarray,
        narrow_frame: np.ndarray,
        use_tracker: bool = True,
    ) -> tuple[list[Detection], list[Detection]]:
        """
        Geniş ve dar açı kareleri arka arkaya işler.

        Returns:
            (wide_detections, narrow_detections)
        """
        wide_dets = self.detect(wide_frame, camera="wide", use_tracker=use_tracker)
        narrow_dets = self.detect(narrow_frame, camera="narrow", use_tracker=use_tracker)
        return wide_dets, narrow_dets

    # ─── Görselleştirme ───────────────────────────────────────────────────────

    @staticmethod
    def draw_detections(
        frame: np.ndarray,
        detections: list[Detection],
        color: tuple[int, int, int] = (0, 255, 80),
    ) -> np.ndarray:
        """
        Tespit sonuçlarını kare üzerine çizer (debug/görselleştirme için).

        Args:
            frame:      Orijinal BGR karesi (kopyalanır, değiştirilmez).
            detections: Çizilecek tespit listesi.
            color:      BGR renk tonu.

        Returns:
            Annotasyon eklenmiş kare kopyası.
        """
        annotated = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_label} {det.confidence:.2f}"
            if det.track_id is not None:
                label = f"#{det.track_id} {label}"
            cv2.putText(
                annotated,
                label,
                (x1, max(y1 - 6, 0)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                1,
                cv2.LINE_AA,
            )
        return annotated

    # ─── Yardımcı Metotlar ────────────────────────────────────────────────────

    def _load_model(self):
        """Modeli ilk kullanımda lazy-load eder."""
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "ultralytics paketi yüklü değil. "
                "Kurulum: pip install ultralytics"
            ) from exc

        model_path = self._cfg.model_path
        if not Path(model_path).exists():
            logger.warning(
                "Model dosyası bulunamadı: %s. "
                "YOLOv8n varsayılan modeli indiriliyor...",
                model_path,
            )
            model_path = "yolov8n.pt"

        self._model = YOLO(str(model_path))
        self._model.to(self._cfg.device)
        logger.info("Model yüklendi: %s (%s)", model_path, self._cfg.device)
        return self._model

    def _parse_results(
        self,
        results,
        camera: str,
        use_tracker: bool,
    ) -> list[Detection]:
        """YOLO sonuç objesini Detection listesine dönüştürür."""
        detections: list[Detection] = []
        ts = time.time()

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                label = (
                    result.names[cls_id]
                    if result.names
                    else str(cls_id)
                )
                # Yalnızca hedef sınıfları filtrele
                if (
                    self._cfg.target_classes
                    and label not in self._cfg.target_classes
                ):
                    continue

                xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                conf = float(boxes.conf[i].item())
                track_id: Optional[int] = None
                if use_tracker and boxes.id is not None:
                    track_id = int(boxes.id[i].item())

                detections.append(
                    Detection(
                        bbox=tuple(xyxy),          # type: ignore[arg-type]
                        confidence=conf,
                        class_label=label,
                        class_id=cls_id,
                        track_id=track_id,
                        source_camera=camera,
                        timestamp=ts,
                    )
                )
        return detections
