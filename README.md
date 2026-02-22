# FedBuff: Asynchronous Robust Federated Learning (ARFL)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)

FedBuff is an advanced, production-ready Asynchronous Federated Learning framework designed to address the critical bottlenecks in traditional synchronous Federated Learning: stragglers (slow clients) and Byzantine failures (malicious clients or corrupted data).

By utilizing an **event-driven asynchronous buffer** and a **two-layer defense mechanism**, FedBuff allows for continuous, secure, and robust global model updates without waiting for the slowest participants.

## 🌟 Key Features

*   **Asynchronous Buffered Aggregation (FedBuff)**: Clients push updates independently. The server aggregates automatically once a configurable buffer size ($K$) is reached, eliminating the straggler problem.
*   **Staleness-Aware Learning**: Implements staleness discounting (polynomial or exponential decay) to ensure delayed updates from slow clients don't degrade the global model.
*   **Two-Layer Byzantine Defense**:
    *   *Layer 1 (Targeted Defense)*: An L2-Norm Gatekeeper efficiently filters out extreme anomalous weights.
    *   *Layer 2 (Robust Aggregation)*: Supports advanced aggregation strategies including Krum, Trimmed Mean, and Coordinate Median alongside standard FedAvg.
*   **SABD (Staleness-Aware Byzantine Detection)**: Sophisticated trust-scoring system combining behavioral reputation (robust Z-scores) and update staleness to dynamically weigh client contributions.
*   **Differential Privacy (DP-SGD)**: Built-in support for client-side Differential Privacy with gradient clipping and noise injection (via Opacus).
*   **Multi-Modality**: Out-of-the-box support for Image data (FEMNIST via CNNs) and Text data (Shakespeare via LSTMs) using the LEAF benchmark format.
*   **Dynamic Node Management**: Secure JWT-based registration, node registry, and MongoDB-backed chunk assignment for data partitioning.
*   **Real-time Telemetry & Dashboard**: Server-Sent Events (SSE) stream training metrics, trust scores, and aggregation times directly to a frontend React dashboard.
*   **Network Simulation**: Test under realistic edge conditions with configurable packet loss, latency bounds, and network partitions.

## 📂 Repository Structure

```text
async_federated_learning/
├── aggregation/        # Robust aggregation strategies (FedAvg, Krum, Trimmed Mean, etc.)
├── attacks/            # Byzantine attack simulations (Sign Flip, Label Flip, Noise)
├── client/             # WebSocket client and FedProx Honest Trainer
├── dashboard/          # React + Vite UI dashboard for monitoring
├── detection/          # Defense mechanisms (SABD, OutlierFilter)
├── evaluation/         # Metrics collection and SSE streaming
├── experiments/        # Scripts for running large-scale benchmarks
├── models/             # PyTorch model definitions (CNN, LSTM)
├── network/            # Network degradation simulator
├── privacy/            # Differential Privacy (DP-SGD engine)
├── scripts/            # Setup and client spawning utilities
├── server/             # FastAPI backend, async buffer, chunk manager
├── config.py           # Centralized Pydantic-based configuration
└── main.py             # FastAPI entrypoint (REST + WebSockets)
```

## 🚀 Setup and Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/DevHacks.git
    cd DevHacks/async_federated_learning
    ```

2.  **Set up the Virtual Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Configure Environment**:
    Create a `.env` file in the root directory (or update the existing one):
    ```env
    JWT_SECRET=your_super_secret_key
    MONGO_URI=mongodb://localhost:27017
    MONGO_DB=fedbuff_db
    ```

4.  **Download Datasets**:
    Follow the instructions in the `data/` directory to download and partition the LEAF benchmarks (FEMNIST / Shakespeare).

## 💻 Usage

### Starting the Server
Run the FastAPI backend using `uvicorn` (handles WebSockets and REST):
```bash
cd async_federated_learning
python main.py
```
*The server will start on `http://0.0.0.0:8765` by default.*

### Spawning Clients
You can spawn multiple clients (both honest and malicious) using the provided script:
```bash
python scripts/spawn_clients.py \
    --url "ws://127.0.0.1:8765/ws/fl" \
    --mode realistic \
    --total 50 \
    --malicious 10 \
    --task femnist
```

### Viewing the Dashboard
Navigate to the `dashboard/` directory, install dependencies, and start the Vite dev server:
```bash
cd dashboard
npm install
npm run dev
```

## ⚙️ Configuration
All hyperparameters and system settings are managed centrally in `config.py`. Key parameters include:
*   `BUFFER_SIZE_K`: Number of updates required to trigger asynchronous aggregation.
*   `MAX_STALENESS`: Maximum allowed delay for an update before rejection.
*   `AGGREGATION_STRATEGY`: Switch between `fedavg`, `krum`, `trimmed_mean`, `coordinate_median`, or `staleness_aware`.
*   `USE_DP`: Toggle Differential Privacy.

## 🛡️ License
This project is developed for DevHacks 2026. All rights reserved.
