"""
geo/gps_localizer.py
=====================
GPSLocalizer — Araç GPS verisi + kamera açısı + mesafeden tabela coğrafi
koordinatını hesaplayan modül.

Matematiksel Yöntem:
    Aracın anlık konumu (lat, lon, heading) ve tabelanın mesafesi (D)
    kullanılarak düz yüzey (flat-earth) yaklaşımıyla yeni koordinat bulunur.

    Δnorth = D × cos(bearing)
    Δeast  = D × sin(bearing)

    Bu fark, Haversine tersine çevirme ile enlem/boylama dönüştürülür.

Referans kamera ofseti (camera_offset_ned) config'den alınır.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from config import GPSConfig

logger = logging.getLogger(__name__)

# Dünya yarı çapı [metre] — WGS84 ortalaması
EARTH_RADIUS_M = 6_371_000.0


@dataclass
class GPSFix:
    """Tek bir GPS ölçümünü temsil eder."""
    latitude: float          # Enlem [derece, WGS84]
    longitude: float         # Boylam [derece, WGS84]
    altitude_m: float = 0.0  # Rakım [metre]
    heading_deg: float = 0.0 # Araç başlık açısı [derece, kuzey=0, saat yönünde]
    speed_ms: float = 0.0    # Hız [m/s]
    hdop: float = 1.0        # Yatay doğruluk faktörü (küçük = daha iyi)
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    @property
    def is_reliable(self) -> bool:
        """HDOP eşiğine göre konum güvenilirliği."""
        return self.hdop <= 2.0


@dataclass
class SignGeoLocation:
    """Tespit edilen bir tabelanın hesaplanmış coğrafi konumu."""
    latitude: float
    longitude: float
    altitude_m: float
    distance_from_vehicle_m: float
    # Konum belirsizliği tahmini [metre]
    position_uncertainty_m: float
    # Kullanılan GPS fix verisi
    vehicle_fix: GPSFix


class GPSLocalizer:
    """
    Araç konumunu ve kamera parametrelerini kullanarak tabela koordinatı hesaplar.

    Kullanım:
        localizer = GPSLocalizer(config.gps)
        gps_fix = GPSFix(lat=39.92, lon=32.85, heading_deg=45.0, hdop=1.2)
        sign_loc = localizer.estimate_sign_location(
            vehicle_fix=gps_fix,
            sign_distance_m=25.0,
            bearing_offset_deg=0.0,   # Tabela tam önde
        )
    """

    def __init__(self, cfg: GPSConfig) -> None:
        self._cfg = cfg

    def estimate_sign_location(
        self,
        vehicle_fix: GPSFix,
        sign_distance_m: float,
        bearing_offset_deg: float = 0.0,
        sign_height_offset_m: float = 0.0,
    ) -> SignGeoLocation:
        """
        Tabelanın dünya koordinatlarını (enlem/boylam) hesaplar.

        Args:
            vehicle_fix:         Aracın anlık GPS verisi.
            sign_distance_m:     Kameradan tabelaya olan mesafe [metre].
            bearing_offset_deg:  Araç başlık açısına göre tabela sapması [derece].
                                 0 = tam önde, pozitif = sağa.
            sign_height_offset_m: Kameradan tabelanın yükseklik farkı [metre].

        Returns:
            SignGeoLocation (enlem, boylam, belirsizlik vb.)
        """
        if not vehicle_fix.is_reliable:
            logger.warning("GPS HDOP=%.2f — Konum güvenilir değil!", vehicle_fix.hdop)

        # Yatay mesafeyi (3D'den 2D'ye)
        horizontal_dist = math.sqrt(
            max(0.0, sign_distance_m ** 2 - sign_height_offset_m ** 2)
        )

        # Tabelanın bakış açısı = araç başlık + kamera ofseti + sapma
        bearing = vehicle_fix.heading_deg + bearing_offset_deg
        bearing_rad = math.radians(bearing % 360.0)

        # Düz yüzey (flat-earth) yaklaşımı — kısa mesafelerde yeterince hassas
        delta_north = horizontal_dist * math.cos(bearing_rad)
        delta_east = horizontal_dist * math.sin(bearing_rad)

        new_lat, new_lon = _offset_to_latlon(
            vehicle_fix.latitude,
            vehicle_fix.longitude,
            delta_north,
            delta_east,
        )

        # Belirsizlik tahmini: GPS belirsizliği + mesafe belirsizliği
        gps_accuracy = vehicle_fix.hdop * 2.5        # Tipik çarpan
        distance_uncertainty = sign_distance_m * 0.03  # ±%3 mesafe hatası
        total_uncertainty = math.sqrt(gps_accuracy ** 2 + distance_uncertainty ** 2)

        logger.debug(
            "Tabela konumu: lat=%.6f, lon=%.6f, belirsizlik=±%.1f m",
            new_lat, new_lon, total_uncertainty,
        )
        return SignGeoLocation(
            latitude=new_lat,
            longitude=new_lon,
            altitude_m=vehicle_fix.altitude_m + sign_height_offset_m,
            distance_from_vehicle_m=sign_distance_m,
            position_uncertainty_m=total_uncertainty,
            vehicle_fix=vehicle_fix,
        )

    def batch_estimate(
        self,
        vehicle_fix: GPSFix,
        detections_with_distance: list[tuple[float, float]],
    ) -> list[SignGeoLocation]:
        """
        Birden fazla tespit için toplu konum hesabı.

        Args:
            vehicle_fix:                Araç GPS verisi.
            detections_with_distance:   [(mesafe_m, bearing_offset_deg), ...]

        Returns:
            SignGeoLocation listesi.
        """
        return [
            self.estimate_sign_location(vehicle_fix, dist_m, offset_deg)
            for dist_m, offset_deg in detections_with_distance
        ]


# ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def _offset_to_latlon(
    lat0: float, lon0: float, delta_north: float, delta_east: float
) -> tuple[float, float]:
    """
    Bir noktadan metre cinsinden kuzey/doğu ofseti ile yeni enlem/boylam hesaplar.
    Flat-earth yaklaşımı (<50 km için hata <0.1%).
    """
    new_lat = lat0 + math.degrees(delta_north / EARTH_RADIUS_M)
    new_lon = lon0 + math.degrees(
        delta_east / (EARTH_RADIUS_M * math.cos(math.radians(lat0)))
    )
    return new_lat, new_lon


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    İki coğrafi koordinat arasındaki küresel mesafeyi Haversine formülü
    ile hesaplar.

    Returns:
        Mesafe [metre].
    """
    R = EARTH_RADIUS_M
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
