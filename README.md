# FedBuff — Buffered Async Federated Learning

A production-quality backend for Buffered Asynchronous Federated Learning, designed for a 4-PC multi-task demonstration environment.

## Overview

FedBuff simulates a network of 6 concurrent clients from 3 physical client machines. Each participant (Alice, Bob, Mallory) runs two concurrent client processes — one for image classification (FEMNIST) and one for next-character prediction (Shakespeare). This demonstrates heterogeneous multi-task federated learning with Byzantine fault tolerance.

## Architecture

```
[6 CLIENT PROCESSES across 3 PCs]  <-->  [BACKEND AGGREGATOR SERVER]  <-->  [TELEMETRY DASHBOARD]
   (Edge Tier — 2 processes per PC)         (Server Tier / FastAPI)            (Observer Tier / React)
```

### PC Assignments

| Machine | Participant | Process 1 | Process 2 | Behavior |
|---------|-------------|-----------|-----------|----------|
| PC-1 | Server | Server + Dashboard | — | Aggregation, defense, telemetry |
| PC-2 | Alice | FEMNIST client | Shakespeare client | Honest |
| PC-3 | Bob | FEMNIST client | Shakespeare client | Honest |
| PC-4 | Mallory | FEMNIST client | Shakespeare client | Malicious (sign-flip) |

### Defense Layers

1. **Layer 1 — Gatekeeper (L2 Norm):** Pre-filters incoming updates by checking the L2 norm of weight diffs. Updates exceeding the threshold are rejected before entering the buffer.
2. **Layer 2 — Robust Aggregation:** After buffer drains, applies one of four strategies:
   - **Multi-Krum (SABD):** Selects the most trusted subset of updates
   - **Trimmed Mean:** Removes extreme coordinate values before averaging
   - **Coordinate Median:** Takes the median per coordinate
   - **FedAvg:** Baseline weighted average (no Byzantine defense)

## Quick Start

### 1. Server Setup (PC-1)

```bash
# Clone and enter the repository
cd fedbuff

# Run setup script
bash scripts/setup_server.sh

# Generate user credentials
source venv/bin/activate
python scripts/create_users.py --server-ip <YOUR_LAN_IP>

# Start the server
python main.py
```

### 2. Client Setup (PC-2, PC-3, PC-4)

```bash
# Copy the repo and appropriate env files to each client PC
cd fedbuff
bash scripts/setup_client.sh

# Copy env files from PC-1:
#   PC-2: pc2_img.env, pc2_txt.env
#   PC-3: pc3_img.env, pc3_txt.env
#   PC-4: pc4_img.env, pc4_txt.env

# Start both client processes
source venv/bin/activate
python client/fl_client.py --env pc2_img.env &
python client/fl_client.py --env pc2_txt.env &
wait
```

### 3. Demo Mode (Faster)

```bash
python client/fl_client.py --env pc2_img.env --demo-speed &
python client/fl_client.py --env pc2_txt.env --demo-speed &
wait
```

## LEAF Data Setup (Optional)

The system uses synthetic fallback data by default. For real data:

```bash
git clone https://github.com/TalwalkarLab/leaf.git

# FEMNIST
cd leaf/data/femnist && ./preprocess.sh -s niid --sf 0.05 -k 0 -t sample
# Copy leaf/data/femnist/data/ -> fedbuff/data/femnist/data/

# Shakespeare
cd leaf/data/shakespeare && ./preprocess.sh -s niid --sf 0.2 -k 0 -t sample
# Copy leaf/data/shakespeare/data/ -> fedbuff/data/shakespeare/data/
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ws/fl?token=&task=` | WebSocket | FL client connection |
| `/health` | GET | Server health check |
| `/model/latest?task=` | GET | Latest model weights |
| `/metrics` | GET | Prometheus metrics |
| `/admin/clients` | GET | Connected clients (admin) |
| `/telemetry/stream` | GET | SSE telemetry stream |

## Running Experiments

```bash
# Full experiment sweep
python experiments/run_experiments.py

# SABD detection proof
python experiments/sabd_proof.py
```

## Running Tests

```bash
pytest tests/ -v
```

## Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## Project Structure

```
fedbuff/
├── main.py                    # FastAPI server entrypoint
├── config.py                  # Configuration (Pydantic BaseSettings)
├── messages.py                # WebSocket message schemas
├── aggregation/               # Aggregation strategies
├── attacks/                   # Byzantine attack implementations
├── client/                    # FL client (edge tier)
├── server/                    # Server components
├── detection/                 # Defense layers
├── evaluation/                # Metrics and telemetry
├── experiments/               # Offline experiments
├── models/                    # Neural network architectures
├── privacy/                   # Differential privacy
├── dashboard/                 # React telemetry dashboard
├── scripts/                   # Setup and utility scripts
├── tests/                     # Test suite
└── results/                   # Output directory
```

## License

See COMPONENT_ATTRIBUTION.md for third-party component attributions.
