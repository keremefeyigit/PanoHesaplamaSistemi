"""
main.py
=======
Akıllı Tabela Ölçüm Sistemi — Giriş Noktası

Çalıştırma:
    python main.py                       # Tam sistem (kamera + DB)
    python main.py --simulate            # Donanım olmadan simülasyon
    python main.py --calibrate           # Kalibrasyon modu
    python main.py --demo-distance       # Mesafe hesap demonstrasyonu
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

# Loglama
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/tabela_sistemi.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

from config import config
from core.distance_calculator import DistanceCalculator
from pipeline.edge_pipeline import EdgePipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Akıllı Tabela Ölçüm Sistemi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--simulate", action="store_true", help="Donanım olmadan simülasyon çalıştır")
    parser.add_argument("--calibrate", action="store_true", help="Kamera kalibrasyon modunu başlat")
    parser.add_argument("--demo-distance", action="store_true", help="Mesafe hesap demonstrasyonu")
    parser.add_argument("--max-frames", type=int, default=None, help="İşlenecek maksimum kare sayısı")
    parser.add_argument("--session-id", type=str, default=None, help="PostgreSQL sefer ID (yoksa otomatik oluşturulur)")
    parser.add_argument("--no-db", action="store_true", help="Veritabanı bağlantısı olmadan çalış")
    return parser.parse_args()


async def run_full_system(args: argparse.Namespace) -> None:
    """Tam sistemi başlatır (kamera + DB)."""
    session_id = args.session_id or str(uuid.uuid4())
    logger.info("=" * 60)
    logger.info("Akıllı Tabela Sistemi Başlatılıyor")
    logger.info("Sefer ID: %s", session_id)
    logger.info("=" * 60)

    db_manager = None

    if not args.no_db:
        try:
            from db.database_manager import DatabaseManager
            db_manager = await DatabaseManager.create(config.postgresql, config.redis)
            logger.info("Veritabanı bağlantısı kuruldu.")
        except Exception as exc:
            logger.warning("DB bağlantısı kurulamadı (%s). --no-db modunda devam ediliyor.", exc)
            db_manager = None

    pipeline = EdgePipeline(session_id=session_id, cfg=config)
    pipeline.initialize()

    # Flush worker — Redis'i periyodik olarak PG'ye boşaltır
    async def flush_worker():
        while True:
            await asyncio.sleep(5)
            if db_manager:
                try:
                    written = await db_manager.flush_buffer_to_postgres(max_items=200)
                    if written > 0:
                        logger.info("Flush: %d kayıt PostgreSQL'e aktarıldı.", written)
                except Exception as exc:
                    logger.error("Flush hatası: %s", exc)

    try:
        await asyncio.gather(
            pipeline.run(max_frames=args.max_frames, db_manager=db_manager),
            flush_worker(),
        )
    except KeyboardInterrupt:
        logger.info("Kullanıcı tarafından durduruldu.")
    finally:
        pipeline.stop()
        if db_manager:
            await db_manager.close()


def run_simulation(args: argparse.Namespace) -> None:
    """Donanım olmadan mesafe hesap simülasyonu çalıştırır."""
    logger.info("─── SİMÜLASYON MODU ───")
    calc = DistanceCalculator(config.cameras)

    test_cases = [
        {"true_distance_m": 10.0,  "true_width_m": 2.0},
        {"true_distance_m": 25.0,  "true_width_m": 3.0},
        {"true_distance_m": 50.0,  "true_width_m": 4.0},
        {"true_distance_m": 100.0, "true_width_m": 6.0},
    ]

    print("\n{'─'*70}")
    print(f"{'Gerçek D (m)':>15} {'Gerçek W (m)':>13} {'Tahmin D (m)':>13} {'Hata %':>8} {'Disparity D (m)':>16} {'Disp. Hata%':>12}")
    print("─" * 82)

    for tc in test_cases:
        r = DistanceCalculator.simulate(
            true_distance_m=tc["true_distance_m"],
            true_width_m=tc["true_width_m"],
            focal_length_px=config.cameras.wide.focal_length_px,
            baseline_m=config.cameras.baseline_m,
        )
        print(
            f"{r['true_distance_m']:>15.1f} "
            f"{r['true_width_m']:>13.1f} "
            f"{r['estimated_distance_m_triangles']:>13.2f} "
            f"{r['error_distance_pct_triangles']:>7.2f}% "
            f"{r['estimated_distance_m_disparity']:>16.2f} "
            f"{r['error_distance_pct_disparity']:>11.2f}%"
        )
    print("─" * 82)


def run_demo_distance() -> None:
    """Dokümandaki formüllerle küçük interaktif demo."""
    print("\n━━━━ Benzer Üçgenler Demo ━━━━")
    print("Formül: D = (W × f) / P")
    print()

    from core.distance_calculator import _similar_triangles_distance, _real_dimension

    examples = [
        (3.0, 850.0, 127),    # W=3m, f=850px, P=127px
        (3.0, 850.0,  51),    # Daha uzak
        (6.0, 850.0,  85),    # Daha büyük tabela
    ]

    for W, f, P in examples:
        D = _similar_triangles_distance(W, f, P)
        W_back = _real_dimension(D, P, f)
        print(f"  W={W}m, f={f}px, P={P}px  →  D={D:.2f}m  (geri-doğrulama W={W_back:.3f}m)")

    print("\n━━━━ Disparity Demo ━━━━")
    print("Formül: D = (f × baseline) / disparity")
    from core.distance_calculator import _disparity_to_distance
    for disp_px in [5, 15, 30, 60]:
        D = _disparity_to_distance(850.0, 0.25, disp_px)
        print(f"  baseline=0.25m, f=850px, disparity={disp_px}px  →  D={D:.2f}m")


def main() -> None:
    args = parse_args()

    # Log dizinini oluştur
    Path("logs").mkdir(exist_ok=True)

    if args.demo_distance:
        run_demo_distance()
        return

    if args.simulate:
        run_simulation(args)
        return

    if args.calibrate:
        logger.info("Kalibrasyon modu — core/camera_calibration.py CameraCalibration.calibrate_from_checkerboard() kullanın.")
        return

    # Tam sistem
    asyncio.run(run_full_system(args))


if __name__ == "__main__":
    main()
