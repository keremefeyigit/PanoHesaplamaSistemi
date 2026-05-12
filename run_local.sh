#!/usr/bin/env bash
# =============================================================================
# run_local.sh — Akıllı Tabela Sistemi Yerel Çalıştırıcı
# =============================================================================
# Kullanım:
#   ./run_local.sh              → Menü göster
#   ./run_local.sh demo         → Formül demo (donanım gerektirmez)
#   ./run_local.sh simulate     → Tam simülasyon (YOLO yok, dummy kare)
#   ./run_local.sh yolo         → YOLOv8 ile gerçek tespit dene
#   ./run_local.sh pipeline     → Pipeline --no-db ile başlat (sonsuz döngü)
#   ./run_local.sh pipeline-db  → Pipeline + Docker DB ile başlat
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

# ── Venv kontrolü ─────────────────────────────────────────────────────────────
ensure_dirs() {
    mkdir -p "$PROJECT_ROOT/logs" "$PROJECT_ROOT/debug_frames" "$PROJECT_ROOT/models"
}

check_venv() {
    if [ ! -f "$VENV_PYTHON" ]; then
        echo -e "${RED}[HATA] Sanal ortam bulunamadı.${NC}"
        echo -e "Önce kurulum yapın: ${CYAN}./setup_dev.sh${NC}"
        exit 1
    fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║   PanoHesaplamaSistemi — Yerel Çalıştırıcı      ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Mod: Formül Demo (donanım gerektirmez, cv2 YOK) ─────────────────────────
run_demo() {
    ensure_dirs
    echo -e "${CYAN}${BOLD}▶ Formül Demo — Benzer Üçgenler + Disparity${NC}"
    echo "─────────────────────────────────────────────────────"
    cd "$PROJECT_ROOT"
    "$VENV_PYTHON" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.getcwd())
from core.distance_calculator import _similar_triangles_distance, _real_dimension, _disparity_to_distance

print("\n━━━━ Benzer Üçgenler Demo ━━━━")
print("Formül: D = (W × f) / P")
print()
examples = [(3.0, 850.0, 127), (3.0, 850.0, 51), (6.0, 850.0, 85)]
for W, f, P in examples:
    D = _similar_triangles_distance(W, f, P)
    W_back = _real_dimension(D, P, f)
    print(f"  W={W}m, f={f}px, P={P}px  →  D={D:.2f}m  (geri-doğrulama W={W_back:.3f}m)")

print("\n━━━━ Disparity Demo ━━━━")
print("Formül: D = (f × baseline) / disparity")
for disp_px in [5, 15, 30, 60]:
    D = _disparity_to_distance(850.0, 0.25, disp_px)
    print(f"  baseline=0.25m, f=850px, disparity={disp_px}px  →  D={D:.2f}m")

print("\n━━━━ Simülasyon (10m–100m) ━━━━")
print(f"{'Gerçek D':>12} {'Gerçek W':>10} {'Tahmin D':>10} {'Hata%':>8} {'Disp. D':>10} {'D.Hata%':>9}")
print("─" * 65)
from core.distance_calculator import DistanceCalculator
for d, w in [(10,2), (25,3), (50,4), (100,6)]:
    r = DistanceCalculator.simulate(true_distance_m=d, true_width_m=w,
                                     focal_length_px=850.0, baseline_m=0.25)
    print(f"  {r['true_distance_m']:>10.1f}m {r['true_width_m']:>9.1f}m "
          f"{r['estimated_distance_m_triangles']:>9.2f}m "
          f"{r['error_distance_pct_triangles']:>7.2f}% "
          f"{r['estimated_distance_m_disparity']:>9.2f}m "
          f"{r['error_distance_pct_disparity']:>8.2f}%")
print("─" * 65)
PYEOF
    echo "─────────────────────────────────────────────────────"
    echo -e "${GREEN}✓ Demo tamamlandı${NC}"
}

# ── Mod: Mesafe Simülasyonu (cv2 YOK) ────────────────────────────────────────
run_simulate() {
    ensure_dirs
    echo -e "${CYAN}${BOLD}▶ GPS + Mesafe Simülasyonu${NC}"
    echo "─────────────────────────────────────────────────────"
    cd "$PROJECT_ROOT"
    "$VENV_PYTHON" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.getcwd())
from core.distance_calculator import DistanceCalculator
from geo.gps_localizer import GPSLocalizer, GPSFix
from config import config

