"""
db/database_manager.py
=======================
DatabaseManager — PostgreSQL/PostGIS + Redis katmanlı veri yöneticisi.

Mimari:
    [Tespit] → Redis Stream (tampon) → [Tüketici] → PostgreSQL (kalıcı depo)

    Yoğun veri akışında Redis Stream ara tampon görevi görür.
    Arka planda çalışan bir worker, Stream'i okuyup PostgreSQL'e yazar.

Bağımlılıklar:
    pip install asyncpg redis[hiredis]
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

# Async PostgreSQL sürücüsü
try:
    import asyncpg  # type: ignore
except ImportError:
    asyncpg = None  # type: ignore

# Redis istemcisi
try:
    import redis.asyncio as aioredis  # type: ignore
    import redis as sync_redis        # type: ignore
except ImportError:
    aioredis = None      # type: ignore
    sync_redis = None    # type: ignore

from config import PostgreSQLConfig, RedisConfig

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    İki katmanlı veri yöneticisi:
      1. Redis Stream — yüksek hızlı tampon (Edge cihazından buluta)
      2. PostgreSQL/PostGIS — coğrafi veri kalıcı deposu

    Kullanım (async):
        async with DatabaseManager.create(pg_cfg, redis_cfg) as db:
            await db.buffer_detection(detection_payload)
            await db.flush_buffer_to_postgres(max_items=100)
    """

    def __init__(
        self,
        pg_cfg: PostgreSQLConfig,
        redis_cfg: RedisConfig,
    ) -> None:
        self._pg_cfg = pg_cfg
        self._redis_cfg = redis_cfg
        self._pg_pool: Optional[Any] = None          # asyncpg.Pool
        self._redis: Optional[Any] = None             # aioredis.Redis

    # ─── Bağlantı Yönetimi ────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        pg_cfg: PostgreSQLConfig,
        redis_cfg: RedisConfig,
    ) -> "DatabaseManager":
        """Factory: Bağlantı havuzlarını oluşturur ve döndürür."""
        manager = cls(pg_cfg, redis_cfg)
        await manager._connect()
        return manager

    async def _connect(self) -> None:
        """PostgreSQL ve Redis bağlantılarını başlatır."""
        if asyncpg is None:
            raise ImportError("asyncpg yüklü değil: pip install asyncpg")
        if aioredis is None:
            raise ImportError("redis[hiredis] yüklü değil: pip install redis[hiredis]")

        logger.info("PostgreSQL bağlantı havuzu oluşturuluyor...")
        self._pg_pool = await asyncpg.create_pool(
            dsn=self._pg_cfg.dsn,
            min_size=self._pg_cfg.pool_min_size,
            max_size=self._pg_cfg.pool_max_size,
            command_timeout=30,
        )

        logger.info("Redis bağlantısı oluşturuluyor...")
        self._redis = await aioredis.from_url(
            f"redis://{self._redis_cfg.host}:{self._redis_cfg.port}/{self._redis_cfg.db}",
            password=self._redis_cfg.password,
            decode_responses=True,
        )
        logger.info("Veritabanı bağlantıları hazır.")

    async def close(self) -> None:
        """Tüm bağlantıları kapatır."""
        if self._pg_pool:
            await self._pg_pool.close()
        if self._redis:
            await self._redis.aclose()
        logger.info("Veritabanı bağlantıları kapatıldı.")

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator:
        """PostgreSQL transaction context manager."""
        async with self._pg_pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    # ─── Redis Tampon İşlemleri ──────────────────────────────────────────────

    async def buffer_detection(self, payload: dict) -> str:
        """
        Tespit verisini Redis Stream'e yazar (tampon).

        Bu yöntem; edge cihazında çalışır ve düşük gecikme garantisi verir.
        Ağır PostgreSQL yazımı ayrı bir worker thread'inde yapılır.

        Args:
            payload: Tespit meta verisi sözlüğü.

        Returns:
            Redis Stream entry ID (string).
        """
        payload["_buffered_at"] = time.time()
        entry_id = await self._redis.xadd(
            self._redis_cfg.stream_key,
            {k: json.dumps(v) if not isinstance(v, str) else v for k, v in payload.items()},
            maxlen=self._redis_cfg.stream_max_len,
            approximate=True,
        )
        logger.debug("Redis Stream'e yazıldı: %s", entry_id)
        return entry_id

    async def flush_buffer_to_postgres(
        self, max_items: int = 200, consumer_group: str = "pg_writer"
    ) -> int:
        """
        Redis Stream'deki bekleyen tespitleri PostgreSQL'e toplu yazar.

        Args:
            max_items:      Tek seferinde işlenecek maksimum kayıt sayısı.
            consumer_group: Redis Consumer Group adı.

        Returns:
            Yazılan kayıt sayısı.
        """
        # Consumer Group yoksa oluştur
        try:
            await self._redis.xgroup_create(
                self._redis_cfg.stream_key, consumer_group, id="0", mkstream=True
            )
        except Exception:
            pass  # Zaten var

        messages = await self._redis.xreadgroup(
            consumer_group,
            "worker-1",
            {self._redis_cfg.stream_key: ">"},
            count=max_items,
            block=100,
        )
        if not messages:
            return 0

        written = 0
        for _stream, entries in messages:
            for entry_id, data in entries:
                parsed = {k: self._try_json_loads(v) for k, v in data.items()}
                try:
                    await self.insert_detection(parsed)
                    await self._redis.xack(
                        self._redis_cfg.stream_key, consumer_group, entry_id
                    )
                    written += 1
                except Exception as exc:
                    logger.error("PostgreSQL yazım hatası [%s]: %s", entry_id, exc)

        logger.info("Redis → PostgreSQL: %d kayıt aktarıldı.", written)
        return written

    async def get_buffer_length(self) -> int:
        """Redis Stream'deki bekleyen mesaj sayısını döndürür."""
        info = await self._redis.xinfo_stream(self._redis_cfg.stream_key)
        return info.get("length", 0)

    # ─── PostgreSQL CRUD İşlemleri ────────────────────────────────────────────

    async def insert_detection(self, payload: dict) -> str:
        """
        Tek bir tespit kaydını PostgreSQL'e yazar.

        Beklenen payload anahtarları:
            session_id, class_label, confidence, distance_m,
            real_width_m, real_height_m, sign_lat, sign_lon,
            vehicle_lat, vehicle_lon, source_camera,
            thumbnail_path (opsiyonel), measurement_method (opsiyonel)

        Returns:
            Yeni oluşturulan kaydın UUID'si (string).
        """
        detection_id = str(uuid.uuid4())
        sign_lat = float(payload["sign_lat"])
        sign_lon = float(payload["sign_lon"])

        query = """
            INSERT INTO sign_detections (
                id, session_id, class_label, confidence,
                distance_m, real_width_m, real_height_m,
                sign_geom, vehicle_lat, vehicle_lon,
                source_camera, thumbnail_path, measurement_method,
                yolo_bbox_x1, yolo_bbox_y1, yolo_bbox_x2, yolo_bbox_y2
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7,
                ST_SetSRID(ST_MakePoint($8, $9), 4326),
                $10, $11, $12, $13, $14,
                $15, $16, $17, $18
            )
            RETURNING id
        """
        bbox = payload.get("bbox", [None, None, None, None])

        async with self._pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                detection_id,
                payload["session_id"],
                payload["class_label"],
                float(payload["confidence"]),
                float(payload["distance_m"]),
                float(payload.get("real_width_m", 0)),
                float(payload.get("real_height_m", 0)),
                sign_lon,           # ST_MakePoint(lon, lat) — dikkat: lon önce!
                sign_lat,
                float(payload.get("vehicle_lat", 0)),
                float(payload.get("vehicle_lon", 0)),
                payload.get("source_camera", "wide"),
                payload.get("thumbnail_path"),
                payload.get("measurement_method", "similar_triangles"),
                bbox[0] if bbox[0] is not None else None,
                bbox[1] if bbox[1] is not None else None,
                bbox[2] if bbox[2] is not None else None,
                bbox[3] if bbox[3] is not None else None,
            )
        return str(row["id"])

    async def create_session(self, vehicle_id: str, notes: str = "") -> str:
        """Yeni bir araç seferi kaydı oluşturur."""
        session_id = str(uuid.uuid4())
        async with self._pg_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO sessions (id, vehicle_id, notes) VALUES ($1, $2, $3)",
                session_id, vehicle_id, notes,
            )
        logger.info("Yeni sefer oluşturuldu: %s (araç: %s)", session_id, vehicle_id)
        return session_id

    async def close_session(self, session_id: str, total_km: float = 0.0) -> None:
        """Seferi kapatır ve toplam km'yi günceller."""
        async with self._pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET ended_at=NOW(), total_km=$1 WHERE id=$2",
                total_km, session_id,
            )

    async def query_signs_near(
        self,
        lat: float,
        lon: float,
        radius_m: float = 100.0,
    ) -> list[dict]:
        """
        Belirli bir konumun çevresindeki tabelaları kataloğdan sorgular.
        PostGIS ST_DWithin ile coğrafi filtre uygular.
        """
        async with self._pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM signs_near_point($1, $2, $3)",
                lat, lon, radius_m,
            )
        return [dict(row) for row in rows]

    async def get_session_summary(self, session_id: str) -> dict:
        """Bir seferin özet istatistiklerini döndürür."""
        query = """
            SELECT
                COUNT(*) AS total_detections,
                COUNT(DISTINCT class_label) AS unique_classes,
                AVG(confidence) AS avg_confidence,
                AVG(real_width_m) AS avg_width_m,
                MIN(detected_at) AS first_detection,
                MAX(detected_at) AS last_detection
            FROM sign_detections
            WHERE session_id = $1
        """
        async with self._pg_pool.acquire() as conn:
            row = await conn.fetchrow(query, session_id)
        return dict(row) if row else {}

    # ─── Senkron Yardımcı (Jetson'da ön-test için) ───────────────────────────

    @staticmethod
    def sync_redis_ping(redis_cfg: RedisConfig) -> bool:
        """Redis bağlantısını senkron olarak test eder (async dışında kullanım için)."""
        if sync_redis is None:
            raise ImportError("redis paketi yüklü değil: pip install redis[hiredis]")
        r = sync_redis.Redis(
            host=redis_cfg.host,
            port=redis_cfg.port,
            db=redis_cfg.db,
            password=redis_cfg.password,
        )
        return r.ping()

    # ─── Yardımcı ─────────────────────────────────────────────────────────────

    @staticmethod
    def _try_json_loads(value: str) -> Any:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
