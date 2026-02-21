#!/bin/bash
# scripts/setup_client.sh — Client setup for PC-2, PC-3, PC-4

set -e

echo "=============================="
echo "FedBuff Client Setup"
echo "=============================="

# Parse optional flag
WITH_LEAF_DATA=false
for arg in "$@"; do
    if [ "$arg" == "--with-leaf-data" ]; then
        WITH_LEAF_DATA=true
    fi
done

# 1. Check Python 3.9+
echo ""
echo "[1/5] Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>/dev/null || python --version 2>/dev/null || echo "not found")
echo "  Found: $PYTHON_VERSION"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "  ERROR: Python 3.9+ is required but not found."
    echo "  Install Python from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
    PYTHON_CMD="python"
fi

# 2. Create virtual environment and install dependencies
echo ""
echo "[2/5] Creating virtual environment..."
$PYTHON_CMD -m venv venv
source venv/bin/activate
echo "  Virtual environment created and activated."

echo ""
echo "[3/5] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "  Dependencies installed."

# 3. Create data and results directories
echo ""
echo "[4/5] Creating data directories..."
mkdir -p data/femnist/data/train data/femnist/data/test
mkdir -p data/shakespeare/data/train data/shakespeare/data/test
mkdir -p results
echo "  Created: data/femnist/data/{train,test}"
echo "  Created: data/shakespeare/data/{train,test}"
echo "  Created: results"

# 4. LEAF data instructions
if [ "$WITH_LEAF_DATA" = true ]; then
    echo ""
    echo "[LEAF DATA] To download and preprocess LEAF benchmark data:"
    echo ""
    echo "  # Clone LEAF repository"
    echo "  git clone https://github.com/TalwalkarLab/leaf.git"
    echo ""
    echo "  # FEMNIST data"
    echo "  cd leaf/data/femnist && ./preprocess.sh -s niid --sf 0.05 -k 0 -t sample"
    echo "  Copy leaf/data/femnist/data/ -> fedbuff/data/femnist/data/"
    echo ""
    echo "  # Shakespeare data"
    echo "  cd leaf/data/shakespeare && ./preprocess.sh -s niid --sf 0.2 -k 0 -t sample"
    echo "  Copy leaf/data/shakespeare/data/ -> fedbuff/data/shakespeare/data/"
    echo ""
    echo "  Note: If no LEAF data is found, the client will use synthetic fallback data."
fi

# 5. Check for env files
echo ""
echo "[5/5] Checking configuration..."
ENV_FOUND=false

for env_file in pc2_img.env pc2_txt.env pc3_img.env pc3_txt.env pc4_img.env pc4_txt.env; do
    if [ -f "$env_file" ]; then
        echo "  Found: $env_file"
        ENV_FOUND=true
    fi
done

if [ "$ENV_FOUND" = false ]; then
    echo "  WARNING: No client env files found!"
    echo "  Copy the appropriate env files from PC-1 (after running create_users.py)."
    echo ""
    echo "  For PC-2 (Alice): pc2_img.env, pc2_txt.env"
    echo "  For PC-3 (Bob):   pc3_img.env, pc3_txt.env"
    echo "  For PC-4 (Mallory): pc4_img.env, pc4_txt.env"
fi

echo ""
echo "=============================="
echo "Setup complete!"
echo ""
echo "To start both client processes (example for PC-2 / Alice):"
echo ""
echo "  source venv/bin/activate"
echo "  python client/fl_client.py --env pc2_img.env &"
echo "  python client/fl_client.py --env pc2_txt.env &"
echo "  wait"
echo ""
echo "For demo mode (faster, 1 epoch per round):"
echo "  python client/fl_client.py --env pc2_img.env --demo-speed &"
echo "  python client/fl_client.py --env pc2_txt.env --demo-speed &"
echo "  wait"
echo "=============================="
