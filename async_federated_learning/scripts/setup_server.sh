#!/bin/bash
# scripts/setup_server.sh — Server setup for PC-1

set -e

echo "=============================="
echo "FedBuff Server Setup (PC-1)"
echo "=============================="

# 1. Check Python 3.9+
echo ""
echo "[1/6] Checking Python version..."
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
echo "[2/6] Creating virtual environment..."
$PYTHON_CMD -m venv venv
source venv/bin/activate
echo "  Virtual environment created and activated."

echo ""
echo "[3/6] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "  Dependencies installed."

# 3. Build dashboard if Node.js is available
echo ""
echo "[4/6] Checking for Node.js (dashboard build)..."
if command -v node &>/dev/null && command -v npm &>/dev/null; then
    echo "  Node.js found: $(node --version)"
    echo "  Building dashboard..."
    cd dashboard
    npm install
    npm run build
    cd ..
    echo "  Dashboard built."
else
    echo "  Node.js not found. Dashboard will not be built."
    echo "  Install Node.js from https://nodejs.org/ for the dashboard."
fi

# 4. Create results directory
echo ""
echo "[5/6] Creating results directories..."
mkdir -p results/checkpoints
echo "  Created: results/checkpoints"

# 5. Check for pc1.env
echo ""
echo "[6/6] Checking configuration..."
if [ -f "pc1.env" ]; then
    echo "  Found: pc1.env"
    echo "  Found: users.json" 2>/dev/null || echo "  WARNING: users.json not found"
else
    echo "  WARNING: pc1.env not found!"
    echo "  Run the following command first:"
    echo ""
    echo "    python scripts/create_users.py --server-ip <LAN_IP>"
    echo ""
    echo "  Replace <LAN_IP> with your server's LAN IP address."
fi

echo ""
echo "=============================="
echo "Setup complete!"
echo ""
echo "To start the server:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo "=============================="
