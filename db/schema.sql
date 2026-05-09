"""
db/schema.sql
=============
PostgreSQL + PostGIS veritabanı şeması — Akıllı Tabela Sistemi

Bu dosya:
  1. PostGIS uzantısını etkinleştirir.
  2. Araç seferi (session) tablosunu oluşturur.
  3. Tespit edilen tabelaları coğrafi veri (GEOMETRY) ile saklar.
  4. Küçük resimleri (thumbnail) referanslar.
  5. Performans için GiST (coğrafi) ve B-Tree indeksler tanımlar.

Çalıştırma:
    psql -U tabela_user -d tabela_db -f db/schema.sql
"""

-- ─── Uzantılar ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Sefer (Session) Tablosu ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id      TEXT        NOT NULL,          -- Araç plakası / kimliği
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    total_km        NUMERIC(10, 3),
    notes           TEXT,

    CONSTRAINT sessions_ended_after_started
        CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- ─── Araç Konum Günlüğü ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicle_positions (
    id              BIGSERIAL   PRIMARY KEY,
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PostGIS Point (WGS84, SRID=4326)
    geom            GEOMETRY(Point, 4326) NOT NULL,
    altitude_m      NUMERIC(8, 2),
    heading_deg     NUMERIC(6, 2),
    speed_ms        NUMERIC(6, 2),
    hdop            NUMERIC(5, 2)
);

CREATE INDEX IF NOT EXISTS idx_vehicle_positions_geom
    ON vehicle_positions USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_vehicle_positions_session_time
    ON vehicle_positions (session_id, recorded_at DESC);

-- ─── Tabela Tespitleri ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sign_detections (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id              UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Coğrafi konum (tabelanın hesaplanan dünya koordinatı)
    sign_geom               GEOMETRY(Point, 4326) NOT NULL,

    -- Ölçüm verileri
    distance_m              NUMERIC(8, 2) NOT NULL,
    real_width_m            NUMERIC(6, 3),
    real_height_m           NUMERIC(6, 3),
    area_m2                 NUMERIC(8, 4) GENERATED ALWAYS AS (real_width_m * real_height_m) STORED,

    -- Yapay Zeka / Tespit Meta Verisi
    class_label             TEXT        NOT NULL,
    confidence              NUMERIC(5, 4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    track_id                INTEGER,
    yolo_bbox_x1            INTEGER,
    yolo_bbox_y1            INTEGER,
    yolo_bbox_x2            INTEGER,
    yolo_bbox_y2            INTEGER,

    -- Hesaplama Yöntemi
    measurement_method      TEXT        NOT NULL DEFAULT 'similar_triangles',
    position_uncertainty_m  NUMERIC(8, 2),

    -- Araç konumu o anki GPS verisi (referans için)
    vehicle_lat             NUMERIC(12, 8),
    vehicle_lon             NUMERIC(12, 8),

    -- Küçük resim (thumbnail) — S3/nesne depolama yolu veya base64
    thumbnail_path          TEXT,
    thumbnail_width_px      INTEGER,
    thumbnail_height_px     INTEGER,

    -- Kaynak kamera
    source_camera           TEXT        CHECK (source_camera IN ('wide', 'narrow', 'combined'))
);

-- Coğrafi sorgular için GiST indeks
CREATE INDEX IF NOT EXISTS idx_sign_detections_geom
    ON sign_detections USING GIST (sign_geom);

-- Sefer ve zaman filtreleri için bileşik indeks
CREATE INDEX IF NOT EXISTS idx_sign_detections_session_time
    ON sign_detections (session_id, detected_at DESC);

-- Sınıf filtreleme indeksi
CREATE INDEX IF NOT EXISTS idx_sign_detections_class
    ON sign_detections (class_label);

-- ─── Tekil Tabela Kataloğu (De-Duplicate) ────────────────────────────────────
-- Aynı fiziksel tabelanın birden fazla tespitini kümeleyerek
-- bir "Tabela Envanteri" tablosu oluşturur.
CREATE TABLE IF NOT EXISTS sign_catalog (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Kümeleme merkezi koordinatı
    center_geom     GEOMETRY(Point, 4326) NOT NULL,

    -- Ortalama ölçüm değerleri
    avg_width_m     NUMERIC(6, 3),
    avg_height_m    NUMERIC(6, 3),
    avg_distance_m  NUMERIC(8, 2),

    -- En çok gözlemlenen sınıf
    dominant_class  TEXT        NOT NULL,
    detection_count INTEGER     NOT NULL DEFAULT 1,

    -- En iyi güven skoruna sahip tespit
    best_detection_id UUID REFERENCES sign_detections(id),
    thumbnail_path  TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_sign_catalog_geom
    ON sign_catalog USING GIST (center_geom);

-- ─── Görünümler ───────────────────────────────────────────────────────────────

-- Son 24 saatin tespitlerini özet olarak gösterir
CREATE OR REPLACE VIEW v_recent_detections AS
    SELECT
        sd.id,
        sd.detected_at,
        sd.class_label,
        sd.confidence,
        sd.distance_m,
        sd.real_width_m,
        sd.real_height_m,
        sd.area_m2,
        ST_Y(sd.sign_geom) AS sign_lat,
        ST_X(sd.sign_geom) AS sign_lon,
        sd.thumbnail_path,
        s.vehicle_id
    FROM sign_detections sd
    JOIN sessions s ON s.id = sd.session_id
    WHERE sd.detected_at >= NOW() - INTERVAL '24 hours'
    ORDER BY sd.detected_at DESC;

-- ─── Yardımcı Fonksiyonlar ───────────────────────────────────────────────────

-- Belirli yarıçap içindeki tabelaları sorgular
CREATE OR REPLACE FUNCTION signs_near_point(
    p_lat FLOAT,
    p_lon FLOAT,
    p_radius_m FLOAT DEFAULT 100.0
)
RETURNS TABLE(
    id UUID,
    class_label TEXT,
    distance_to_query_m FLOAT,
    sign_lat FLOAT,
    sign_lon FLOAT,
    avg_width_m NUMERIC,
    thumbnail_path TEXT
)
LANGUAGE SQL STABLE
AS $$
    SELECT
        sc.id,
        sc.dominant_class,
        ST_Distance(
            sc.center_geom::geography,
            ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography
        ) AS distance_to_query_m,
        ST_Y(sc.center_geom) AS sign_lat,
        ST_X(sc.center_geom) AS sign_lon,
        sc.avg_width_m,
        sc.thumbnail_path
    FROM sign_catalog sc
    WHERE ST_DWithin(
        sc.center_geom::geography,
        ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography,
        p_radius_m
    )
    ORDER BY distance_to_query_m;
$$;
