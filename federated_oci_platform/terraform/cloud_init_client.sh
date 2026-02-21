#!/bin/bash
# terraform/cloud_init_client.sh — Bootstrap an FL Client Node
# ============================================================================
# Runs as root on first boot via OCI cloud-init.
# Terraform injects: node_id, server_ip, server_port, bucket_url,
#                    git_repo_url, git_branch
# ============================================================================
set -euo pipefail

NODE_ID="${node_id}"
SERVER_IP="${server_ip}"
SERVER_PORT="${server_port}"
BUCKET_URL="${bucket_url}"
GIT_REPO="${git_repo_url}"
GIT_BRANCH="${git_branch}"

LOG_FILE="/var/log/fl_client.log"
exec > /var/log/fl_client_setup.log 2>&1

echo "=========================================="
echo "FedBuff Client Node $NODE_ID Bootstrap — $(date)"
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
    curl

echo "[1/7] System packages installed."

# --- Application Directory ---
APP_DIR="/app"
mkdir -p "$APP_DIR/data"
cd "$APP_DIR"

# --- Clone Repository ---
if [ -d "$APP_DIR/repo" ]; then
    rm -rf "$APP_DIR/repo"
fi
git clone --branch "$GIT_BRANCH" --depth 1 "$GIT_REPO" "$APP_DIR/repo"
echo "[2/7] Repository cloned."

# --- Download Partition Data from OCI Object Storage ---
DATA_FILE="$APP_DIR/data/partition_$NODE_ID.pt"
DOWNLOAD_URL="$BUCKET_URL/partition_$NODE_ID.pt"

echo "[3/7] Downloading partition data: $DOWNLOAD_URL"
wget --retry-connrefused --waitretry=5 --tries=10 \
     --timeout=60 -O "$DATA_FILE" "$DOWNLOAD_URL"

if [ -f "$DATA_FILE" ]; then
    FILE_SIZE=$(stat --format=%s "$DATA_FILE")
    echo "[3/7] Partition downloaded successfully: $DATA_FILE ($FILE_SIZE bytes)"
else
    echo "[3/7] ERROR: Failed to download partition data!"
    echo "       URL: $DOWNLOAD_URL"
    echo "       Continuing anyway — client will use synthetic fallback."
fi

# --- Python Virtual Environment ---
python3 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"

if [ -f "$APP_DIR/repo/federated_oci_platform/requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r "$APP_DIR/repo/federated_oci_platform/requirements.txt"
elif [ -f "$APP_DIR/repo/requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r "$APP_DIR/repo/requirements.txt"
fi
echo "[4/7] Python dependencies installed."

# --- Generate Client .env ---
cat > "$APP_DIR/.env" <<ENVEOF
NODE_ID=$NODE_ID
CLIENT_ID=node_$NODE_ID
SERVER_URL=ws://$SERVER_IP:$SERVER_PORT/ws/fl
DATA_PATH=$APP_DIR/data/partition_$NODE_ID.pt
DATASET=femnist
TOTAL_NODES=10
LOCAL_EPOCHS=3
LEARNING_RATE=0.01
MU=0.01
DP_MAX_GRAD_NORM=1.0
DP_NOISE_MULTIPLIER=1.1
CLIENT_ROLE=legitimate_client
DISPLAY_NAME=CloudNode_$NODE_ID
PARTICIPANT=oci-node-$NODE_ID
ENVEOF

echo "[5/7] Client .env created at $APP_DIR/.env"

# --- Register with Server (retry until server is up) ---
echo "[6/7] Waiting for server to become available..."
MAX_RETRIES=30
RETRY_DELAY=10
for i in $(seq 1 $MAX_RETRIES); do
    HEALTH_CHECK=$(curl -s -o /dev/null -w "%%{http_code}" \
        "http://$SERVER_IP:$SERVER_PORT/health" 2>/dev/null || echo "000")

    if [ "$HEALTH_CHECK" = "200" ]; then
        echo "[6/7] Server is up! (attempt $i)"

        # Register this node
        REGISTER_RESPONSE=$(curl -s -X POST \
            "http://$SERVER_IP:$SERVER_PORT/nodes/register" \
            -H "Content-Type: application/json" \
            -d "{\"task\": \"femnist\", \"role\": \"legitimate_client\", \"display_name\": \"CloudNode_$NODE_ID\"}" \
            2>/dev/null || echo "{}")

        echo "[6/7] Registration response: $REGISTER_RESPONSE"

        # Extract auth token from registration response
        AUTH_TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('token', ''))
except:
    print('')
" 2>/dev/null || echo "")

        if [ -n "$AUTH_TOKEN" ]; then
            echo "AUTH_TOKEN=$AUTH_TOKEN" >> "$APP_DIR/.env"
            echo "[6/7] Auth token received and saved."
        else
            echo "[6/7] WARNING: No auth token received. Client will retry on connect."
        fi
        break
    fi

    echo "  Server not ready (attempt $i/$MAX_RETRIES). Retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
done

# --- Create systemd Service for FL Client ---
CLIENT_WORK_DIR="$APP_DIR/repo/async_federated_learning"

cat > /etc/systemd/system/fl-client.service <<SVCEOF
[Unit]
Description=FedBuff FL Client Node $NODE_ID
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$CLIENT_WORK_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$APP_DIR/venv/bin/python3 client/fl_client.py --env $APP_DIR/.env
Restart=always
RestartSec=10
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable fl-client.service
systemctl start fl-client.service

echo "[7/7] FL Client service started."

echo "=========================================="
echo "FedBuff Client Node $NODE_ID Bootstrap COMPLETE"
echo "  Data path  : $DATA_FILE"
echo "  Server     : ws://$SERVER_IP:$SERVER_PORT/ws/fl"
echo "  Logs       : $LOG_FILE"
echo "  Setup logs : /var/log/fl_client_setup.log"
echo "=========================================="
