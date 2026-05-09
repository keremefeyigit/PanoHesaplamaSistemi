"""
core/distance_calculator.py
============================
DistanceCalculator — Benzer Üçgenler ve çift kamera dispariti yöntemiyle
mesafe ve gerçek boyut hesaplama.

Matematiksel Model (dokümandan):
    D  = (W × f) / P          [Benzer Üçgenler]
    W  = (D × P) / f          [Gerçek genişlik]
    K  = f_n / f_w            [Odak uzaklığı oranı — kalibrasyon sabiti]

Çift kamera disparity yaklaşımı:
    D_disparity = (f_w × baseline) / disparity

Her iki yöntem de uygulanır; geçerli olduğu durumlarda daha düşük belirsizlikli
olan seçilir.

NOT: Gerçek dünyada distorsiyon ve perspektif bozulması nedeniyle bu formüller
     ham kareye değil, undistort edilmiş görüntüye uygulanmalıdır.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from config import DualCameraConfig
from core.models import Detection

logger = logging.getLogger(__name__)


@dataclass
class MeasurementResult:
    """Mesafe ve boyut hesabının sonuçlarını tutan veri sınıfı."""
    # Kameraya olan uzaklık [metre]
    distance_m: float
    # Tabelanın hesaplanan gerçek genişliği [metre]
    real_width_m: float
    # Tabelanın hesaplanan gerçek yüksekliği [metre]
    real_height_m: float
    # Kullanılan yöntem: "similar_triangles" | "disparity" | "combined"
    method: str
    # Tahmini hata payı (±) [metre]  — None ise hesaplanamadı
    uncertainty_m: Optional[float] = None
    # Hesaplamada kullanılan bounding box piksel genişliği
    pixel_width: Optional[int] = None
    # Kullanılan odak uzaklığı [piksel]
    focal_length_px: Optional[float] = None

    @property
    def area_m2(self) -> float:
        """Tabelanın tahmini yüzey alanı [m²]."""
        return self.real_width_m * self.real_height_m


class DistanceCalculator:
    """
    Çift kamera sistemi için mesafe ve gerçek boyut hesaplayıcı.

    Desteklenen Yöntemler:
        1. Benzer Üçgenler (Tek kamera + bilinen referans genişlik)
        2. Disparity (Çift kamera piksel farkı)
        3. Birleşik (disparity öncelikli, single-cam fallback)

    Kullanım:
        calc = DistanceCalculator(config.cameras)
        result = calc.from_disparity(wide_det, narrow_det)
        result = calc.from_single_camera(wide_det, known_width_m=3.0)
    """

    def __init__(self, dual_config: DualCameraConfig) -> None:
        self._cfg = dual_config
        self._K = dual_config.focal_length_ratio    # K = f_n / f_w

    # ─── Yöntem 1: Benzer Üçgenler (tek kamera) ─────────────────────────────

    def from_single_camera(
        self,
        detection: Detection,
        known_width_m: float,
        use_narrow: bool = False,
    ) -> MeasurementResult:
        """
        Bilinen gerçek genişliğe sahip bir tabela için mesafe hesaplar.

            D = (W × f) / P

        Bu yöntem; bounding box'tan elde edilen piksel genişliği (P) ve
        tabelanın bilinen fiziksel genişliği (W) ile mesafeyi bulur.

        Args:
            detection:    Tespit nesnesi (pixel_width kullanılır).
            known_width_m: Tabelanın gerçek fiziksel genişliği [metre].
            use_narrow:   True ise dar açı kamerası parametreleri kullanılır.

        Returns:
            MeasurementResult
        """
        cam = self._cfg.narrow if use_narrow else self._cfg.wide
        f_px = cam.focal_length_px
        P = detection.pixel_width

        if P <= 0:
            raise ValueError(f"Geçersiz piksel genişliği: {P}")

        D = _similar_triangles_distance(W=known_width_m, f=f_px, P=P)

        # Gerçek yüksekliği de hesapla (oran yoluyla)
        real_height = _real_dimension(D=D, P=detection.pixel_height, f=f_px)

        logger.debug(
            "BenzerÜçgenler | P=%d px, f=%.1f px, W=%.2f m → D=%.2f m",
            P, f_px, known_width_m, D,
        )
        return MeasurementResult(
            distance_m=D,
            real_width_m=known_width_m,
            real_height_m=real_height,
            method="similar_triangles",
            uncertainty_m=self._estimate_uncertainty_single(D, P, f_px),
            pixel_width=P,
            focal_length_px=f_px,
        )

    # ─── Yöntem 2: Disparity (çift kamera) ──────────────────────────────────

    def from_disparity(
        self,
        wide_det: Detection,
        narrow_det: Detection,
    ) -> MeasurementResult:
        """
        Geniş ve dar açı bounding box merkezi farkından (disparity) mesafe hesaplar.

            disparity = |cx_wide - (cx_narrow / K)|    [normalise edilmiş]

        Ardından benzer üçgen ve gerçek boyut formülleriyle tamamlanır.

        Args:
            wide_det:   Geniş açı kamerasındaki tespit.
            narrow_det: Dar açı kamerasındaki aynı tabelanın tespiti.

        Returns:
            MeasurementResult
        """
        f_w = self._cfg.wide.focal_length_px
        baseline = self._cfg.baseline_m

        # Piksel merkezi disparity hesabı
        cx_wide = wide_det.bbox_center[0]
        cx_narrow = narrow_det.bbox_center[0]

        # Dar açı merkezi, geniş açı koordinat sistemine eşlenir
        cx_narrow_normalized = cx_narrow / self._K

        disparity = abs(cx_wide - cx_narrow_normalized)

        if disparity < self._cfg.min_disparity:
            logger.warning(
                "Disparity çok küçük (%.2f px) — benzer üçgen yöntemine geçildi.",
                disparity,
            )
            # Fallback: geniş kamera bounding box'ından Real Width olmadan tahmin
            return self._fallback_from_wide_bbox(wide_det)

        D = _disparity_to_distance(f=f_w, baseline=baseline, disparity=disparity)
        D = float(np.clip(D, 1.0, self._cfg.wide.max_reliable_distance_m))

        # Gerçek boyutlar
        f_w_px = f_w
        real_w = _real_dimension(D=D, P=wide_det.pixel_width, f=f_w_px)
        real_h = _real_dimension(D=D, P=wide_det.pixel_height, f=f_w_px)

        logger.debug(
            "Disparity | disp=%.2f px, baseline=%.3f m → D=%.2f m, W=%.2f m",
            disparity, baseline, D, real_w,
        )
        return MeasurementResult(
            distance_m=D,
            real_width_m=real_w,
            real_height_m=real_h,
            method="disparity",
            uncertainty_m=self._estimate_uncertainty_disparity(D, baseline, disparity),
            pixel_width=wide_det.pixel_width,
            focal_length_px=f_w,
        )

    # ─── Yöntem 3: Birleşik (disparity + single-cam doğrulama) ──────────────

    def combined_estimate(
        self,
        wide_det: Detection,
        narrow_det: Detection,
        reference_width_m: Optional[float] = None,
    ) -> MeasurementResult:
        """
        Hem disparity hem de (mümkünse) benzer üçgen sonuçlarını karşılaştırır,
        daha düşük belirsizliği olan sonucu döndürür.
        """
        result_disp = self.from_disparity(wide_det, narrow_det)

        if reference_width_m is not None:
            result_tri = self.from_single_camera(wide_det, reference_width_m)
            # İki tahminin ağırlıklı ortalaması
            combined = _weighted_average_results(result_disp, result_tri)
            combined.method = "combined"
            return combined

        return result_disp

    # ─── Simülasyon / Birim Test Yardımcısı ─────────────────────────────────

    @staticmethod
    def simulate(
        true_distance_m: float = 20.0,
        true_width_m: float = 3.0,
        focal_length_px: float = 850.0,
        baseline_m: float = 0.25,
        image_width_px: int = 1920,
        add_noise_px: float = 2.0,
    ) -> dict:
        """
        Verilen gerçek değerlerle sentetik piksel değerleri üretir ve
        mesafe/boyut hesaplamalarını doğrular.

        Bu yöntem, gerçek donanım olmadan algoritmaları test etmek için kullanılır.

        Args:
            true_distance_m:  Gerçek mesafe [metre].
            true_width_m:     Gerçek tabela genişliği [metre].
            focal_length_px:  Odak uzaklığı [piksel].
            baseline_m:       İki kamera arası fiziksel mesafe [metre].
            image_width_px:   Görüntü genişliği [piksel].
            add_noise_px:     Bounding box hata payı (Gauss gürültüsü std) [piksel].

        Returns:
            Simülasyon sonuçlarını içeren sözlük.
        """
        rng = np.random.default_rng(42)

        # Gerçek piksel genişliği hesabı
        true_P = (true_width_m * focal_length_px) / true_distance_m
        # Gürültü ekle
        P_noisy = max(1, true_P + rng.normal(0, add_noise_px))

        # Geri hesaplama — D = (W × f) / P
        estimated_D = _similar_triangles_distance(
            W=true_width_m, f=focal_length_px, P=P_noisy
        )
        # Geri hesaplama — W = (D × P) / f
        estimated_W = _real_dimension(D=estimated_D, P=P_noisy, f=focal_length_px)

        # Disparity simülasyonu
        K = 2.8   # f_n / f_w örnek oranı
        cx_wide = image_width_px / 2.0
        cx_narrow = cx_wide * K + rng.normal(0, add_noise_px)
        disparity = abs(cx_wide - cx_narrow / K)
        D_disp = _disparity_to_distance(focal_length_px, baseline_m, max(disparity, 0.1))

        result = {
            "true_distance_m": true_distance_m,
            "true_width_m": true_width_m,
            "true_pixel_width": round(true_P, 2),
            "noisy_pixel_width": round(P_noisy, 2),
            "estimated_distance_m_triangles": round(estimated_D, 4),
            "estimated_width_m_triangles": round(estimated_W, 4),
            "estimated_distance_m_disparity": round(D_disp, 4),
            "error_distance_pct_triangles": round(
                abs(estimated_D - true_distance_m) / true_distance_m * 100, 2
            ),
            "error_distance_pct_disparity": round(
                abs(D_disp - true_distance_m) / true_distance_m * 100, 2
            ),
        }
        logger.info("Simülasyon tamamlandı: %s", result)
        return result

    # ─── Özel Yardımcı Metotlar ──────────────────────────────────────────────

    def _fallback_from_wide_bbox(self, wide_det: Detection) -> MeasurementResult:
        """Disparity kullanılamadığında geniş açı bounding box boyutuna dayalı tahmin."""
        # Standart bir tabela (~3m) için referans alınır
        REFERENCE_SIGN_WIDTH_M = 3.0
        return self.from_single_camera(wide_det, REFERENCE_SIGN_WIDTH_M)

    @staticmethod
    def _estimate_uncertainty_single(D: float, P: float, f: float) -> float:
        """
        Benzer üçgen yöntemi için hata yayılımı (propagation of uncertainty).
        ΔD/D = ΔP/P  (P'deki ±1px hatanın D'ye etkisi)
        """
        delta_P = 1.0   # ±1 piksel bounding box belirsizliği
        return D * (delta_P / P)

    @staticmethod
    def _estimate_uncertainty_disparity(
        D: float, baseline: float, disparity: float
    ) -> float:
        """
        Disparity yöntemi için hata yayılımı.
        ΔD = D² × Δd / (f × baseline)
        """
        delta_d = 1.0   # ±1 piksel disparity belirsizliği
        f_approx = (baseline * D) / max(disparity, 1e-6) * disparity
        return (D ** 2 * delta_d) / max(f_approx, 1e-6)


# ─── Saf Fonksiyonlar (Modül Düzeyinde — Test Edilebilir) ─────────────────────

def _similar_triangles_distance(W: float, f: float, P: float) -> float:
    """
    Benzer Üçgenler formülü:  D = (W × f) / P

    Args:
        W: Nesnenin gerçek genişliği [metre].
        f: Odak uzaklığı [piksel].
        P: Görüntüdeki piksel genişliği [piksel].

    Returns:
        Mesafe D [metre].
    """
    if P <= 0:
        raise ValueError(f"Piksel genişliği sıfırdan büyük olmalı, alınan: {P}")
    return (W * f) / P


def _real_dimension(D: float, P: float, f: float) -> float:
    """
    Gerçek boyut formülü:  W = (D × P) / f

    Args:
        D: Mesafe [metre].
        P: Piksel boyutu [piksel].
        f: Odak uzaklığı [piksel].

    Returns:
        Gerçek boyut [metre].
    """
    if f <= 0:
        raise ValueError(f"Odak uzaklığı sıfırdan büyük olmalı, alınan: {f}")
    return (D * P) / f


def _disparity_to_distance(f: float, baseline: float, disparity: float) -> float:
    """
    Stereo disparity'den mesafe hesabı:  D = (f × baseline) / disparity

    Args:
        f:         Odak uzaklığı [piksel].
        baseline:  Kameralar arası fiziksel mesafe [metre].
        disparity: Piksel farkı [piksel].

    Returns:
        Mesafe D [metre].
    """
    if disparity <= 0:
        raise ValueError(f"Disparity sıfırdan büyük olmalı, alınan: {disparity}")
    return (f * baseline) / disparity


def _weighted_average_results(
    r1: MeasurementResult, r2: MeasurementResult
) -> MeasurementResult:
    """
    İki ölçüm sonucunu belirsizlik ağırlıklı ortalama ile birleştirir.
    Belirsizlik bilinmiyorsa eşit ağırlık kullanılır.
    """
    u1 = r1.uncertainty_m if r1.uncertainty_m else 1.0
    u2 = r2.uncertainty_m if r2.uncertainty_m else 1.0
    w1 = 1.0 / u1
    w2 = 1.0 / u2
    total = w1 + w2

    D = (r1.distance_m * w1 + r2.distance_m * w2) / total
    W = (r1.real_width_m * w1 + r2.real_width_m * w2) / total
    H = (r1.real_height_m * w1 + r2.real_height_m * w2) / total
    u_combined = 1.0 / math.sqrt(w1 ** 2 + w2 ** 2)

    return MeasurementResult(
        distance_m=D,
        real_width_m=W,
        real_height_m=H,
        method="combined",
        uncertainty_m=u_combined,
    )
