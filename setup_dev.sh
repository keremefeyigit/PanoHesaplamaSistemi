#!/usr/bin/env bash
# =============================================================================
# setup_dev.sh — Akıllı Tabela Sistemi Geliştirme Ortamı Kurulumu
# =============================================================================
# Kullanım:
#   chmod +x setup_dev.sh
#   ./setup_dev.sh           → tam kurulum (ultralytics dahil)
#   ./setup_dev.sh --minimal → sadece test bağımlılıkları (CV/GPU gerektirmez)
#
# Ne yapar:
#   1. venv/ oluşturur
#   2. requirements.txt bağımlılıklarını yükler
#   3. YOLOv8n modelini indirir (sadece tam kurulumda)
#   4. logs/ ve debug_frames/ dizinlerini oluşturur
#   5. Temel doğrulama testini çalıştırır
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
PYTHON_BIN="python3"
MINIMAL=false

# ── Argüman ayrıştırma ───────────────────────────────────────────────────────
for arg in "$@"; do
    case $arg in
        --minimal) MINIMAL=true ;;
        --help|-h)
            echo "Kullanım: ./setup_dev.sh [--minimal]"
            echo "  --minimal   Sadece pytest + numpy kurar (GPU/CV gerektirmez)"
            exit 0
            ;;
    esac
done

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   PanoHesaplamaSistemi — Geliştirme Kurulumu     ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Mod: ${BOLD}$([ "$MINIMAL" = true ] && echo 'Minimal (test only)' || echo 'Tam kurulum')${NC}"
echo ""

# ── Python kontrolü ──────────────────────────────────────────────────────────
if ! command -v "$PYTHON_BIN" &>/dev/null; then
    echo -e "${RED}[HATA] python3 bulunamadı. Lütfen Python 3.10+ kurun.${NC}"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED_MAJOR=3
REQUIRED_MINOR=10
ACTUAL_MINOR=$("$PYTHON_BIN" -c "import sys; print(sys.version_info.minor)")

if [ "$("$PYTHON_BIN" -c "import sys; print(int(sys.version_info >= (3,10)))")" = "0" ]; then
    echo -e "${RED}[HATA] Python 3.10+ gerekli, bulunan: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

# ── Sanal ortam ──────────────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}→ Sanal ortam oluşturuluyor...${NC}"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ venv/ oluşturuldu${NC}"
else
    echo -e "${GREEN}✓ venv/ zaten mevcut${NC}"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── pip güncelleme ───────────────────────────────────────────────────────────
echo -e "${YELLOW}→ pip güncelleniyor...${NC}"
"$VENV_PIP" install --quiet --upgrade pip

# ── Bağımlılık kurulumu ──────────────────────────────────────────────────────
if [ "$MINIMAL" = true ]; then
    echo -e "${YELLOW}→ Minimal bağımlılıklar kuruluyor (numpy + pytest)...${NC}"
    "$VENV_PIP" install --quiet \
        "numpy>=1.24.0" \
        "pytest>=8.0.0" \
        "pytest-asyncio>=0.23.0"
else
    echo -e "${YELLOW}→ requirements.txt bağımlılıkları kuruluyor...${NC}"
    echo -e "  ${YELLOW}(ultralytics/opencv büyük paketler — birkaç dakika sürebilir)${NC}"
    "$VENV_PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"
    echo -e "${GREEN}✓ Tüm bağımlılıklar kuruldu${NC}"

    # YOLOv8n model dosyasını indir (yoksa)
    MODELS_DIR="$PROJECT_ROOT/models"
    mkdir -p "$MODELS_DIR"
    YOLO_BASE="$MODELS_DIR/yolov8n.pt"
    if [ ! -f "$YOLO_BASE" ]; then
        echo -e "${YELLOW}→ YOLOv8n temel modeli indiriliyor (~6MB)...${NC}"
        "$VENV_PYTHON" -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" 2>/dev/null || true
        # ultralytics kendi cache dizinine indirir, buraya da symlink koy
        CACHE_PT="$HOME/.config/Ultralytics/yolov8n.pt"
        [ -f "$CACHE_PT" ] && ln -sf "$CACHE_PT" "$YOLO_BASE" && \
            echo -e "${GREEN}✓ YOLOv8n modeli hazır: $YOLO_BASE${NC}"
    else
        echo -e "${GREEN}✓ YOLOv8n modeli zaten mevcut${NC}"
    fi
fi

# ── Proje dizin yapısı ───────────────────────────────────────────────────────
echo -e "${YELLOW}→ Gerekli dizinler oluşturuluyor...${NC}"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/debug_frames"
mkdir -p "$PROJECT_ROOT/models"
echo -e "${GREEN}✓ logs/, debug_frames/, models/ hazır${NC}"

# ── Doğrulama testi ──────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}▶ Doğrulama testleri çalıştırılıyor...${NC}"
echo "─────────────────────────────────────────────────────"
cd "$PROJECT_ROOT"
"$VENV_PYTHON" -m pytest tests/test_distance_calculator.py -v --tb=short
echo "─────────────────────────────────────────────────────"

# ── Özet ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✓ Kurulum tamamlandı!${NC}"
echo ""
echo -e "Sanal ortamı aktif etmek için:"
echo -e "  ${CYAN}source venv/bin/activate${NC}"
echo ""
echo -e "Testleri çalıştırmak için:"
echo -e "  ${CYAN}./run_tests.sh${NC}"
if [ "$MINIMAL" = false ]; then
    echo ""
    echo -e "Pipeline'ı başlatmak için:"
    echo -e "  ${CYAN}source venv/bin/activate && python3 main.py${NC}"
fi
