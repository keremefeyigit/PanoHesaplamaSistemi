-- db/schema_organizations.sql
-- Organizasyon ve kullanıcı yönetimi için ek tablolar
-- Mevcut schema.sql'in üstüne uygulanır:
--   psql -U tabela_user -d tabela_db -f db/schema_organizations.sql

-- ─── Organizasyonlar (Kurumlar) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL UNIQUE,
    slug        TEXT NOT NULL UNIQUE,       -- URL-friendly: "ankara-belediyesi"
    logo_url    TEXT,
    contact_email TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    -- Abonelik için gelecekte kullanılacak alan
    plan        TEXT NOT NULL DEFAULT 'free',   -- 'free' | 'basic' | 'pro'
    plan_expires_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Kullanıcılar ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'viewer'
                        CHECK (role IN ('admin', 'viewer')),
    -- viewer rolü için hangi kuruma bağlı
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Veri Paylaşımı: Hangi sefer hangi kurumla paylaşılmış ──────────────────
-- Admin istediği session'ı istediği kurumla paylaşır.
CREATE TABLE IF NOT EXISTS shared_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shared_by       UUID REFERENCES users(id),
    shared_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Paylaşım notları
    notes           TEXT,
    -- Erişim seviyesi: 'read' (sadece görüntüle)
    access_level    TEXT NOT NULL DEFAULT 'read',
    UNIQUE (session_id, organization_id)
);

CREATE INDEX IF NOT EXISTS idx_shared_sessions_org
    ON shared_sessions (organization_id);
CREATE INDEX IF NOT EXISTS idx_shared_sessions_session
    ON shared_sessions (session_id);

-- ─── Oturumlar tablosuna organizasyon alanı ekle ─────────────────────────────
-- (Eğer zaten yoksa)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='sessions' AND column_name='organization_id'
    ) THEN
        ALTER TABLE sessions ADD COLUMN organization_id UUID REFERENCES organizations(id);
    END IF;
END
$$;

-- ─── Varsayılan Admin Kullanıcısı ─────────────────────────────────────────────
-- Şifre: "admin123" → bcrypt hash (üretimde değiştir!)
INSERT INTO users (email, password_hash, full_name, role)
VALUES (
    'admin@tabela.local',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMlJbekRShaNGW3Em29loMBa.6',
    'Sistem Yöneticisi',
    'admin'
)
ON CONFLICT (email) DO NOTHING;
