"""
tests/test_distance_calculator.py
===================================
DistanceCalculator için birim testler.
Donanım gerektirmez — saf matematik fonksiyonları test edilir.

Çalıştırma:
    pytest tests/ -v
"""

import math
import pytest

from core.distance_calculator import (
    _similar_triangles_distance,
    _real_dimension,
    _disparity_to_distance,
    _weighted_average_results,
    DistanceCalculator,
    MeasurementResult,
)
from config import SystemConfig


# ─── Benzer Üçgenler Testleri ─────────────────────────────────────────────────

class TestSimilarTriangles:

    def test_basic_formula(self):
        """D = (W × f) / P — basit doğrulama."""
        D = _similar_triangles_distance(W=3.0, f=850.0, P=127.0)
        assert math.isclose(D, (3.0 * 850.0) / 127.0, rel_tol=1e-9)

    def test_inverse_relationship_with_P(self):
        """P artarsa D azalmalı (nesne yaklaşıyor)."""
        D1 = _similar_triangles_distance(W=3.0, f=850.0, P=50.0)
        D2 = _similar_triangles_distance(W=3.0, f=850.0, P=100.0)
        assert D1 > D2

    def test_zero_pixel_width_raises(self):
        with pytest.raises(ValueError, match="(?i)piksel"):
            _similar_triangles_distance(W=3.0, f=850.0, P=0)

    def test_negative_pixel_width_raises(self):
        with pytest.raises(ValueError):
            _similar_triangles_distance(W=3.0, f=850.0, P=-5)

    def test_roundtrip_distance_to_width(self):
        """D → W geri dönüşümü orijinal W'yi vermelidir."""
        W_orig = 4.0
        f, P = 850.0, 200.0
        D = _similar_triangles_distance(W=W_orig, f=f, P=P)
        W_back = _real_dimension(D=D, P=P, f=f)
        assert math.isclose(W_orig, W_back, rel_tol=1e-9)


class TestRealDimension:

    def test_basic_formula(self):
        """W = (D × P) / f."""
        W = _real_dimension(D=20.0, P=100.0, f=850.0)
        assert math.isclose(W, (20.0 * 100.0) / 850.0, rel_tol=1e-9)

    def test_zero_focal_raises(self):
        with pytest.raises(ValueError, match="(?i)odak"):
            _real_dimension(D=20.0, P=100.0, f=0.0)

    def test_larger_distance_larger_real_width(self):
        """Aynı piksel boyutu, daha uzak nesne → daha büyük gerçek boyut."""
        W1 = _real_dimension(D=10.0, P=100.0, f=850.0)
        W2 = _real_dimension(D=50.0, P=100.0, f=850.0)
        assert W2 > W1


# ─── Disparity Testleri ───────────────────────────────────────────────────────

class TestDisparityDistance:

    def test_basic_formula(self):
        """D = (f × baseline) / disparity."""
        D = _disparity_to_distance(f=850.0, baseline=0.25, disparity=10.625)
        assert math.isclose(D, (850.0 * 0.25) / 10.625, rel_tol=1e-6)

    def test_larger_disparity_closer_object(self):
        D1 = _disparity_to_distance(f=850.0, baseline=0.25, disparity=5.0)
        D2 = _disparity_to_distance(f=850.0, baseline=0.25, disparity=50.0)
        assert D1 > D2

    def test_zero_disparity_raises(self):
        with pytest.raises(ValueError, match="(?i)disparity"):
            _disparity_to_distance(f=850.0, baseline=0.25, disparity=0.0)

    def test_wider_baseline_longer_range(self):
        """Daha geniş baseline → daha uzak mesafe algılama."""
        D_narrow = _disparity_to_distance(f=850.0, baseline=0.1, disparity=5.0)
        D_wide = _disparity_to_distance(f=850.0, baseline=0.5, disparity=5.0)
        assert D_wide > D_narrow


# ─── DistanceCalculator Entegrasyon Testleri ──────────────────────────────────

class TestDistanceCalculatorSimulation:

    @pytest.fixture
    def calc(self):
        cfg = SystemConfig()
        return DistanceCalculator(cfg.cameras)

    def test_simulation_low_error(self, calc):
        """Simülasyonda mesafe hatası %5'ten az olmalı."""
        result = DistanceCalculator.simulate(
            true_distance_m=25.0,
            true_width_m=3.0,
            focal_length_px=850.0,
            baseline_m=0.25,
            add_noise_px=1.0,   # Düşük gürültü
        )
        assert result["error_distance_pct_triangles"] < 5.0

    def test_simulation_returns_expected_keys(self, calc):
        result = DistanceCalculator.simulate()
        expected_keys = {
            "true_distance_m", "true_width_m", "estimated_distance_m_triangles",
            "estimated_width_m_triangles", "error_distance_pct_triangles",
            "estimated_distance_m_disparity",
        }
        assert expected_keys.issubset(result.keys())

    def test_simulation_various_distances(self, calc):
        """10m-100m arası tüm mesafelerde hata oranı %10'dan az olmalı."""
        for d in [10, 25, 50, 75, 100]:
            r = DistanceCalculator.simulate(
                true_distance_m=float(d),
                true_width_m=3.0,
                add_noise_px=2.0,
            )
            assert r["error_distance_pct_triangles"] < 10.0, (
                f"d={d}m'de hata çok yüksek: {r['error_distance_pct_triangles']}%"
            )


# ─── Ağırlıklı Ortalama Testi ────────────────────────────────────────────────

class TestWeightedAverage:

    def test_equal_uncertainty_gives_midpoint(self):
        """Eşit belirsizlikte sonuç ortalaması verir."""
        r1 = MeasurementResult(
            distance_m=20.0, real_width_m=3.0, real_height_m=2.0,
            method="a", uncertainty_m=1.0
        )
        r2 = MeasurementResult(
            distance_m=30.0, real_width_m=5.0, real_height_m=3.0,
            method="b", uncertainty_m=1.0
        )
        combined = _weighted_average_results(r1, r2)
        assert math.isclose(combined.distance_m, 25.0, rel_tol=1e-6)
        assert math.isclose(combined.real_width_m, 4.0, rel_tol=1e-6)

    def test_low_uncertainty_dominates(self):
        """Daha az belirsizliği olan ölçüm ağırlıklı olarak ön plana çıkmalı."""
        r1 = MeasurementResult(
            distance_m=20.0, real_width_m=3.0, real_height_m=2.0,
            method="a", uncertainty_m=0.1   # Çok kesin
        )
        r2 = MeasurementResult(
            distance_m=50.0, real_width_m=6.0, real_height_m=4.0,
            method="b", uncertainty_m=10.0  # Çok belirsiz
        )
        combined = _weighted_average_results(r1, r2)
        # r1'e daha yakın olmalı
        assert combined.distance_m < 25.0
