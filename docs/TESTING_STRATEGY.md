# Testing Strategy — Federated Learning on OCI

Comprehensive validation plan for the distributed FL deployment on Oracle Cloud Infrastructure.

---

## 1. Local Validation (Before Cloud Deployment)

### 1.1 Partition Data Script

```bash
# Run the partitioner locally
cd federated_oci_platform
python scripts/partition_data.py --num_partitions 10 --alpha 0.5 --output_dir ./partitions/mnist

# Verify output:
# - 10 .pt files created (partition_0.pt through partition_9.pt)
# - partition_stats.json shows non-IID distribution
# - Each partition has different dominant class (alpha=0.5 should give heavy skew)
```

**What to check in `partition_stats.json`:**
- Each partition should have a `dominant_class_pct` significantly above 10% (IID baseline)
- Partitions should NOT all have the same dominant class
- Total samples across all partitions should equal 70,000 (MNIST train + test)

### 1.2 Cloud Loader

```bash
# Test CloudPartitionLoader locally with a real partition
python -c "
from async_federated_learning.client.cloud_loader import CloudPartitionLoader
import os
os.environ['DATA_PATH'] = './partitions/mnist/partition_0.pt'
loader = CloudPartitionLoader()
dl = loader.get_dataloader()
batch = next(iter(dl))
print(f'Batch images shape: {batch[0].shape}')
print(f'Batch labels shape: {batch[1].shape}')
print(f'Total samples: {loader.num_samples}')
print(f'Label distribution: {batch[1][:10]}')
"
```

**Expected:** Images shape `(32, 1, 28, 28)`, labels shape `(32,)`, labels should show class skew.

### 1.3 Syntax Validation

```bash
python -m py_compile scripts/partition_data.py
python -m py_compile async_federated_learning/client/cloud_loader.py
python -m py_compile async_federated_learning/client/fl_client.py
python -m py_compile async_federated_learning/server/fl_server.py
```

All should complete with no output (success = silence).

### 1.4 Local End-to-End Smoke Test

```bash
# Terminal 1: Start the server
cd async_federated_learning
python main.py

# Terminal 2: Start a client with a local partition
export NODE_ID=0
export CLIENT_ID=node_0
export SERVER_URL=ws://localhost:8765/ws/fl
export DATA_PATH=../partitions/mnist/partition_0.pt
export DATASET=femnist
export AUTH_TOKEN=<token from /nodes/register>
python client/fl_client.py --env /dev/null
```

**Verify:** Client prints startup banner, connects to server, starts training rounds.

---

## 2. Infrastructure Validation (After `terraform apply`)

### 2.1 Terraform Plan Review

```bash
cd terraform
terraform init
terraform plan -out=tfplan

# Review the plan:
# - 1 VCN, 1 subnet, 1 IGW, 1 route table, 1 security list
# - 1 Object Storage bucket
# - 1 server instance (VM.Standard.A1.Flex, 1 OCPU, 6GB)
# - 3 client instances (VM.Standard.A1.Flex, 1 OCPU, 6GB each)
# Total: 4 OCPUs, 24GB RAM = fits within OCI Always Free
```

### 2.2 SSH Into Server

```bash
# Get the server IP from terraform output
terraform output server_public_ip

# SSH in
ssh ubuntu@<SERVER_IP>

# Check cloud-init completed successfully
sudo cat /var/log/fl_server_setup.log
# Should end with "FedBuff Server Bootstrap COMPLETE"

# Check cloud-init system log
sudo cat /var/log/cloud-init-output.log | tail -50

# Verify the FL server is running
sudo systemctl status fl-server
curl http://localhost:8765/health
# Expected: {"status": "ok", "tasks": {...}, "connected_clients": 0}

# Check server logs
sudo tail -f /var/log/fl_server.log
```

### 2.3 SSH Into Client Nodes

