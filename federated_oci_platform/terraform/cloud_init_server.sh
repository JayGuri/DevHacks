#!/bin/bash
# terraform/cloud_init_server.sh — Bootstrap the FL Central Server
# ============================================================================
# Runs as root on first boot via OCI cloud-init.
# Installs Python deps, clones repo, configures environment, starts services.
# ============================================================================
set -euo pipefail

exec > /var/log/fl_server_setup.log 2>&1
echo "=========================================="
echo "FedBuff Server Bootstrap — $(date)"
echo "=========================================="

# --- System Packages ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    wget \
    curl \
    nginx \
    nodejs \
    npm

echo "[1/6] System packages installed."

# --- Application Directory ---
APP_DIR="/app"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# --- Clone Repository ---
if [ -d "$APP_DIR/repo" ]; then
    rm -rf "$APP_DIR/repo"
fi
git clone --branch "${git_branch}" --depth 1 "${git_repo_url}" "$APP_DIR/repo"
echo "[2/6] Repository cloned: ${git_repo_url} (branch: ${git_branch})"

# --- Python Virtual Environment ---
python3 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"

# Install dependencies
if [ -f "$APP_DIR/repo/federated_oci_platform/requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r "$APP_DIR/repo/federated_oci_platform/requirements.txt"
elif [ -f "$APP_DIR/repo/requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r "$APP_DIR/repo/requirements.txt"
fi
echo "[3/6] Python dependencies installed."

# --- Generate JWT Secret ---
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "[4/6] JWT secret generated."

# --- Generate Server .env ---
cat > "$APP_DIR/.env" <<ENVEOF
JWT_SECRET=$JWT_SECRET
SERVER_HOST=0.0.0.0
SERVER_PORT=${server_port}
BUFFER_SIZE_K=3
AGGREGATION_STRATEGY=krum
L2_NORM_THRESHOLD=10000.0
MAX_STALENESS=10
MIN_UPDATES_FOR_AGGREGATION=2
MAX_WAIT_SECONDS=15.0
MAX_UPDATES_PER_BATCH=20
CLIENT_HEARTBEAT_TIMEOUT=120.0
HEARTBEAT_CHECK_INTERVAL=15.0
LOG_LEVEL=INFO
MODEL_CHECKPOINT_DIR=$APP_DIR/results/checkpoints
RESULTS_DIR=$APP_DIR/results
ENVEOF

echo "[5/6] Server .env created at $APP_DIR/.env"

# --- Create Results Directories ---
mkdir -p "$APP_DIR/results/checkpoints"

# --- Create systemd Service for FL Server ---
SERVER_WORK_DIR="$APP_DIR/repo/async_federated_learning"

cat > /etc/systemd/system/fl-server.service <<SVCEOF
[Unit]
Description=FedBuff FL Central Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SERVER_WORK_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$APP_DIR/venv/bin/python3 main.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/fl_server.log
StandardError=append:/var/log/fl_server.log

# Load our generated .env
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable fl-server.service
systemctl start fl-server.service

echo "[6/6] FL Server service started."

# --- Optional: Nginx Reverse Proxy for Dashboard ---
cat > /etc/nginx/sites-available/fl-dashboard <<NGXEOF
server {
    listen 80;
    server_name _;

    # Proxy WebSocket connections to FL server
    location /ws/ {
        proxy_pass http://127.0.0.1:${server_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }

    # Proxy API requests to FL server
    location /api/ {
        proxy_pass http://127.0.0.1:${server_port}/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # Proxy telemetry stream
    location /telemetry/ {
        proxy_pass http://127.0.0.1:${server_port}/telemetry/;
        proxy_set_header Host \$host;
        proxy_buffering off;
        proxy_cache off;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:${server_port}/health;
    }
}
NGXEOF

ln -sf /etc/nginx/sites-available/fl-dashboard /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

echo "=========================================="
echo "FedBuff Server Bootstrap COMPLETE"
echo "Server running on port ${server_port}"
echo "Nginx proxy on port 80"
echo "Logs: /var/log/fl_server.log"
echo "=========================================="
