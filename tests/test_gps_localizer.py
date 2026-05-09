"""
tests/test_gps_localizer.py
============================
GPSLocalizer için birim testler.

Çalıştırma:
    pytest tests/ -v
"""

import math
import pytest

from geo.gps_localizer import GPSLocalizer, GPSFix, haversine_distance, _offset_to_latlon
from config import SystemConfig


@pytest.fixture
def localizer():
    return GPSLocalizer(SystemConfig().gps)


@pytest.fixture
def ankara_fix():
    """Ankara merkezine yakın bir GPS fix."""
    return GPSFix(
        latitude=39.9208,
        longitude=32.8541,
        heading_deg=0.0,    # Kuzeye bakıyor
        hdop=1.2,
        speed_ms=10.0,
    )


class TestGPSFix:

    def test_reliable_fix(self, ankara_fix):
        assert ankara_fix.is_reliable is True

    def test_unreliable_fix(self):
        fix = GPSFix(latitude=39.0, longitude=32.0, hdop=5.0)
        assert fix.is_reliable is False


class TestOffsetToLatLon:

    def test_north_offset(self):
        """100m kuzeye gidince enlem artmalı, boylam değişmemeli."""
        lat0, lon0 = 39.9208, 32.8541
        new_lat, new_lon = _offset_to_latlon(lat0, lon0, delta_north=100.0, delta_east=0.0)
        assert new_lat > lat0
        assert math.isclose(new_lon, lon0, abs_tol=1e-6)

    def test_east_offset(self):
        """100m doğuya gidince boylam artmalı, enlem değişmemeli."""
        lat0, lon0 = 39.9208, 32.8541
        new_lat, new_lon = _offset_to_latlon(lat0, lon0, delta_north=0.0, delta_east=100.0)
        assert new_lon > lon0
        assert math.isclose(new_lat, lat0, abs_tol=1e-6)

    def test_zero_offset(self):
        """Sıfır ofset ile koordinat değişmemeli."""
        lat0, lon0 = 39.9208, 32.8541
        new_lat, new_lon = _offset_to_latlon(lat0, lon0, 0.0, 0.0)
        assert math.isclose(new_lat, lat0, abs_tol=1e-10)
        assert math.isclose(new_lon, lon0, abs_tol=1e-10)


class TestHaversineDistance:

    def test_same_point_is_zero(self):
        d = haversine_distance(39.92, 32.85, 39.92, 32.85)
        assert d == 0.0

    def test_ankara_to_istanbul_approx(self):
        """Ankara–İstanbul yaklaşık 350 km."""
        d = haversine_distance(39.9208, 32.8541, 41.0082, 28.9784)
        assert 340_000 < d < 360_000

    def test_symmetry(self):
        """A→B mesafesi = B→A mesafesi."""
        d1 = haversine_distance(39.9, 32.8, 41.0, 28.9)
        d2 = haversine_distance(41.0, 28.9, 39.9, 32.8)
        assert math.isclose(d1, d2, rel_tol=1e-9)


class TestGPSLocalizer:

    def test_sign_location_north(self, localizer, ankara_fix):
        """Araç kuzeye bakıyorken 25m öndeki tabela daha kuzeyde olmalı."""
        ankara_fix.heading_deg = 0.0  # Kuzey
        loc = localizer.estimate_sign_location(ankara_fix, sign_distance_m=25.0)
        assert loc.latitude > ankara_fix.latitude

    def test_sign_location_east(self, localizer, ankara_fix):
        """Araç doğuya bakıyorken tabela daha doğuda olmalı."""
        ankara_fix.heading_deg = 90.0  # Doğu
        loc = localizer.estimate_sign_location(ankara_fix, sign_distance_m=25.0)
        assert loc.longitude > ankara_fix.longitude

    def test_uncertainty_increases_with_distance(self, localizer, ankara_fix):
        """Daha uzaktaki tabela için belirsizlik daha yüksek olmalı."""
        loc_near = localizer.estimate_sign_location(ankara_fix, sign_distance_m=10.0)
        loc_far = localizer.estimate_sign_location(ankara_fix, sign_distance_m=80.0)
        assert loc_far.position_uncertainty_m > loc_near.position_uncertainty_m

    def test_bearing_offset_right(self, localizer, ankara_fix):
        """Pozitif bearing ofseti (sağa) doğu yönünde kayma oluşturmalı."""
        ankara_fix.heading_deg = 0.0
        loc_center = localizer.estimate_sign_location(ankara_fix, 25.0, bearing_offset_deg=0.0)
        loc_right = localizer.estimate_sign_location(ankara_fix, 25.0, bearing_offset_deg=45.0)
        assert loc_right.longitude > loc_center.longitude

    def test_unreliable_gps_still_returns_result(self, localizer):
        """HDOP yüksek olsa bile sonuç döndürülmeli (uyarı ile)."""
        bad_fix = GPSFix(latitude=39.9, longitude=32.8, hdop=5.0)
        loc = localizer.estimate_sign_location(bad_fix, 25.0)
        assert loc is not None
