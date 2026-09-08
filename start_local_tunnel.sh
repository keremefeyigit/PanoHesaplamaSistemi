#!/usr/bin/env bash
# =============================================================================
# start_local_tunnel.sh — Kurumsal Filtreyi Aşmak İçin Yerel SSH Tüneli Başlatıcı
# =============================================================================

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# Konfigürasyon (Varsayılan veya Ortam Değişkeni)
SSH_KEY="${SSH_KEY:-$HOME/.ssh/proje}"
SERVER_IP="${SERVER_IP:-127.0.0.1}"
PORT="${PORT:-8080}"

echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗"
echo -e "║   PanoHesaplamaSistemi — Yerel SSH Tünel Bağlantısı          ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}→ SSH Tüneli kuruluyor (${SERVER_IP} -> localhost:${PORT})...${NC}"

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}[HATA] SSH anahtarı bulunamadı: $SSH_KEY${NC}"
    exit 1
fi

echo -e "${GREEN}✓ SSH Anahtarı doğrulandı.${NC}"
echo -e "${GREEN}✓ Bağlantı kuruldu!${NC}"
echo ""
echo -e "👉 Tarayıcınızda şu adresi açın: ${CYAN}${BOLD}http://localhost:${PORT}${NC}"
echo -e "${YELLOW}  (Bağlantıyı açık tutmak için bu terminali kapatmayın. Durdurmak için: Ctrl+C)${NC}"
echo "─────────────────────────────────────────────────────────────"

# Start the port-forwarding SSH tunnel
ssh -i "$SSH_KEY" -N -L ${PORT}:localhost:${PORT} root@${SERVER_IP} -o StrictHostKeyChecking=no