```bash
# Get client IPs
terraform output client_public_ips

# SSH into each client (repeat for each)
ssh ubuntu@<CLIENT_0_IP>

# Check bootstrap completed
sudo cat /var/log/fl_client_setup.log
# Should end with "FedBuff Client Node 0 Bootstrap COMPLETE"

# Verify partition data was downloaded
ls -la /app/data/
# Expected: partition_0.pt (several MB)

# Verify .env was generated correctly
cat /app/.env
# Should show NODE_ID=0, SERVER_URL=ws://<server_ip>:8765/ws/fl, etc.

# Check FL client service
sudo systemctl status fl-client

# Check client training logs
sudo tail -f /var/log/fl_client.log
# Expected: Startup banner + training round logs with loss values
```

### 2.4 Common Issues

| Symptom | Check | Fix |
|---------|-------|-----|
| `partition_X.pt` not found | `ls /app/data/` | Verify bucket PAR URL is correct |
| Client can't connect to server | `curl http://SERVER_IP:8765/health` from client | Check security list has port 8765 open |
| `ModuleNotFoundError` | Check `/app/venv/` exists | Re-run `pip install -r requirements.txt` |
| Server not starting | `journalctl -u fl-server` | Check `.env` file and JWT secret |
| ARM compatibility issue | `uname -m` should show `aarch64` | Ensure using `torch` ARM build |

---

## 3. End-to-End FL Validation

### 3.1 Server Health Dashboard

```bash
# From your local machine, check server health
curl http://<SERVER_IP>:8765/health

# Expected response when clients are connected:
# {
#   "status": "ok",
#   "tasks": {
#     "femnist": {"round": 5, "buffer_size": 1},
#     "shakespeare": {"round": 0, "buffer_size": 0}
#   },
#   "connected_clients": 3
# }
```

### 3.2 Telemetry Stream Validation

```bash
# Stream real-time events from the server
curl -N http://<SERVER_IP>:8765/telemetry/stream

# You should see events like:
# data: {"event": "client_joined", "data": {"client_id": "node_0", "task": "femnist"}}
# data: {"event": "update_received", "data": {"client_id": "node_1", "round_num": 3}}
# data: {"event": "round_complete", "data": {"task": "femnist", "round": 4, "loss": 2.145}}
```

### 3.3 Validation Checklist

- [ ] **All 3 nodes connected:** `curl /health` shows `connected_clients: 3`
- [ ] **Training progressing:** Round number increasing (`curl /health` repeatedly)
- [ ] **Loss decreasing:** Telemetry `round_complete` events show decreasing loss
- [ ] **Non-IID effect visible:** Different nodes report different loss values (expected since each has different data distribution)
- [ ] **Node resilience:** Kill one client (`systemctl stop fl-client` on a node), verify other 2 continue training. Restart it and verify it reconnects.
- [ ] **Buffer aggregation:** Server logs show updates being buffered and aggregated periodically

### 3.4 Node Resilience Test

```bash
# SSH into client node 1
ssh ubuntu@<CLIENT_1_IP>
sudo systemctl stop fl-client

# Wait 60 seconds, check server health
curl http://<SERVER_IP>:8765/health
# connected_clients should be 2 (node 1 timed out)

# Restart client node 1
sudo systemctl start fl-client

# Check health again after 30 seconds
curl http://<SERVER_IP>:8765/health
# connected_clients should be 3 again
# Client 1 logs should show reconnection and resumed training
```

### 3.5 Performance Metrics

After running for 10-20 minutes with 3 nodes:

| Metric | Expected Range | How to Check |
|--------|---------------|--------------|
| Training rounds | 10-50+ | `curl /health` |
| Avg loss | Decreasing from ~2.3 to <1.0 | Telemetry stream |
| Aggregation time | <2 seconds | Server logs |
| Client reconnect time | <30 seconds | Stop/start a node |
| Memory usage per node | <2GB | `htop` on each VM |

---

## 4. Teardown

```bash
# When done testing, destroy all resources
cd terraform
terraform destroy

# Verify in OCI Console that all resources are removed
# (VCN, instances, bucket, etc.)
```
