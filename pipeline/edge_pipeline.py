"""
pipeline/edge_pipeline.py
==========================
EdgePipeline — NVIDIA Jetson Orin için optimize edilmiş görüntü işleme akışı.

Mimari:
    ┌──────────┐    ┌───────────────┐    ┌──────────────────┐
    │  Kamera  │───▶│  Undistort    │───▶│  ObjectDetector  │
    │ (Wide +  │    │ (CameraCalib) │    │  (YOLOv8/TRT)    │
    │  Narrow) │    └───────────────┘    └────────┬─────────┘
    └──────────┘                                  │
                                    ┌─────────────▼──────────────┐
                                    │  DistanceCalculator        │
                                    │  (Disparity + SimilarTri.) │
                                    └─────────────┬──────────────┘
                                                  │
                                    ┌─────────────▼──────────────┐
                                    │  GPSLocalizer              │
                                    │  (Sign World Coordinates)  │
                                    └─────────────┬──────────────┘
                                                  │
                    ┌─────────────────────────────▼──────────────────────────────┐
                    │  Redis Stream Buffer  ──►  Async PG Writer (flush worker)  │
                    └────────────────────────────────────────────────────────────┘

Edge Prensipleri:
    - Ağır inference (YOLO + mesafe) cihazda yapılır.
    - Buluta yalnızca metadata + thumbnail gönderilir.
    - Redis Stream; ağ kesintisine karşı yerel tampon görevi görür.
    - Frame skip (detection_interval_frames) ile CPU/GPU yükü dengelenir.
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

import cv2
import numpy as np

from config import SystemConfig, config as default_config
from core.camera_calibration import CameraCalibration
from core.object_detector import ObjectDetector, Detection
from core.distance_calculator import DistanceCalculator, MeasurementResult
from geo.gps_localizer import GPSLocalizer, GPSFix

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Tek bir karenin tam işleme sonucu."""
    frame_index: int
    timestamp: float
    # Tespit ve ölçüm çiftleri [(tespit, ölçüm), ...]
    measurements: list[tuple[Detection, MeasurementResult]] = field(default_factory=list)
    # GPS fix (frame işlendiği andaki değer)
    gps_fix: Optional[GPSFix] = None
    # Hata mesajı (frame işlenemezse)
    error: Optional[str] = None
    # İşleme süresi [ms]
    processing_time_ms: float = 0.0

    @property
    def detection_count(self) -> int:
        return len(self.measurements)