print("\n── Mesafe Simülasyonu ───────────────────────────────────")
print(f"  Kamera f_w={config.cameras.wide.focal_length_px}px | "
      f"baseline={config.cameras.baseline_m}m | "
      f"K={config.cameras.focal_length_ratio:.2f}")
print()

for d, w in [(10,2), (25,3), (50,4), (75,5), (100,6)]:
    r = DistanceCalculator.simulate(
        true_distance_m=d, true_width_m=w,
        focal_length_px=config.cameras.wide.focal_length_px,
        baseline_m=config.cameras.baseline_m,
    )
    ok = "✓" if r['error_distance_pct_triangles'] < 5 else "⚠"
    print(f"  {ok} D={d:3}m W={w}m → tahmin={r['estimated_distance_m_triangles']:.2f}m hata={r['error_distance_pct_triangles']:.2f}%")

print()
print("── GPS Konum Simülasyonu ────────────────────────────────")
localizer = GPSLocalizer(config.gps)
fix = GPSFix(latitude=39.9208, longitude=32.8541, heading_deg=90.0, hdop=1.2)
for dist in [10, 30, 60]:
    loc = localizer.estimate_sign_location(fix, dist)
    print(f"  Araç=(39.9208, 32.8541) mesafe={dist}m → Tabela=({loc.latitude:.6f}, {loc.longitude:.6f})")
PYEOF
    echo "─────────────────────────────────────────────────────"
    echo -e "${GREEN}✓ Simülasyon tamamlandı${NC}"
}

# ── Mod: YOLOv8 Tespit Deneyi ────────────────────────────────────────────────
run_yolo() {
    ensure_dirs
    echo -e "${CYAN}${BOLD}▶ YOLOv8 Tespit Deneyi${NC}"
    echo "─────────────────────────────────────────────────────"

    # ultralytics kurulu mu?
    if ! "$VENV_PYTHON" -c "import ultralytics" &>/dev/null; then
        echo -e "${YELLOW}→ ultralytics bulunamadı, kuruluyor...${NC}"
        "$PROJECT_ROOT/venv/bin/pip" install --quiet ultralytics
    fi

    # Test görüntüsü var mı?
    TEST_IMG="$PROJECT_ROOT/test_image.jpg"
    if [ ! -f "$TEST_IMG" ]; then
        echo -e "${YELLOW}→ test_image.jpg bulunamadı. Örnek görüntü indiriliyor...${NC}"
        # Wikimedia'dan CC lisanslı sokak görüntüsü
        curl -sL "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/Bikesgone.jpg/800px-Bikesgone.jpg" \
            -o "$TEST_IMG" 2>/dev/null || {
            echo -e "${YELLOW}İndirme başarısız. Siyah kare ile devam ediliyor.${NC}"
        }
    fi

    echo -e "${YELLOW}→ YOLOv8n ile tespit yapılıyor...${NC}"
    cd "$PROJECT_ROOT"
    "$VENV_PYTHON" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.getcwd())

from config import SystemConfig
from core.object_detector import ObjectDetector
import numpy as np
import cv2

cfg = SystemConfig()
cfg.detector.model_path = "yolov8n.pt"   # Genel model, özel eğitim yok
cfg.detector.target_classes = []          # Tüm sınıfları kabul et
cfg.detector.device = "cpu"              # GPU olmayan ortamda çalıştır
cfg.detector.confidence_threshold = 0.25

detector = ObjectDetector(cfg.detector)

# Görüntüyü yükle
img_path = "test_image.jpg"
if os.path.exists(img_path):
    frame = cv2.imread(img_path)
    print(f"  Görüntü: {img_path} ({frame.shape[1]}×{frame.shape[0]} px)")
else:
    frame = np.random.randint(100, 200, (480, 640, 3), dtype=np.uint8)
    print("  Görüntü: sentetik (test_image.jpg bulunamadı)")

print("\n  ── Tespit Sonuçları ──────────────────────")
dets = detector.detect(frame, camera="wide")

if dets:
    for d in dets:
        print(f"  ✓ [{d.class_label}]  güven={d.confidence:.2f}  bbox={d.bbox}")
else:
    print("  ○ Tespit yok (beklenen: genel sınıflar için görüntü gerekli)")

