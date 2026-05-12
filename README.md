[AKILLI_TABELA_SISTEM_DOKUMANI.md](https://github.com/user-attachments/files/27552872/AKILLI_TABELA_SISTEM_DOKUMANI.md)

# PanoHesaplamaSistemi
Kentsel reklam alanlarının yönetiminde dijital dönüşüm: Belediye ve kamu kurumları için reklam panosu boyutlarını milimetrik hassasiyetle hesaplayan, koordinat takibini otomatize eden OpenCV ve Yapay Zeka destekli yenilikçi analiz ekosistemi.

[AKILLI_TABELA_SISTEM_DOKUMANI_.md](https://github.com/user-attachments/files/27563979/AKILLI_TABELA_SISTEM_DOKUMANI_v2.1.md)

## Teknik Sistem Dökümanı — v2.1 (Proje Durumuna Göre Güncel)

> **Son Güncelleme:** Mayıs 2026
> **Durum:** Aktif Geliştirme — Edge Pipeline & Backend İskelet Tamamlandı

---

## ⚡ Geliştirici Hızlı Başlangıç

> **Not:** Linux/macOS'ta scriptler `./` prefix'i ile çalıştırılmalıdır.

### 1. İlk Kurulum (tek seferlik)

```bash
chmod +x setup_dev.sh run_tests.sh run_local.sh
./setup_dev.sh --minimal   # hızlı kurulum (test + demo için yeterli)
./setup_dev.sh             # tam kurulum (ultralytics + opencv)
```

### 2. Testleri Çalıştır

```bash
./run_tests.sh             # tüm birim testleri (30 test, hızlı)
./run_tests.sh -k distance # sadece mesafe testleri
```

### 3. Sistemi Localde Çalıştır

```bash
./run_local.sh demo        # formül demo — D=f×B/d, W=W_px×Z/f (donanım yok)
./run_local.sh simulate    # mesafe + GPS simülasyonu tablosu
./run_local.sh yolo        # YOLOv8 ile gerçek tespit dene
./run_local.sh pipeline    # tam pipeline, DB olmadan (50 kare)
./run_local.sh pipeline 200  # 200 kare işle
./run_local.sh             # etkileşimli menü
```

#### Docker ile tam sistem (PostgreSQL + Redis):
```bash
./run_local.sh db-up       # Docker ile PG + Redis başlat
./run_local.sh pipeline-db # pipeline + DB birlikte çalıştır
./run_local.sh db-down     # servisleri durdur
```

---

## 📋 İçindekiler

1. [Giriş](#1-giriş)
2. [Proje Mevcut Durumu (Tamamlananlar)](#2-proje-mevcut-durumu)
3. [Teknik Analiz ve Yaklaşım](#3-teknik-analiz-ve-yaklaşım)
4. [Sistem Mimarisi](#4-sistem-mimarisi)
5. [Modül Detayları ve Kodlama Durumu](#5-modül-detayları-ve-kodlama-durumu)
6. [Veritabanı Tasarımı](#6-veritabanı-tasarımı)
7. [Harita Entegrasyonu](#7-harita-entegrasyonu)
8. [API Servisleri](#8-api-servisleri)
9. [İhtiyaç ve Gider Kalemleri](#9-ihtiyaç-ve-gider-kalemleri)
10. [Sonraki Adımlar (TODO)](#10-sonraki-adımlar-todo)

---


## 1. Giriş

Bu döküman, hareket halindeki belediye otobüsleri üzerinden reklam tabelalarının (pano) tespiti, boyut ölçümü ve coğrafi konumlandırılması için geliştirilen **"Akıllı Tabela Ölçüm Sistemi"**nin teknik gereksinimlerini, mimari yapısını ve güncel kodlama durumunu kapsamaktadır.

Sistem nihai hedef olarak belediyelere şunu sağlayacaktır: Tüm yol kenarı reklam panolarının boyut ve konum envanterini otomatik çıkarmak; bu veriden dinamik fiyatlandırma yapabilmek.

---

## 2. Proje Mevcut Durumu

### ✅ Tamamlanan Modüller

| Modül | Dosya | Durum |
|---|---|---|
| Edge Pipeline ana akışı | `pipeline/edge_pipeline.py` | ✅ Tamamlandı |
| GPS Lokalizasyonu | `geo/gps_localizer.py` | ✅ Tamamlandı |
| Mesafe Hesaplayıcı testi | `tests/test_distance_calculator.py` | ✅ Test yazıldı |
| GPS Lokalizasyon testi | `tests/test_gps_localizer.py` | ✅ Test yazıldı |
| Veritabanı şema (organizasyonlar) | `db/schema_organizations.sql` | ✅ Tamamlandı |
| Veritabanı şema (genel) | `db/schema.sql` | ✅ Tamamlandı |
| Veritabanı yöneticisi | `db/database_manager.py` | ✅ Tamamlandı |
| Backend iskelet | `web/backend/main.py` | ✅ İskelet hazır |
| API route yapısı | `web/backend/api/routes/` | ✅ Klasör yapısı oluşturuldu |
| Frontend iskelet | `web/frontend/` (Vite + React) | ✅ Proje oluşturuldu |
| Sistem konfigürasyonu | `config.py` | ✅ Tamamlandı |

### 🔄 Devam Eden Modüller

| Modül | Dosya | Durum |
|---|---|---|
| Kamera Kalibrasyonu | `core/camera_calibration.py` | 🔄 Arayüz tanımlı, implementasyon eksik |
| Nesne Dedektörü | `core/object_detector.py` | 🔄 Arayüz tanımlı, YOLO entegrasyonu eksik |
| Mesafe Hesaplayıcı | `core/distance_calculator.py` | 🔄 Arayüz tanımlı, formül implementasyonu eksik |
| Backend API endpoint'leri | `web/backend/api/routes/` | 🔄 Dosyalar boş |
| Frontend dashboard bileşenleri | `web/frontend/src/` | 🔄 Vite scaffolding, içerik boş |

### ❌ Henüz Başlanmamış

- YOLOv8 model eğitimi (Türkiye'ye özgü pano görselleri ile)
- TimescaleDB / Redis entegrasyonu
- Harita bileşeni (Leaflet.js)
- Fiyatlandırma motoru
- Deployment / Docker yapılandırması

---

## 3. Teknik Analiz ve Yaklaşım

### 3.1. OpenCV ve Yapay Zeka — Rol Dağılımı

Sistemde sadece AI nesne tespiti için yeterlidir; ancak **hassas boyut ölçümü için Hibrit Yaklaşım zorunludur.**

| Görev | Araç | Açıklama |
|---|---|---|
| Pano tespiti (bounding box) | **YOLOv8 / TensorRT** | Görüntü akışından "Tabela", "Pano", "Afiş" tespiti |
| Kötü hava / gece performansı | **YOLOv8** | Eğitimle üstesinden gelinir |
| Kamera kalibrasyonu | **OpenCV** | Lens distorsiyonu düzeltme, intrinsic matris |
| Görüntü rektifikasyonu | **OpenCV** | İki kamerayı aynı düzleme getirme |
| Mesafe hesabı (Z) | **OpenCV + Geometri** | Benzer üçgenler / disparity formülü |
| Gerçek boyut hesabı | **NumPy (formül)** | W = W_pix × Z / f |
| Perspektif düzeltme | **OpenCV** | Eğik çekimlerde bozulma giderme |

**Sonuç:** Tespit için AI, mesafe ve boyut hesabı için OpenCV + deterministik geometri gereklidir.

### 3.2. Matematiksel Model — Mesafeden Bağımsız Boyut Ölçümü

Sistemde **Geniş Açı (Wide-Angle)** ve **Dar Açı (Narrow-Angle / Telephoto)** olmak üzere iki kamera kullanılır. Notlardaki üçgen çizimi bu prensibi göstermektedir: otobüs ne kadar yakın veya uzak olursa olsun, doğru boyut bulunabilir.

#### Adım 1: Mesafe Hesabı

```
        f × B
  Z  = ───────
          d

  Z  = Kamera – pano mesafesi (metre)
  f  = Odak uzaklığı (piksel) ← kamera kalibrasyonundan gelir
  B  = İki kamera merkezi arası fiziksel mesafe / baseline (metre)
  d  = Disparity = x_geniş_açı − x_dar_açı (piksel)
```

> **Neden işe yarar?** Uzak nesne → d küçük → Z büyük. Yakın nesne → d büyük → Z küçük. Formül her mesafede tutarlıdır.

#### Adım 2: Gerçek Boyut Hesabı

```
              W_piksel × Z          H_piksel × Z
  W_gerçek = ──────────────    H_gerçek = ──────────────
                   f                           f
```

#### Çift Kamera Karşılaştırması (Kalibrasyon Adımı)

1. Odak uzaklığı oranı `K = f_dar / f_geniş` kalibrasyon ile bir kez belirlenir ve `config.py` içine kaydedilir.
2. Aynı panonun iki kameradaki piksel konumlarındaki yatay kayma disparity'yi verir.
3. Disparity → Z (mesafe) → W, H (gerçek boyut).

#### Sayısal Doğrulama (Mesafeden Bağımsızlık)

| Parametre | 30 m uzakta | 10 m yakında |
|---|---|---|
| Gerçek pano genişliği | 3.00 m | 3.00 m |
| Bounding box piksel genişliği | 80 px | 240 px |
| Disparity (d) | 3.2 px | 9.6 px |
| Z hesaplanan (f=800, B=0.12m) | 30.0 m ✅ | 10.0 m ✅ |
| **W hesaplanan** | **3.00 m ✅** | **3.00 m ✅** |

---

## 4. Sistem Mimarisi

### 4.1. Genel Katman Yapısı

```
┌─────────────────────────────────────────────────────────┐
│  KATMAN 1 — OTOBÜS (Edge)        [pipeline/ modülü]     │
│                                                          │
│  Geniş Açı Kamera ──┐                                   │
│                     ├─→ EdgePipeline (edge_pipeline.py) │
│  Dar Açı Kamera  ───┘     │                             │
│                           ├─ CameraCalibration          │
│  GPS Modülü ──────────────┤─ ObjectDetector (YOLO/TRT)  │
│  IMU Sensörü ─────────────┤─ DistanceCalculator         │
│                           └─ GPSLocalizer               │
│                                  │                       │
│                     Redis Stream Buffer                  │
│                                  │                       │
│                     Async PG Writer (flush worker)       │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTPS / JSON  (4G/5G)
┌──────────────────────────▼───────────────────────────────┐
│  KATMAN 2 — BULUT BACKEND         [web/backend/ modülü]  │
│                                                          │
│  FastAPI (main.py)  →  API Routes  →  Core Services      │
│  TimescaleDB (ölçüm zaman serisi)                        │
│  PostgreSQL + PostGIS (pano envanteri, coğrafi veri)     │
│  Redis (yazma kuyruğu, cache)                            │
│  S3 / MinIO (fotoğraf depolama)                          │
└──────────────────────────┬───────────────────────────────┘
                           │ REST API / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│  KATMAN 3 — FRONTEND              [web/frontend/ modülü] │
│                                                          │
│  React + Vite + TypeScript                               │
│  Leaflet.js (Harita)                                     │
│  Dashboard, Envanter, Fiyatlandırma                      │
└──────────────────────────────────────────────────────────┘
```

### 4.2. Edge Pipeline Dahili Akışı (`edge_pipeline.py`)

```
Kamera (Geniş + Dar)
      │
      ▼
  Undistort ── CameraCalibration
      │
      ▼
  ObjectDetector (YOLOv8 / TensorRT) ── Bounding Box
      │
      ▼
  DistanceCalculator (Disparity + SimilarTri.) ── Z, W, H
      │
      ▼
  GPSLocalizer (Sign World Coordinates) ── Lat/Lon
      │
      ▼
  Redis Stream Buffer ──→ Async PG Writer (flush worker)
```

**Edge Prensipleri (kodda belirtildiği haliyle):**
- Ağır inference (YOLO + mesafe) cihazda yapılır.
- Buluta yalnızca metadata + thumbnail gönderilir.
- Redis Stream: ağ kesintisine karşı yerel tampon görevi görür.
- `frame_skip` (detection_interval_frames) ile CPU/GPU yükü dengelenir.

### 4.3. `PipelineResult` Veri Yapısı

```python
@dataclass
class PipelineResult:
    frame_index: int
    timestamp: float
    measurements: List[tuple[Detection, MeasurementResult]]
    gps_fix: Optional[GPSFix] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0

    @property
    def detection_count(self) -> int:
        return len(self.measurements)
```

---

## 5. Modül Detayları ve Kodlama Durumu

### 5.1. `pipeline/edge_pipeline.py` ✅

**Sorumluluk:** Tüm edge işlem hattını orkestre eder.

**Bağımlılıklar:**
```python
import cv2, numpy as np, asyncio, threading, time, logging
from core.camera_calibration import CameraCalibration
from core.object_detector   import ObjectDetector, Detection
from core.distance_calculator import DistanceCalculator, MeasurementResult
from geo.gps_localizer       import GPSLocalizer, GPSFix
```

**Ana sınıf:** `EdgePipeline` — Jetson Orin için optimize edilmiş görüntü işleme akışı.

---

### 5.2. `core/camera_calibration.py` 🔄 — Implementasyon Gerekiyor

**Sorumluluk:** İki kameranın kalibrasyon verilerini yönetir.

**Tamamlanması gereken metodlar:**
```python
class CameraCalibration:
    def load_from_file(self, path: str) -> None:
        # JSON/YAML formatında f, cx, cy, k1, k2 yükle
        ...

    def undistort(self, frame: np.ndarray) -> np.ndarray:
        # cv2.undistort() ile lens bozulmasını düzelt
        ...

    def get_focal_length_px(self, camera: str) -> float:
        # 'wide' veya 'narrow' için piksel odak uzaklığı döndür
        ...

    def get_baseline_m(self) -> float:
        # İki kamera merkezi arası fiziksel mesafe (B)
        ...
```

---

### 5.3. `core/object_detector.py` 🔄 — YOLO Entegrasyonu Gerekiyor

**Sorumluluk:** YOLOv8 / TensorRT ile pano tespiti.

**Tamamlanması gereken:**
```python
class ObjectDetector:
    def __init__(self, model_path: str, conf_threshold: float = 0.70):
        # YOLOv8 veya TensorRT engine yükle
        ...

    def detect(self, frame: np.ndarray) -> List[Detection]:
        # Bounding box listesi döndür: [x1, y1, x2, y2, conf, class_id]
        ...
```

**Model eğitimi için not:** Türkiye yol kenarı pano görüntüleri ile özel eğitim yapılmalıdır. Başlangıç için genel COCO pre-trained ağırlıklar kullanılabilir, ancak `billboard` sınıfı için fine-tuning gereklidir.

---

### 5.4. `core/distance_calculator.py` 🔄 — Formül Implementasyonu Gerekiyor

**Sorumluluk:** Bölüm 3.2'deki matematiksel modeli uygular.

**Tamamlanması gereken:**
```python
class DistanceCalculator:
    def __init__(self, calib: CameraCalibration):
        self.f  = calib.get_focal_length_px('wide')
        self.B  = calib.get_baseline_m()

    def compute_disparity(self,
                          bbox_wide: tuple,
                          bbox_narrow: tuple) -> float:
        # İki kameradaki bounding box merkezlerinin x farkı
        cx_wide   = (bbox_wide[0]   + bbox_wide[2])   / 2
        cx_narrow = (bbox_narrow[0] + bbox_narrow[2]) / 2
        return cx_wide - cx_narrow   # disparity d (piksel)

    def compute_distance(self, disparity: float) -> float:
        # Z = f × B / d
        if disparity <= 0:
            raise ValueError("Disparity sıfır veya negatif olamaz")
        return (self.f * self.B) / disparity

    def compute_real_size(self,
                          bbox_wide: tuple,
                          distance_m: float) -> MeasurementResult:
        # W = W_piksel × Z / f
        # H = H_piksel × Z / f
        w_px = bbox_wide[2] - bbox_wide[0]
        h_px = bbox_wide[3] - bbox_wide[1]
        width_m  = (w_px * distance_m) / self.f
        height_m = (h_px * distance_m) / self.f
        return MeasurementResult(
            distance_m=distance_m,
            width_m=width_m,
            height_m=height_m
        )
```

---

### 5.5. `geo/gps_localizer.py` ✅

**Sorumluluk:** Otobüsün GPS konumundan panonun dünya koordinatlarını hesaplar.

**Formül:** Otobüs konumu + mesafe (Z) + kamera yönü (heading) → pano lat/lon.

---

### 5.6. `db/` Modülü ✅

**`schema.sql`** — Ana tablolar (measurements, billboards, buses, users, pricing_rules, price_history).

**`schema_organizations.sql`** — Belediye organizasyon yapısı, yetki şeması.

**`database_manager.py`** — Bağlantı havuzu (PgBouncer uyumlu), asyncpg ile async yazma.

---

### 5.7. `web/backend/` — FastAPI ✅ İskelet / 🔄 Endpoint'ler

`main.py` iskelet hazır. `api/routes/` altındaki dosyalar oluşturulmuş, içerik doldurulacak.

---

### 5.8. `web/frontend/` — React + Vite ✅ İskelet

Vite + React + TypeScript projesi `create` edilmiş. `src/` altında bileşenler yazılacak.

---

## 6. Veritabanı Tasarımı

### 6.1. Seçilen Teknoloji Yığını

```
Hızlı Ölçüm Yazma  →  TimescaleDB (PostgreSQL extension)
                        • Hypertable ile otomatik zaman bölümleme
                        • %90'a kadar sıkıştırma
                        • PostGIS uyumlu (aynı instance)

Pano Envanteri     →  PostgreSQL + PostGIS
                        • Coğrafi sorgular (ST_DWithin, ST_Distance)
                        • JOIN, ilişkisel yapı

Hızlı Buffer       →  Redis Stream
                        • Otobüs → Redis → Async PG Writer akışı
                        • Ağ kesintisinde yerel tampon

Fotoğraf           →  S3 / MinIO
```

### 6.2. Ana Tablolar

#### `measurements` (TimescaleDB Hypertable)

```sql
CREATE TABLE measurements (
    time          TIMESTAMPTZ   NOT NULL,         -- Hypertable anahtarı
    billboard_id  UUID,
    bus_id        UUID,
    distance_m    DECIMAL(7,2)  NOT NULL,
    disparity_px  DECIMAL(6,2)  NOT NULL,
    width_m       DECIMAL(6,2)  NOT NULL,
    height_m      DECIMAL(6,2)  NOT NULL,
    confidence    DECIMAL(3,2),
    bus_location  GEOGRAPHY(POINT, 4326) NOT NULL,
    angle_deg     DECIMAL(5,1),
    is_valid      BOOLEAN       DEFAULT TRUE
);

SELECT create_hypertable('measurements', 'time');
SELECT add_compression_policy('measurements', INTERVAL '90 days');
```

#### `billboards` (PostgreSQL + PostGIS)

```sql
CREATE TABLE billboards (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location             GEOGRAPHY(POINT, 4326) NOT NULL,
    address              TEXT,
    district             VARCHAR(100),
    width_m              DECIMAL(6,2)  NOT NULL,
    height_m             DECIMAL(6,2)  NOT NULL,
    area_m2              DECIMAL(8,2)  GENERATED ALWAYS AS (width_m * height_m) STORED,
    billboard_type       VARCHAR(50),   -- Statik, Dijital, LED, Megalight, Raket
    status               VARCHAR(20)    DEFAULT 'active',
    current_monthly_price DECIMAL(10,2),
    measurement_count    INTEGER        DEFAULT 0,
    last_seen_at         TIMESTAMPTZ,
    photo_url            TEXT,
    created_at           TIMESTAMPTZ    DEFAULT NOW()
);

CREATE INDEX idx_billboards_location ON billboards USING GIST (location);
```

---

## 7. Harita Entegrasyonu

### 7.1. Koordinat Hesaplama (GPSLocalizer)

```
Pano Konumu = f(Otobüs GPS, Mesafe Z, Kamera Yönü)

lat_pano = lat_otobüs + (Z × cos(heading)) / 111320
lon_pano = lon_otobüs + (Z × sin(heading)) / (111320 × cos(lat_otobüs))
```

### 7.2. Frontend Harita Bileşeni

**Başlangıç için:** Leaflet.js + OpenStreetMap (ücretsiz, açık kaynak)
**Büyüme sonrası:** Mapbox GL JS (3D, gelişmiş stiller)

**Harita özellikleri:**
- Tüm panolar renkli pin ile gösterilir (kırmızı=büyük, turuncu=orta, yeşil=küçük).
- Cluster görünümü: Yakın panolar otomatik gruplandırılır.
- Tıklama popup: Fotoğraf, boyut, alan, aylık kira tahmini.
- Aktif otobüs konumları (gerçek zamanlı, WebSocket, 10 sn güncelleme).
- Katmanlar: İlçe sınırları, güzergahlar, fiyat ısı haritası.
- GeoJSON dışa aktarma.

### 7.3. Backend Tile Servisi

`pg_tileserv` ile PostGIS verisi doğrudan vektör tile olarak sunulur. Frontend bu tile'ları Leaflet üzerinden çeker.

---

## 8. API Servisleri

### 8.1. Endpoint Listesi (`web/backend/api/routes/`)

| Endpoint | Metod | Açıklama | Yetki |
|---|---|---|---|
| `/api/v1/measurements` | POST | Otobüsten ölçüm verisi al | API Key |
| `/api/v1/billboards` | GET | Pano listesi (filtreli) | JWT |
| `/api/v1/billboards/{id}` | GET | Tek pano detayı + geçmiş | JWT |
| `/api/v1/billboards/{id}/price` | GET | Güncel fiyat hesapla | JWT |
| `/api/v1/billboards/geo` | GET | Bounding box coğrafi sorgu | JWT |
| `/api/v1/pricing/rules` | GET/PUT | Fiyat kurallarını yönet | Admin |
| `/api/v1/map/tiles/{z}/{x}/{y}` | GET | Vektör tile servisi | Public |
| `/api/v1/reports/export` | POST | PDF/Excel rapor | JWT |
| `/api/v1/buses` | GET/POST | Otobüs yönetimi | Admin |
| `/api/v1/auth/login` | POST | JWT üretimi | Public |
| `ws://…/ws/buses` | WebSocket | Gerçek zamanlı otobüs konumları | JWT |

---

## 9. İhtiyaç ve Gider Kalemleri

### 9.1. Donanım

| Kalem | Kapsam | Notlar |
|---|---|---|
| Stereo kamera seti (Geniş + Dar açı) | Araç başına 1 set | IP67, endüstriyel, yüksek FPS |
| Edge computing birimi | Araç başına 1 adet | NVIDIA Jetson Orin Nano veya muadili |
| GPS / GNSS modülü | Araç başına 1 adet | <1m doğruluk, U-blox F9P veya muadili |
| IMU sensörü | Araç başına 1 adet | 6 eksen; titreşim filtresi için |
| 4G/5G modem + anten | Araç başına 1 adet | Endüstriyel, bağlantı kesintisi tamponlu |
| Yerel depolama | Araç başına 1 adet | Min. 128 GB NVMe / SD |
| Güç dönüştürücü + sigortalar | Araç başına 1 set | 12/24V → 5/12V, aşırı akım korumalı |
| Montaj braket ve kablolama | Araç başına 1 set | Titreşime dayanıklı, hava koşullarına uygun |
| Kalibrasyon aparatı (satranç tahtası) | Tesis başına 1 adet | Kurulum + periyodik bakım |

### 9.2. Yazılım ve Lisanslar

| Kalem | Lisans Türü | Notlar |
|---|---|---|
| OpenCV | Açık kaynak, ücretsiz | Stereo kalibrasyon, disparity, görüntü işleme |
| YOLOv8 (Ultralytics) | Açık kaynak; eğitim GPU gerektirir | Özel eğitim için bulut GPU saati gerekebilir |
| FastAPI / Python | Açık kaynak, ücretsiz | Backend API çatısı |
| TimescaleDB Community | Açık kaynak, ücretsiz | Ölçüm zaman serisi |
| PostgreSQL + PostGIS | Açık kaynak, ücretsiz | Pano envanteri ve coğrafi veri |
| Redis | Açık kaynak, ücretsiz | Yazma kuyruğu, cache |
| Leaflet.js + OpenStreetMap | Açık kaynak, ücretsiz | OSM için ODbL lisansı — atıf zorunlu |
| Mapbox GL JS (isteğe bağlı) | Kullanım bazlı ücretli | Tile sayısı aşılırsa ücret oluşur |
| SSL Sertifikası | Yıllık yenileme | API ve web için HTTPS zorunlu |

### 9.3. Bulut / Altyapı

| Kalem | Ölçek | Notlar |
|---|---|---|
| Uygulama sunucusu (API) | 2+ sanal makine | Yük dengeleme için en az 2 örnek |
| Veritabanı sunucusu | 1 ana + 1 yedek | TimescaleDB + PostgreSQL aynı instance |
| Redis sunucusu | 1 adet (başlangıç) | Yüksek yükte cluster'a geçilebilir |
| Nesne depolama | Araç × gün × ~5 MB | Pano fotoğrafları için S3 / MinIO |
| CDN | Frontend statik dosyalar | Dashboard ve harita varlıkları |
| Bant genişliği | Araç başına ~50 MB/gün | Sıkıştırmayla azaltılabilir |
| VPN / Güvenli tünel | Tüm araçlar | Araç–bulut iletişim güvenliği |
| Yedekleme depolama | Aylık snapshot | Felaketten kurtarma planı |

### 9.4. Bağlantı

| Kalem | Kapsam | Notlar |
|---|---|---|
| SIM kart / IoT data paketi | Araç başına 1 hat | ~1.5–3 GB/ay tahmini |
| M2M toplu SIM anlaşması | Filo geneli | Operatörle toplu IoT SIM avantajlı olabilir |

### 9.5. İnsan Kaynağı

| Rol | Tür | Kapsam |
|---|---|---|
| Computer Vision Müh. | Tam zamanlı | OpenCV kalibrasyon, YOLOv8 eğitimi, stereo pipeline |
| Backend Geliştirici | Tam zamanlı | FastAPI, TimescaleDB, PostGIS, Redis |
| Frontend Geliştirici | Tam zamanlı | React, Leaflet, dashboard |
| Gömülü Sistem Müh. | Proje bazlı | Jetson entegrasyonu, donanım montaj/kalibrasyon |
| DevOps | Yarı zamanlı / hizmet | Sunucu, CI/CD, izleme, yedekleme |
| Saha Teknisyeni | Kurulum + bakım | Araçlara donanım kurulumu, periyodik kalibrasyon |
| Belediye personeli eğitimi | Proje sonu | Dashboard kullanımı, fiyat kuralı yönetimi |

### 9.6. Uyumluluk ve Hukuki

| Kalem | Kapsam | Notlar |
|---|---|---|
| KVKK uyumluluk danışmanlığı | Hukuki inceleme | Kamera kayıtları KVKK kapsamında değerlendirilmeli |
| Belediye meclisi / kurul onayı | Resmi izin | Araçlara kamera takılması için onay süreci |
| OpenStreetMap lisans uyumu | ODbL atıf | Haritada OSM kullanılıyorsa kaynak gösterilmeli |

---

## 10. Sonraki Adımlar (TODO)

### 🔴 Öncelik 1 — Core Modüller (Bu hafta / gelecek hafta)

Bu adımlar tamamlanmadan sistem çalışmaz.

#### TODO-1: `core/distance_calculator.py` Tamamla

Bölüm 5.4'teki formülleri implement et:
- `compute_disparity(bbox_wide, bbox_narrow)` → Piksel merkez farkı
- `compute_distance(disparity)` → `Z = f × B / d`
- `compute_real_size(bbox_wide, distance_m)` → `W = W_px × Z / f`
- `MeasurementResult` dataclass: `distance_m`, `width_m`, `height_m`, `confidence`

**Test:** `tests/test_distance_calculator.py` dosyan var, içini doldur:
```python
def test_distance_invariance():
    """Aynı pano farklı mesafelerden aynı boyutu versin."""
    # 30m uzak senaryo
    # 10m yakın senaryo
    # width_m farkı < %3 olmalı
```

---

#### TODO-2: `core/camera_calibration.py` Tamamla

- Kalibrasyon verilerini YAML/JSON'dan yükleme
- `undistort(frame)` metodunu OpenCV ile implement et
- Baseline (B) ve odak uzaklıkları (f_geniş, f_dar) için getter metodları
- **Gerçek kalibrasyon:** Satranç tahtasıyla `cv2.calibrateCamera()` çalıştırıp katsayıları bir kez kaydet

---

#### TODO-3: `core/object_detector.py` — YOLOv8 Entegrasyon

```python
from ultralytics import YOLO

class ObjectDetector:
    def __init__(self, model_path: str):
        self.model = YOLO(model_path)
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        results = self.model(frame, conf=0.70)
        # Detection listesine dönüştür
```

Başlangıç için `yolov8n.pt` (nano) modelini dene. Sonra Türkiye pano verisiyle fine-tune.

---

### 🟡 Öncelik 2 — Backend Endpoint'leri (Bu ay)

#### TODO-4: `web/backend/api/routes/measurements.py`

```python
@router.post("/measurements")
async def receive_measurement(payload: MeasurementPayload, db: AsyncSession):
    # 1. API Key doğrula
    # 2. Redis kuyruğuna yaz
    # 3. 202 Accepted döndür (senkron bekleme yok)
```

#### TODO-5: `web/backend/api/routes/billboards.py`

- `GET /billboards` → Filtreli liste, PostGIS sorgusu
- `GET /billboards/{id}` → Detay + ölçüm geçmişi (TimescaleDB)
- `GET /billboards/geo?bbox=...` → Harita için coğrafi sorgu

#### TODO-6: Redis → TimescaleDB Async Writer

```python
async def flush_worker():
    """Redis kuyruğunu okuyup TimescaleDB'ye toplu yazar."""
    while True:
        batch = await redis.lrange("measurements_queue", 0, 99)
        if batch:
            await db.executemany("INSERT INTO measurements ...", batch)
            await redis.ltrim("measurements_queue", len(batch), -1)
        await asyncio.sleep(1)
```

---

### 🟢 Öncelik 3 — Frontend (Gelecek ay)

#### TODO-7: Harita Bileşeni

```
web/frontend/src/components/
  ├── MapView.tsx          ← Leaflet harita, pin'ler
  ├── BillboardPopup.tsx   ← Tıklama popup
  ├── LayerControl.tsx     ← Katman açma/kapama
  └── BusTracker.tsx       ← Gerçek zamanlı otobüs konumu
```

#### TODO-8: Dashboard Ana Sayfa

```
web/frontend/src/pages/
  ├── Dashboard.tsx        ← Özet kartlar, grafikler
  ├── BillboardList.tsx    ← Filtreli liste
  ├── BillboardDetail.tsx  ← Detay sayfası
  └── Pricing.tsx          ← Fiyat kuralları yönetimi
```

---

### 🔵 Öncelik 4 — Deployment (2. ay sonu)

#### TODO-9: Docker Compose

```yaml
services:
  api:        # FastAPI
  db:         # TimescaleDB + PostGIS
  redis:      # Redis Stream
  pgbouncer:  # Bağlantı havuzu
  tileserv:   # pg_tileserv harita tile
  frontend:   # Nginx + React build
```

#### TODO-10: Kalibrasyon Scripti

Gerçek kameralarla bir kez çalıştırılacak kalibrasyon aracı:
```
python tools/calibrate_cameras.py \
    --wide-device 0 \
    --narrow-device 1 \
    --output config/calibration.yaml
```

---

### 📋 Genel Öneri Sırası

```
Hafta 1–2:  TODO-1 + TODO-2 + TODO-3  (Core formüller + YOLO)
            → Test et: test_distance_calculator.py geçsin
Hafta 3–4:  TODO-4 + TODO-5 + TODO-6  (Backend endpoint'leri)
            → Test et: Postman ile ölçüm POST et, DB'de gör
Ay 2 Hafta 1–2: TODO-7 + TODO-8 (Frontend harita + dashboard)
Ay 2 Hafta 3–4: TODO-9 (Docker) + TODO-10 (Kalibrasyon scripti)
Ay 3:       YOLOv8 fine-tuning + saha testi (1 otobüs, 1 hat)
```

---

## 11. Teknik Kısıtlar ve Bilinmesi Gerekenler

| Kısıt | Detay |
|---|---|
| Min. ölçüm mesafesi | ~3 m — Daha yakında bounding box görüntü dışına taşar |
| Maks. güvenilir mesafe | ~60 m — Daha uzakta disparity < 1 piksel, gürültüye hassas |
| Açı sınırı | < 45° — IMU ile filtrele; daha fazlası geometri bozar |
| Kalibrasyon sıklığı | Her araç kurulumunda + her 3 ayda bir kontrol |
| Frame hızı | Jetson Orin'de YOLOv8n ile ~15–30 FPS beklenir |
| Baseline (B) önerisi | 10–15 cm; çok küçükse disparity hassasiyeti düşer |

---

## 12. Sonuç

Sistem, AI'nın (YOLOv8) pano tespit gücünü OpenCV'nin deterministik geometrik hesabıyla birleştirerek hareket halinden mesafeye bağımsız boyut ölçümü yapar. `edge_pipeline.py` temeli sağlam atılmıştır; öncelikli eksik `core/` modüllerinin formül implementasyonudur. Bu tamamlandığında backend → frontend zinciri hızla kurulabilir.
