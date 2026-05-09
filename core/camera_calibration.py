"""
core/camera_calibration.py
==========================
CameraCalibration — Kamera distorsiyon düzeltme ve iç parametre yönetimi.

Gerçek dünya görüntüleri her zaman lens bozulmalarına (radyal ve teğetsel
distorsiyon) sahiptir. Bu sınıf; kalibrasyon verilerini (satranç tahtası
görüntülerinden veya dosyadan) yükler ve her kare için distorsiyon düzeltmesi
uygular.

Referans: OpenCV kamera kalibrasyon dökümantasyonu
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import DualCameraConfig, NarrowAngleCameraConfig, WideAngleCameraConfig

logger = logging.getLogger(__name__)


@dataclass
class CalibrationData:
    """Tek bir kameraya ait tam kalibrasyon veri seti."""
    camera_matrix: np.ndarray           # 3×3 iç parametre matrisi (K)
    dist_coeffs: np.ndarray             # Distorsiyon katsayıları [k1,k2,p1,p2,k3]
    image_size: tuple[int, int]         # (genişlik, yükseklik) [piksel]
    reprojection_error: float = 0.0     # Yeniden projeksiyon hatası (RMS) [piksel]
    # Stereo kalibrasyon için ek alanlar
    rotation_matrix: Optional[np.ndarray] = None
    translation_vector: Optional[np.ndarray] = None


class CameraCalibration:
    """
    Çift kamera sistemi için kalibrasyon ve distorsiyon düzeltme işlemleri.

    Kullanım:
        cal = CameraCalibration(config.cameras)
        cal.load_from_config()              # Config'deki sabit değerlerle başla
        undistorted = cal.undistort_wide(frame)
    """

    def __init__(self, dual_config: DualCameraConfig) -> None:
        self._cfg = dual_config
        self._wide_data: Optional[CalibrationData] = None
        self._narrow_data: Optional[CalibrationData] = None
        # Undistort haritaları (performans için önceden hesaplanır)
        self._wide_maps: Optional[tuple[np.ndarray, np.ndarray]] = None
        self._narrow_maps: Optional[tuple[np.ndarray, np.ndarray]] = None

    # ─── Fabrika Yöntemleri ───────────────────────────────────────────────────

    def load_from_config(self) -> "CameraCalibration":
        """Config.py'deki değerlerden CalibrationData nesneleri oluşturur."""
        self._wide_data = self._build_calibration_data(self._cfg.wide)
        self._narrow_data = self._build_calibration_data(self._cfg.narrow)
        self._precompute_maps()
        logger.info(
            "Kalibrasyon config'den yüklendi. K_ratio=%.4f",
            self._cfg.focal_length_ratio,
        )
        return self

    def load_from_file(self, filepath: Path) -> "CameraCalibration":
        """
        Daha önce satranç tahtasıyla yapılan ve diske kaydedilen kalibrasyonu yükler.

        Dosya formatı: pickle ile serileştirilmiş dict
        {
            'wide':   CalibrationData,
            'narrow': CalibrationData
        }
        """
        with open(filepath, "rb") as fh:
            data: dict = pickle.load(fh)
        self._wide_data = data["wide"]
        self._narrow_data = data["narrow"]
        self._precompute_maps()
        logger.info("Kalibrasyon dosyadan yüklendi: %s", filepath)
        return self

    def calibrate_from_checkerboard(
        self,
        wide_images: list[np.ndarray],
        narrow_images: list[np.ndarray],
        board_size: tuple[int, int] = (9, 6),
        square_size_mm: float = 25.0,
        save_path: Optional[Path] = None,
    ) -> "CameraCalibration":
        """
        Satranç tahtası görüntülerinden kamera kalibrasyonu yapar.

        Args:
            wide_images:      Geniş açı kamerasının kalibrasyon görüntüleri.
            narrow_images:    Dar açı kamerasının kalibrasyon görüntüleri.
            board_size:       Satranç tahtasındaki iç köşe sayısı (sütun, satır).
            square_size_mm:   Tek karenin kenar uzunluğu [mm].
            save_path:        Sonucu kaydetmek için dosya yolu (opsiyonel).

        Returns:
            self (method chaining için)
        """
        logger.info("Satranç tahtası kalibrasyonu başlıyor...")
        self._wide_data = self._run_opencv_calibration(
            wide_images, board_size, square_size_mm
        )
        self._narrow_data = self._run_opencv_calibration(
            narrow_images, board_size, square_size_mm
        )
        if save_path:
            self._save_to_file(save_path)
        self._precompute_maps()
        return self

    # ─── Distorsiyon Düzeltme ─────────────────────────────────────────────────

    def undistort_wide(self, frame: np.ndarray) -> np.ndarray:
        """Geniş açı kamerası karesine distorsiyon düzeltmesi uygular."""
        return self._undistort(frame, self._wide_maps, "wide")

    def undistort_narrow(self, frame: np.ndarray) -> np.ndarray:
        """Dar açı kamerası karesine distorsiyon düzeltmesi uygular."""
        return self._undistort(frame, self._narrow_maps, "narrow")

    # ─── Özellikler ───────────────────────────────────────────────────────────

    @property
    def wide(self) -> CalibrationData:
        return self._require("wide", self._wide_data)

    @property
    def narrow(self) -> CalibrationData:
        return self._require("narrow", self._narrow_data)

    @property
    def focal_ratio_K(self) -> float:
        """K = f_n / f_w  (piksel cinsinden odak uzaklığı oranı)."""
        return (
            self.narrow.camera_matrix[1, 1] / self.wide.camera_matrix[1, 1]
        )

    # ─── Yardımcı Metotlar ────────────────────────────────────────────────────

    def _build_calibration_data(
        self, cam_cfg: WideAngleCameraConfig | NarrowAngleCameraConfig
    ) -> CalibrationData:
        """Config değerlerinden CalibrationData oluşturur."""
        cx, cy = cam_cfg.cx, cam_cfg.cy
        f = cam_cfg.focal_length_px
        K = np.array(
            [[f, 0.0, cx], [0.0, f, cy], [0.0, 0.0, 1.0]], dtype=np.float64
        )
        D = np.array(cam_cfg.distortion_coeffs, dtype=np.float64)
        return CalibrationData(
            camera_matrix=K,
            dist_coeffs=D,
            image_size=cam_cfg.resolution,
        )

    def _precompute_maps(self) -> None:
        """cv2.remap için distorsiyon haritalarını ön-hesaplar (hız optimizasyonu)."""
        for data, attr in [(self._wide_data, "_wide_maps"), (self._narrow_data, "_narrow_maps")]:
            if data is None:
                continue
            new_K, _ = cv2.getOptimalNewCameraMatrix(
                data.camera_matrix,
                data.dist_coeffs,
                data.image_size,
                alpha=0,            # alpha=0: siyah kenarsız kırpılmış görüntü
                newImgSize=data.image_size,
            )
            map1, map2 = cv2.initUndistortRectifyMap(
                data.camera_matrix,
                data.dist_coeffs,
                None,
                new_K,
                data.image_size,
                cv2.CV_16SC2,
            )
            setattr(self, attr, (map1, map2))
        logger.debug("Undistort haritaları ön-hesaplandı.")

    @staticmethod
    def _undistort(
        frame: np.ndarray,
        maps: Optional[tuple[np.ndarray, np.ndarray]],
        label: str,
    ) -> np.ndarray:
        if maps is None:
            raise RuntimeError(
                f"{label} kamera için kalibrasyon yüklenmemiş. "
                "load_from_config() veya load_from_file() çağırın."
            )
        return cv2.remap(frame, maps[0], maps[1], cv2.INTER_LINEAR)

    @staticmethod
    def _run_opencv_calibration(
        images: list[np.ndarray],
        board_size: tuple[int, int],
        square_size_mm: float,
    ) -> CalibrationData:
        """OpenCV satranç tahtası kalibrasyonunu çalıştırır."""
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0 : board_size[0], 0 : board_size[1]].T.reshape(-1, 2)
        objp *= square_size_mm

        obj_points, img_points = [], []
        img_size: tuple[int, int] = (0, 0)

        for img in images:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img_size = (gray.shape[1], gray.shape[0])
            ret, corners = cv2.findChessboardCorners(gray, board_size, None)
            if ret:
                obj_points.append(objp)
                corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                img_points.append(corners2)

        if not obj_points:
            raise ValueError("Hiçbir görüntüde satranç tahtası köşesi bulunamadı!")

        rms, K, D, rvecs, tvecs = cv2.calibrateCamera(
            obj_points, img_points, img_size, None, None
        )
        logger.info("Kalibrasyon RMS hatası: %.4f piksel", rms)
        return CalibrationData(
            camera_matrix=K,
            dist_coeffs=D,
            image_size=img_size,
            reprojection_error=rms,
        )

    def _save_to_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump({"wide": self._wide_data, "narrow": self._narrow_data}, fh)
        logger.info("Kalibrasyon kaydedildi: %s", path)

    @staticmethod
    def _require(name: str, data: Optional[CalibrationData]) -> CalibrationData:
        if data is None:
            raise RuntimeError(
                f"'{name}' kamerası için kalibrasyon verisi henüz yüklenmedi."
            )
        return data