print(f"\n  Toplam {len(dets)} nesne tespit edildi.")
print("\n  ── Mesafe Hesabı (ilk tespit) ───────────────")
if dets:
    from core.distance_calculator import DistanceCalculator
    calc = DistanceCalculator(cfg.cameras)
    meas = calc.from_single_camera(dets[0], known_width_m=3.0)
    print(f"  Tahmini mesafe : {meas.distance_m:.2f} m")
    print(f"  Tahmini genişlik: {meas.real_width_m:.2f} m")
    print(f"  Belirsizlik    : ±{meas.uncertainty_m:.2f} m")
else:
    print("  (Tespit olmadığı için mesafe hesabı atlandı)")
PYEOF
    echo "─────────────────────────────────────────────────────"
    echo -e "${GREEN}✓ YOLOv8 deneyi tamamlandı${NC}"
}

# ── Mod: Pipeline (--no-db) ───────────────────────────────────────────────────
run_pipeline() {
    ensure_dirs
    local MAX_FRAMES="${1:-50}"
    echo -e "${CYAN}${BOLD}▶ Pipeline — Simülasyon Modu (DB yok, ${MAX_FRAMES} kare)${NC}"
    echo -e "${YELLOW}  Durdurmak için: Ctrl+C${NC}"
    echo "─────────────────────────────────────────────────────"

    # opencv kurulu mu? (pipeline için gerekli)
    if ! "$VENV_PYTHON" -c "import cv2" &>/dev/null; then
        echo -e "${YELLOW}→ opencv-python-headless kuruluyor...${NC}"
        "$PROJECT_ROOT/venv/bin/pip" install --quiet opencv-python-headless
    fi

    cd "$PROJECT_ROOT"
    "$VENV_PYTHON" main.py --no-db --max-frames "$MAX_FRAMES"
    echo "─────────────────────────────────────────────────────"
    echo -e "${GREEN}✓ Pipeline tamamlandı${NC}"
}

# ── Mod: Pipeline + Docker DB ─────────────────────────────────────────────────
run_pipeline_db() {
    if ! command -v docker &>/dev/null; then
        echo -e "${RED}[HATA] Docker bulunamadı. Lütfen Docker kurun.${NC}"
        echo -e "Veya DB olmadan çalıştırın: ${CYAN}./run_local.sh pipeline${NC}"
        exit 1
    fi

    COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo -e "${RED}[HATA] docker-compose.yml bulunamadı.${NC}"
        echo -e "Oluşturmak için: ${CYAN}./run_local.sh db-up${NC}"
        exit 1
    fi

    echo -e "${YELLOW}→ Docker servisleri başlatılıyor (PG + Redis)...${NC}"
    docker compose -f "$COMPOSE_FILE" up -d
    echo -e "${GREEN}✓ Docker hazır${NC}"
    sleep 2

    echo -e "${CYAN}${BOLD}▶ Pipeline başlatılıyor (DB ile)...${NC}"
    echo -e "${YELLOW}  Durdurmak için: Ctrl+C${NC}"
    cd "$PROJECT_ROOT"
    "$VENV_PYTHON" main.py --max-frames 100 || true

    echo ""
    echo -e "${YELLOW}→ Docker servisleri durduruluyor...${NC}"
    docker compose -f "$COMPOSE_FILE" down
    echo -e "${GREEN}✓ Temizlik tamamlandı${NC}"
}

# ── Mod: Sunucular (Frontend & Backend) ──────────────────────────────────────
run_servers() {
    echo -e "${CYAN}${BOLD}▶ Frontend ve Backend Sunucuları Başlatılıyor...${NC}"
    echo "─────────────────────────────────────────────────────"
    
    # npm yüklü mü kontrol et (frontend için)
    if ! command -v npm &>/dev/null; then
        echo -e "${RED}[HATA] npm bulunamadı. Lütfen Node.js kurun.${NC}"
        exit 1
    fi

    # Backend bağımlılıklarını kur (varsa)
    if [ -f "$PROJECT_ROOT/web/backend/requirements.txt" ]; then
        echo -e "${YELLOW}→ Backend bağımlılıkları kontrol ediliyor...${NC}"
        "$PROJECT_ROOT/venv/bin/pip" install -r "$PROJECT_ROOT/web/backend/requirements.txt" --quiet
    fi

    echo -e "${YELLOW}→ Backend (FastAPI) başlatılıyor...${NC}"
    cd "$PROJECT_ROOT/web/backend"
    PYTHONPATH="$PROJECT_ROOT" "$VENV_PYTHON" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
    
    echo -e "${YELLOW}→ Frontend (Vite/React) başlatılıyor...${NC}"
    cd "$PROJECT_ROOT/web/frontend"
    # Bağımlılıklar yoksa kur
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}→ npm install çalıştırılıyor...${NC}"
        npm install --silent
    fi
    npm run dev &
    FRONTEND_PID=$!
    
    echo -e "${GREEN}✓ Sunucular başlatıldı.${NC}"
    echo -e "  Backend:  ${CYAN}http://localhost:8000${NC}"
    echo -e "  Frontend: ${CYAN}http://localhost:5173${NC}"
    echo -e "${YELLOW}  Durdurmak için: Ctrl+C${NC}"
    echo "─────────────────────────────────────────────────────"
    
    # Ctrl+C için trap (çıkışta child process'leri de öldürür)
    trap "echo -e '\n${YELLOW}Sunucular kapatılıyor...${NC}'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
    
    wait $BACKEND_PID $FRONTEND_PID
}