class EdgePipeline:
    """
    Akıllı Tabela Sistemi — Ana işleme pipeline'ı.

    Bu sınıf tüm alt sistemleri koordine eder ve edge cihazında çalışır.
    Kamera okuma, distorsiyon düzeltme, tespit, mesafe hesabı, GPS
    eşleştirme ve Redis tamponlama işlemlerini birleştirir.

    Kullanım:
        pipeline = EdgePipeline(session_id="ses-001")
        pipeline.initialize()
        asyncio.run(pipeline.run(max_frames=1000))
    """

    def __init__(
        self,
        session_id: str,
        cfg: SystemConfig = default_config,
        gps_provider: Optional[Callable[[], GPSFix]] = None,
    ) -> None:
        """
        Args:
            session_id:   PostgreSQL sefer kimliği.
            cfg:          Sistem konfigürasyonu (varsayılan: config.py'den).
            gps_provider: GPS verisi sağlayan callable. None ise simüle edilir.
        """
        self._session_id = session_id
        self._cfg = cfg
        self._gps_provider = gps_provider or self._dummy_gps_provider

        # Alt sistemler (initialize() ile başlatılır)
        self._calibration: Optional[CameraCalibration] = None
        self._detector: Optional[ObjectDetector] = None
        self._calc: Optional[DistanceCalculator] = None
        self._localizer: Optional[GPSLocalizer] = None

        # Kamera yakaları
        self._cap_wide: Optional[cv2.VideoCapture] = None
        self._cap_narrow: Optional[cv2.VideoCapture] = None

        # Durum
        self._running = False
        self._frame_index = 0
        self._stats = _PipelineStats()

        # Thumbnail çıktı dizini
        self._thumb_dir = cfg.pipeline.debug_output_dir / "thumbnails"

    # ─── Başlatma ────────────────────────────────────────────────────────────

    def initialize(self) -> "EdgePipeline":
        """Tüm alt sistemleri başlatır ve kameraları açar."""
        logger.info("EdgePipeline başlatılıyor...")

        self._calibration = CameraCalibration(self._cfg.cameras).load_from_config()
        self._detector = ObjectDetector(self._cfg.detector)
        self._calc = DistanceCalculator(self._cfg.cameras)
        self._localizer = GPSLocalizer(self._cfg.gps)

        # Kameraları aç
        wide_id = self._cfg.cameras.wide.device_id
        narrow_id = self._cfg.cameras.narrow.device_id
        self._cap_wide = cv2.VideoCapture(wide_id)
        self._cap_narrow = cv2.VideoCapture(narrow_id)

        if not self._cap_wide.isOpened():
            logger.warning("Geniş açı kamera açılamadı (id=%d). Simülasyon modu.", wide_id)
        if not self._cap_narrow.isOpened():
            logger.warning("Dar açı kamera açılamadı (id=%d). Simülasyon modu.", narrow_id)

        self._thumb_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Pipeline hazır. Sefer: %s", self._session_id)
        return self

    # ─── Ana Döngü ────────────────────────────────────────────────────────────

    async def run(
        self,
        max_frames: Optional[int] = None,
        db_manager=None,           # DatabaseManager (opsiyonel)
    ) -> None:
        """
        Ana asenkron işleme döngüsü.

        Args:
            max_frames:  Belirli sayıda frame sonra otomatik dur. None = sonsuz.
            db_manager:  DatabaseManager örneği (Redis buffer için).
        """
        self._running = True
        logger.info("Pipeline çalışıyor. max_frames=%s", max_frames)

        while self._running:
            if max_frames and self._frame_index >= max_frames:
                break

            # Kare oku
            wide_frame, narrow_frame = self._read_frames()
            if wide_frame is None:
                logger.warning("Kare okunamadı, 100ms bekleniyor...")
                await asyncio.sleep(0.1)
                continue

            # Frame skip
            if self._frame_index % self._cfg.pipeline.detection_interval_frames != 0:
                self._frame_index += 1
                continue

            # Frame'i işle
            t0 = time.perf_counter()
            gps_fix = self._gps_provider()
            result = await self._process_frame(wide_frame, narrow_frame, gps_fix)
            result.processing_time_ms = (time.perf_counter() - t0) * 1000.0

            self._stats.update(result)

            # Redis'e yaz
            if db_manager and result.measurements:
                for det, meas in result.measurements:
                    payload = self._build_payload(det, meas, gps_fix, wide_frame)
                    await db_manager.buffer_detection(payload)

            self._frame_index += 1
            await asyncio.sleep(0)   # Event loop'u başka görevlere bırak

        self._running = False
        logger.info("Pipeline durdu. İstatistikler: %s", self._stats)

    async def _process_frame(
        self,
        wide_frame: np.ndarray,
        narrow_frame: np.ndarray,
        gps_fix: GPSFix,
    ) -> PipelineResult:
        """Tek bir frame çiftini tamamen işler."""
        result = PipelineResult(
            frame_index=self._frame_index,
            timestamp=time.time(),
            gps_fix=gps_fix,
        )
        try:
            # 1. Distorsiyon düzeltme
            wide_ud = self._calibration.undistort_wide(wide_frame)
            narrow_ud = self._calibration.undistort_narrow(narrow_frame)

            # 2. Nesne tespiti (çift kamera)
            wide_dets, narrow_dets = self._detector.detect_dual(
                wide_ud, narrow_ud, use_tracker=True
            )

            if not wide_dets:
                return result

            # 3. Tespit eşleştirme ve mesafe hesabı
            matched = self._match_detections(wide_dets, narrow_dets)

            for wide_det, narrow_det in matched:
                meas = self._calc.combined_estimate(wide_det, narrow_det)
                result.measurements.append((wide_det, meas))

        except Exception as exc:
            result.error = str(exc)
            logger.error("Frame %d işleme hatası: %s", self._frame_index, exc, exc_info=True)

        return result

    # ─── Kare Okuma ──────────────────────────────────────────────────────────

    def _read_frames(
        self,
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Her iki kameradan senkron kare okur."""
        wide_ok, wide_frame = self._cap_wide.read() if (self._cap_wide and self._cap_wide.isOpened()) else (False, None)
        narrow_ok, narrow_frame = self._cap_narrow.read() if (self._cap_narrow and self._cap_narrow.isOpened()) else (False, None)

        # Kamera yoksa siyah kare simüle et
        if not wide_ok or wide_frame is None:
            wide_frame = self._dummy_frame(self._cfg.cameras.wide.resolution)
        if not narrow_ok or narrow_frame is None:
            narrow_frame = self._dummy_frame(self._cfg.cameras.narrow.resolution)

        return wide_frame, narrow_frame

    # ─── Tespit Eşleştirme ────────────────────────────────────────────────────

    @staticmethod
    def _match_detections(
        wide_dets: list[Detection],
        narrow_dets: list[Detection],
    ) -> list[tuple[Detection, Optional[Detection]]]:
        """
        Track ID'ye veya sınıf etiketine göre geniş-dar açı tespitlerini eşleştirir.

        Returns:
            [(wide_det, narrow_det veya None), ...]
        """
        narrow_by_track: dict[int, Detection] = {
            d.track_id: d for d in narrow_dets if d.track_id is not None
        }
        matched = []
        for wd in wide_dets:
            nd = narrow_by_track.get(wd.track_id) if wd.track_id is not None else None
            matched.append((wd, nd))
        return matched

    # ─── Payload Oluşturma ────────────────────────────────────────────────────

    def _build_payload(
        self,
        det: Detection,
        meas: MeasurementResult,
        gps_fix: GPSFix,
        frame: np.ndarray,
    ) -> dict:
        """Redis/PG için veri yükü hazırlar (thumbnail dahil)."""
        # Konum hesabı
        sign_loc = self._localizer.estimate_sign_location(
            vehicle_fix=gps_fix,
            sign_distance_m=meas.distance_m,
        )

        # Thumbnail oluştur
        thumb_path = self._save_thumbnail(det, frame)

        return {
            "session_id": self._session_id,
            "class_label": det.class_label,
            "confidence": det.confidence,
            "distance_m": round(meas.distance_m, 3),
            "real_width_m": round(meas.real_width_m, 3),
            "real_height_m": round(meas.real_height_m, 3),
            "sign_lat": round(sign_loc.latitude, 8),
            "sign_lon": round(sign_loc.longitude, 8),
            "vehicle_lat": round(gps_fix.latitude, 8),
            "vehicle_lon": round(gps_fix.longitude, 8),
            "source_camera": det.source_camera,
            "measurement_method": meas.method,
            "thumbnail_path": str(thumb_path) if thumb_path else None,
            "bbox": list(det.bbox),
        }

    def _save_thumbnail(self, det: Detection, frame: np.ndarray) -> Optional[Path]:
        """Tespit bounding box'ından thumbnail kaydeder."""
        try:
            x1, y1, x2, y2 = det.bbox
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            if crop.size == 0:
                return None
            max_w, max_h = self._cfg.pipeline.thumbnail_max_size
            h, w = crop.shape[:2]
            scale = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
            if scale < 1.0:
                crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            filename = self._thumb_dir / f"{self._frame_index}_{det.class_label}_{int(time.time())}.jpg"
            cv2.imwrite(str(filename), crop, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return filename
        except Exception as exc:
            logger.warning("Thumbnail kaydedilemedi: %s", exc)
            return None

    # ─── Kapatma ─────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Pipeline'ı güvenli şekilde durdurur."""
        self._running = False
        if self._cap_wide:
            self._cap_wide.release()
        if self._cap_narrow:
            self._cap_narrow.release()
        logger.info("Pipeline kapatıldı.")

    # ─── Yardımcılar ─────────────────────────────────────────────────────────

    @staticmethod
    def _dummy_frame(resolution: tuple[int, int]) -> np.ndarray:
        """Kamera yokken test için siyah kare üretir."""
        w, h = resolution
        return np.zeros((h, w, 3), dtype=np.uint8)

    @staticmethod
    def _dummy_gps_provider() -> GPSFix:
        """GPS donanımı yokken Ankara merkezi koordinatı döndürür."""
        return GPSFix(
            latitude=39.9208,
            longitude=32.8541,
            heading_deg=90.0,
            hdop=1.5,
        )


@dataclass
class _PipelineStats:
    """Pipeline çalışma istatistikleri."""
    total_frames: int = 0
    total_detections: int = 0
    error_frames: int = 0
    total_processing_ms: float = 0.0

    def update(self, result: PipelineResult) -> None:
        self.total_frames += 1
        self.total_detections += result.detection_count
        if result.error:
            self.error_frames += 1
        self.total_processing_ms += result.processing_time_ms

    @property
    def avg_fps(self) -> float:
        if self.total_processing_ms <= 0:
            return 0.0
        return 1000.0 / (self.total_processing_ms / max(self.total_frames, 1))
