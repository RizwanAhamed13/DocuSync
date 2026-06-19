#!/usr/bin/env bash
# =============================================================================
# DocuSync GPU Server — CentOS Deployment Script
# Branch: feat/gpu-server-v2
# Supports: CentOS 7, CentOS 8 Stream, Rocky Linux, AlmaLinux
# Run as a non-root user who has sudo access
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Detect package manager ────────────────────────────────────────────────────
if command -v dnf &>/dev/null; then
    PKG="dnf"
elif command -v yum &>/dev/null; then
    PKG="yum"
else
    die "Neither dnf nor yum found. This script requires CentOS/Rocky/AlmaLinux."
fi
log "Package manager: $PKG"

# =============================================================================
# STEP 1 — Verify GPU
# =============================================================================
log "Step 1: Verifying GPU..."
nvidia-smi &>/dev/null || die "nvidia-smi not found. Install NVIDIA drivers first, then re-run this script."
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
ok "GPU detected: $GPU_NAME ($GPU_MEM)"

# =============================================================================
# STEP 2 — Install Docker
# =============================================================================
log "Step 2: Installing Docker..."
if command -v docker &>/dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    sudo $PKG install -y yum-utils 2>/dev/null || sudo $PKG install -y dnf-utils
    sudo $PKG config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo $PKG install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable --now docker
    ok "Docker installed."
fi

# Add current user to docker group
if ! groups | grep -q docker; then
    sudo usermod -aG docker "$USER"
    warn "Added $USER to docker group. Run 'newgrp docker' or re-login if docker commands fail."
fi

# =============================================================================
# STEP 3 — Install NVIDIA Container Toolkit
# =============================================================================
log "Step 3: Installing NVIDIA Container Toolkit..."
if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi &>/dev/null; then
    ok "NVIDIA Container Toolkit already working."
else
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
        | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo > /dev/null
    sudo $PKG install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    ok "NVIDIA Container Toolkit installed."
fi

# =============================================================================
# STEP 4 — Open firewall port 80
# =============================================================================
log "Step 4: Opening port 80 in firewalld..."
if systemctl is-active --quiet firewalld; then
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --reload
    ok "Port 80 open."
else
    warn "firewalld not running — skipping. Open port 80 manually if needed."
fi

# =============================================================================
# STEP 5 — SELinux volume label
# =============================================================================
log "Step 5: Checking SELinux..."
SELINUX_STATUS=$(getenforce 2>/dev/null || echo "Disabled")
if [ "$SELINUX_STATUS" = "Enforcing" ]; then
    warn "SELinux is Enforcing. Applying container file context to project directory..."
    sudo setsebool -P container_manage_cgroup on
    sudo chcon -Rt svirt_sandbox_file_t "$(pwd)"
    ok "SELinux labels applied."
else
    ok "SELinux: $SELINUX_STATUS — no action needed."
fi

# =============================================================================
# STEP 6 — Build and start Docker Compose services
# =============================================================================
log "Step 6: Building and starting services (first run downloads ~8 GB, takes 10–15 min)..."
docker compose up -d --build
ok "Services started."

# =============================================================================
# STEP 7 — Wait for DocuSync to be healthy
# =============================================================================
log "Step 7: Waiting for DocuSync to be ready..."
MAX_WAIT=180
ELAPSED=0
until curl -sf http://localhost/health > /dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        warn "DocuSync not ready after ${MAX_WAIT}s. Check logs: docker compose logs -f docusync"
        break
    fi
    echo -n "."
done
echo ""
ok "DocuSync is healthy."

# =============================================================================
# STEP 8 — Pull the tagging model into Ollama
# =============================================================================
log "Step 8: Pulling llama3.1:8b into Ollama (~4.7 GB, takes 2–5 min)..."
docker exec ollama ollama pull llama3.1:8b
ok "llama3.1:8b ready."

# =============================================================================
# STEP 9 — Install cloudflared for public access (optional)
# =============================================================================
log "Step 9: Installing cloudflared for public HTTPS tunnel..."
if command -v cloudflared &>/dev/null; then
    ok "cloudflared already installed."
else
    CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.rpm"
    curl -fsSL "$CLOUDFLARED_URL" -o /tmp/cloudflared.rpm
    sudo rpm -ivh /tmp/cloudflared.rpm
    rm /tmp/cloudflared.rpm
    ok "cloudflared installed."
fi

# =============================================================================
# DONE — Print access info
# =============================================================================
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  DocuSync GPU v2 is running!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  Local access     :  ${CYAN}http://localhost${NC}"
echo -e "  LAN access       :  ${CYAN}http://${SERVER_IP}${NC}"
echo ""
echo -e "  For public HTTPS tunnel run:"
echo -e "  ${YELLOW}cloudflared tunnel --url http://localhost:80${NC}"
echo ""
echo -e "  View logs        :  docker compose logs -f"
echo -e "  Stop services    :  docker compose down"
echo -e "  Run benchmark    :  pip install httpx && python benchmark/run_benchmark.py"
echo ""
echo -e "${GREEN}============================================================${NC}"
