# FedBuff — Local Federated Learning Platform (MongoDB Backend)

Distributed asynchronous federated learning (FedBuff architecture) designed to run locally, using **MongoDB Atlas** as the data partition backbone to simulate distributed clients.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Local System / Network                      │
│                                                              │
│                      ┌────────────────┐                      │
│                      │ MongoDB Atlas   │                      │
│                      │ (Shared DB)     │                      │
│                      └───────┬────────┘                      │
│                              │ MONGO_URI                     │
│    ┌─────────────────────────┼─────────────────────────┐     │
│    │                         │                         │     │
│  ┌─┴────────────────┐   ┌────┴────┐               ┌────┴────┐│
│  │ Central Server   │   │ Node 0   │               │ Node N   ││
│  │ FastAPI:8765     │   │ Client   │   . . .       │ Client   ││
│  │ AsyncBuffer      │   │          │               │          ││
│  └────────┬─────────┘   └────┬─────┘               └────┬─────┘│
│           │ ws://            │                          │      │
│           └──────────────────┼──────────────────────────┘      │
│                              │                                 │
└──────────────────────────────┴─────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites
- Python 3.9+ with pip
- MongoDB Atlas account/cluster
- `.env` configured properly (see Setup below)

### 2. Setup MongoDB Configuration
Do **NOT** commit your password to version control!
1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and replace `<username>:<password>` with your real MongoDB Atlas credentials:
   ```
   MONGO_URI="mongodb+srv://sakshat193_db_user:YOUR_PASSWORD@cluster0.ovvgemi.mongodb.net/?appName=Cluster0"
   MONGO_DB="fedbuff_db"
   ```

### 3. Phase 1: Partition Data and Upload to MongoDB

Install requirements:
```bash
pip install -r requirements.txt
```

Download the dataset, partition it into non-IID shards using a Dirichlet distribution, and upload directly to your MongoDB Atlas cluster:
```bash
# Our Python scripts now automatically load credentials from the .env file!
python scripts/partition_data.py --num_partitions 10 --alpha 0.5
```
*Note: This will serialize the PyTorch tensors and store them as `bson.Binary` in the `fedbuff_db.partitions` collection.*

### 4. Phase 2: Start the Central Server

In a new terminal, start the Aggregator:
```bash
cd async_federated_learning
python main.py
```
*The server will start on `ws://0.0.0.0:8765/ws/fl`.*

### 5. Phase 3: Start FL Client Nodes

Each client simulates a separate device by fetching its specific non-IID partition (`NODE_ID`) from MongoDB.

Open multiple terminals (one for each client) and run:

**Terminal (Node 0):**
```bash
# Windows PowerShell
$env:NODE_ID="0"; python client/fl_client.py --env ../.env

# Linux/Mac
NODE_ID=0 python client/fl_client.py --env ../.env
```

**Terminal (Node 1):**
```bash
# Windows PowerShell
$env:NODE_ID="1"; python client/fl_client.py --env ../.env

# Linux/Mac
NODE_ID=1 python client/fl_client.py --env ../.env
```

## File Structure

```
federated_oci_platform/
├── .env.example                   # Example config (copy to .env)
├── scripts/
│   └── partition_data.py          # Partitions MNIST and uploads to MongoDB
├── async_federated_learning/
│   ├── client/
│   │   ├── mongo_loader.py        # MongoDB DataLoader (fetches by NODE_ID)
│   │   └── fl_client.py           # FL client (loads from Mongo, auto-reconnects)
│   └── server/
│       └── fl_server.py           # Server wrapper
├── requirements.txt               # Dependencies (now includes pymongo)
└── README.md                      # This file
```

## Key Design Decisions

1. **MongoDB Atlas Backend**: By using `pymongo.server_api.ServerApi('1')`, we achieve stable, cloud-based partition storage. The large `.pt` shard files are turned into `bson.Binary` records, simulating a real-world scenario where clients fetch remote data.
2. **Dirichlet Non-IID**: Alpha=0.5 creates realistically skewed data partitions to test convergence under heterogeneity.
3. **Dynamic Server & Reconnection**: The server listens dynamically, and clients feature exponential backoff retry loops. Nodes can be killed and restarted locally to simulate device failure.