# ── Mod: docker-compose.yml oluştur ──────────────────────────────────────────
create_compose() {
    COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
    if [ -f "$COMPOSE_FILE" ]; then
        echo -e "${YELLOW}docker-compose.yml zaten mevcut.${NC}"
        return
    fi
    cat > "$COMPOSE_FILE" << 'YAML'
version: "3.9"

services:
  postgres:
    image: postgis/postgis:16-3.4
    container_name: tabela_postgres
    environment:
      POSTGRES_DB: tabela_db
      POSTGRES_USER: tabela_user
      POSTGRES_PASSWORD: changeme
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/01_schema.sql
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "tabela_user", "-d", "tabela_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: tabela_redis
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
YAML
    echo -e "${GREEN}✓ docker-compose.yml oluşturuldu${NC}"
}

# ── Menü ──────────────────────────────────────────────────────────────────────
show_menu() {
    print_banner
    echo -e "  ${BOLD}Bir mod seçin:${NC}"
    echo ""
    echo -e "  ${GREEN}1)${NC} demo         — Formül demonstrasyonu  ${YELLOW}(hızlı, donanım yok)${NC}"
    echo -e "  ${GREEN}2)${NC} simulate     — Mesafe simülasyonu tablosu"
    echo -e "  ${GREEN}3)${NC} yolo         — YOLOv8 ile gerçek tespit dene"
    echo -e "  ${GREEN}4)${NC} pipeline     — Pipeline simülasyon (DB yok)"
    echo -e "  ${GREEN}5)${NC} db-up        — docker-compose.yml oluştur + DB başlat"
    echo -e "  ${GREEN}6)${NC} pipeline-db  — Pipeline + Docker DB (tam sistem)"
    echo -e "  ${GREEN}7)${NC} servers      — Frontend ve Backend Sunucularını Başlat"
    echo ""
    read -rp "  Seçim (1-7 veya mod adı): " choice
    echo ""
    case "$choice" in
        1|demo)         run_demo ;;
        2|simulate)     run_simulate ;;
        3|yolo)         run_yolo ;;
        4|pipeline)     run_pipeline ;;
        5|db-up)
            create_compose
            docker compose -f "$PROJECT_ROOT/docker-compose.yml" up -d
            echo -e "${GREEN}✓ DB ayakta: PG=5432, Redis=6379${NC}"
            ;;
        6|pipeline-db)  create_compose; run_pipeline_db ;;
        7|servers)      run_servers ;;
        *) echo -e "${RED}Geçersiz seçim.${NC}" ;;
    esac
}

# ── Giriş Noktası ─────────────────────────────────────────────────────────────
check_venv
print_banner

MODE="${1:-menu}"
case "$MODE" in
    demo)        run_demo ;;
    simulate)    run_simulate ;;
    yolo)        run_yolo ;;
    pipeline)    run_pipeline "${2:-50}" ;;
    pipeline-db) create_compose; run_pipeline_db ;;
    db-up)
        create_compose
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" up -d
        echo -e "${GREEN}✓ DB ayakta: PG=5432, Redis=6379${NC}"
        ;;
    db-down)
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" down
        echo -e "${GREEN}✓ DB durduruldu${NC}"
        ;;
    servers)     run_servers ;;
    menu)        show_menu ;;
    *)
        echo -e "${RED}Bilinmeyen mod: $MODE${NC}"
        echo -e "Geçerli modlar: demo | simulate | yolo | pipeline | pipeline-db | db-up | db-down | servers"
        exit 1
        ;;
esac
