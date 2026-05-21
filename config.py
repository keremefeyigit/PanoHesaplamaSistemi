"""
config.py — Merkezi Konfigürasyon Dosyası
Akıllı Tabela Ölçüm Sistemi

Bu dosya; kamera sabitleri, veritabanı bağlantı bilgileri,
model yolları ve Edge Computing parametrelerini merkezi olarak yönetir.
Farklı kamera donanımı kullanıldığında yalnızca bu dosya güncellenir.
"""

from dataclasses import dataclass, field
from pathlib import Path

# ─── Proje Kök Dizini ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# ─── Kamera Parametreleri ──────────────────────────────────────────────────────

@dataclass
class WideAngleCameraConfig:
    """Geniş açı kamera sabitleri (fabrika kalibrasyonu + saha kalibrasyonu)."""
    # Piksel cinsinden odak uzaklığı — kalibrasyonla belirlenir
    focal_length_px: float = 850.0          # f_w  [piksel]
    # Kamera çözünürlüğü
    resolution: tuple[int, int] = (1920, 1080)  # (genişlik, yükseklik)
    # Distorsiyon katsayıları [k1, k2, p1, p2, k3] — OpenCV formatı
    distortion_coeffs: list[float] = field(
        default_factory=lambda: [-0.32, 0.11, 0.0001, -0.0002, -0.04]
    )
    # Kamera matrisi (intrinsic) — cx, cy görüntü merkezi
    cx: float = 960.0
    cy: float = 540.0
    # Maksimum güvenilir mesafe [metre]
    max_reliable_distance_m: float = 30.0
    # Kamera kimliği (OpenCV VideoCapture index)
    device_id: int = 0


@dataclass
class NarrowAngleCameraConfig:
    """Dar açı / telefoto kamera sabitleri."""
    focal_length_px: float = 2380.0         # f_n  [piksel]
    resolution: tuple[int, int] = (1920, 1080)
    distortion_coeffs: list[float] = field(
        default_factory=lambda: [-0.28, 0.09, 0.0001, -0.0001, -0.03]
    )
    cx: float = 960.0
    cy: float = 540.0
    max_reliable_distance_m: float = 120.0
    device_id: int = 1


@dataclass
class DualCameraConfig:
    """İki kamera arasındaki geometrik ilişki sabitleri."""
    wide: WideAngleCameraConfig = field(default_factory=WideAngleCameraConfig)
    narrow: NarrowAngleCameraConfig = field(default_factory=NarrowAngleCameraConfig)

    @property
    def focal_length_ratio(self) -> float:
        """K = f_n / f_w  —  Kalibrasyon ile belirlenen oran (sabit)."""
        return self.narrow.focal_length_px / self.wide.focal_length_px

    # Kameralar arası fiziksel öteleme [metre] — stereo baseline
    baseline_m: float = 0.25
    # Disparity eşik değerleri [piksel]
    min_disparity: float = 1.0
    max_disparity: float = 512.0


# ─── YOLO Model Ayarları ───────────────────────────────────────────────────────

@dataclass
class DetectorConfig:
    """YOLOv8/v10 nesne tespit konfigürasyonu."""
    model_path: Path = BASE_DIR / "models" / "yolov8n_tabela.pt"
    # Güven eşiği — bu değerin altındaki tespitler göz ardı edilir
    confidence_threshold: float = 0.45
    # IoU eşiği (NMS — Non-Maximum Suppression için)
    iou_threshold: float = 0.40
    # Hedef sınıf etiketleri (COCO veya özel eğitim sınıfları)
    # Boş liste verilirse modelin bulduğu HER nesneyi kabul eder (Test için ideal)
    target_classes: list[str] = field(
        default_factory=lambda: ["box", "billboard"]
    )
    # GPU kullanım ayarı ('cuda', 'cpu', 'mps')
    device: str = "cpu"
    # Inference çözünürlüğü (imgsz)
    img_size: int = 640
    # Çoklu frame takibi için tracker (botsort / bytetrack)
    tracker: str = "bytetrack.yaml"


# ─── Veritabanı Ayarları ───────────────────────────────────────────────────────

@dataclass
class PostgreSQLConfig:
    """PostGIS destekli PostgreSQL bağlantı parametreleri."""
    host: str = "localhost"
    port: int = 5432
    database: str = "tabela_db"
    user: str = "tabela_user"
    password: str = "changeme"             # Prod'da env-var ile override edin!
    pool_min_size: int = 2
    pool_max_size: int = 10

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass
class RedisConfig:
    """Redis tampon (buffer) konfigürasyonu."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    # Tampon akışı için Redis Stream anahtarı
    stream_key: str = "tabela:detections"
    # Stream'de tutulacak maksimum kayıt sayısı
    stream_max_len: int = 10_000
    # İşlenmiş verilerin TTL süresi [saniye]
    result_ttl_s: int = 3600


# ─── GPS / GNSS Ayarları ──────────────────────────────────────────────────────

@dataclass
class GPSConfig:
    """GPS modülü ayarları."""
    port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    # NMEA cümlesi türleri
    sentence_types: list[str] = field(
        default_factory=lambda: ["GGA", "RMC"]
    )
    # Minimum yatay konum doğruluğu [metre]
    min_hdop: float = 2.0
    # Coğrafi konumlandırma için kamera bağıl ofset [metre, kuzey-doğu-yukarı]
    camera_offset_ned: tuple[float, float, float] = (2.5, 0.0, 1.8)


# ─── Edge Computing / Pipeline Ayarları ──────────────────────────────────────

@dataclass
class PipelineConfig:
    """Görüntü işleme iş akışı parametreleri."""
    # Kaç karede bir tespit çalıştırılacak (frame skip)
    detection_interval_frames: int = 2
    # Thumbnail maksimum boyutu [piksel]
    thumbnail_max_size: tuple[int, int] = (320, 240)
    # Buluta gönderim için veri paket boyutu [bayt]
    max_upload_payload_bytes: int = 50_000
    # Yerel log dizini
    log_dir: Path = BASE_DIR / "logs"
    # Ara görüntü çıktısı (debug modu)
    debug_output_dir: Path = BASE_DIR / "debug_frames"
    # İşleme thread/worker sayısı
    num_workers: int = 4


# ─── Harita / Coğrafi Ayarlar ─────────────────────────────────────────────────

@dataclass
class MapConfig:
    """Harita ve coğrafi görselleştirme ayarları."""
    # Desteklenen harita sağlayıcıları: 'osm', 'mapbox', 'google'
    provider: str = "osm"
    mapbox_token: str = ""                 # Mapbox kullanımı için
    google_api_key: str = ""               # Google Maps kullanımı için
    # PostGIS projeksiyon kodu (WGS84)
    srid: int = 4326
    # Tane ölçeğinde minimum kümeleme mesafesi [metre]
    cluster_radius_m: float = 5.0


# ─── Birleşik Sistem Konfigürasyonu ──────────────────────────────────────────

@dataclass
class SystemConfig:
    """Tüm alt sistem konfigürasyonlarını bir arada tutan ana sınıf."""
    cameras: DualCameraConfig = field(default_factory=DualCameraConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    postgresql: PostgreSQLConfig = field(default_factory=PostgreSQLConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    gps: GPSConfig = field(default_factory=GPSConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    map: MapConfig = field(default_factory=MapConfig)


# Modül düzeyinde tek örnek (singleton) — projenin her yerinden import edilebilir
config = SystemConfig()
