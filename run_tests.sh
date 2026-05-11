#!/usr/bin/env bash
# =============================================================================
# run_tests.sh — Akıllı Tabela Sistemi Test Çalıştırıcı
# =============================================================================
# Kullanım:
#   chmod +x run_tests.sh   (ilk seferinde)
#   ./run_tests.sh           (tüm testler)
#   ./run_tests.sh -k distance   (sadece belirli testler)
#   ./run_tests.sh -v --tb=long  (herhangi bir pytest argümanı geçilebilir)
#
# Ne yapar:
#   1. venv/ yoksa oluşturur
#   2. Minimal bağımlılıkları yükler (numpy + pytest — CV/GPU gerektirmez)
#   3. pytest'i çalıştırır, çıkış kodunu iletir
# =============================================================================

set -euo pipefail

# ── Renkler ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
PYTHON_BIN="python3"

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   PanoHesaplamaSistemi — Test Çalıştırıcı        ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Python kontrolü ──────────────────────────────────────────────────────────
if ! command -v "$PYTHON_BIN" &>/dev/null; then
    echo -e "${RED}[HATA] python3 bulunamadı. Lütfen Python 3.10+ kurun.${NC}"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}✓ Python $PYTHON_VERSION bulundu${NC}"

# ── Sanal ortam ──────────────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}→ Sanal ortam oluşturuluyor: $VENV_DIR${NC}"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Sanal ortam oluşturuldu${NC}"
else
    echo -e "${GREEN}✓ Sanal ortam mevcut${NC}"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── Minimal bağımlılıklar (CV/GPU olmadan testler çalışır) ───────────────────
echo -e "${YELLOW}→ Test bağımlılıkları kontrol ediliyor...${NC}"
"$VENV_PIP" install --quiet --upgrade pip
"$VENV_PIP" install --quiet \
    "numpy>=1.24.0" \
    "pytest>=8.0.0"
echo -e "${GREEN}✓ Bağımlılıklar hazır${NC}"

# ── Testleri çalıştır ────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}▶ pytest çalıştırılıyor...${NC}"
echo "─────────────────────────────────────────────────────"

cd "$PROJECT_ROOT"

# Kullanıcının geçirdiği ek argümanları ilet (örn. -k distance -v --tb=long)
"$VENV_PYTHON" -m pytest tests/ -v "$@"
EXIT_CODE=$?

echo "─────────────────────────────────────────────────────"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ Tüm testler geçti!${NC}"
else
    echo -e "${RED}${BOLD}✗ Bazı testler başarısız. Yukarıdaki çıktıyı inceleyin.${NC}"
fi

exit $EXIT_CODE
