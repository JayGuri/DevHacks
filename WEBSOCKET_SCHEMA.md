# WebSocket Communication Schema

FL training loop message protocol between clients and the aggregation server.

---

## 📤 Client → Server

### `weight_update`
Sent after each local training round with computed weight gradients.

```json
{
  "type": "weight_update",
  "client_id": "string",
  "task": "string",
  "round_num": "int",
  "global_round_received": "int",
  "weights": "string",
  "num_samples": "int",
  "local_loss": "float",
  "privacy_budget": {
    "epsilon": "float",
    "alpha": "float"
  },
  "timestamp": "ISO 8601 string"
}
```

| Field | Description |
|---|---|
| `task` | Dataset task identifier, e.g. `"femnist"` or `"shakespeare"` |
| `round_num` | Client's local training round counter |
| `global_round_received` | Version of the global model this update was trained on (used for staleness computation) |
| `weights` | Base64-encoded msgpack of numpy weight delta arrays |
| `num_samples` | Number of local samples used in training |
| `local_loss` | Cross-entropy loss from local training |
| `privacy_budget.epsilon` | Cumulative DP privacy spend |
| `privacy_budget.alpha` | Rényi DP order parameter |

---

## 📥 Server → Client

### `global_model` — Broadcast
Sent to all connected clients after a successful aggregation round.

```json
{
  "type": "global_model",
  "task": "string",
  "round_num": "int",
  "weights": "string",
  "version": "string",
  "timestamp": "ISO 8601 string",
  "assigned_chunk": "int",
  "personalization_alpha": "float"
}
```

| Field | Description |
|---|---|
| `round_num` | New global round index post-aggregation |
| `weights` | Base64-encoded msgpack of aggregated global model parameters |
| `version` | UUID identifying this exact model version |
| `assigned_chunk` | *(Optional)* MongoDB chunk index assigned to this client |
| `personalization_alpha` | *(Optional)* Blending coefficient for personalized FL (`0.0` = pure global, `1.0` = pure local) |

---

### `trust_report` — Broadcast
Sent after each aggregation round. Contains per-client trust scores, staleness metadata, and rejection lists.

```json
{
  "type": "trust_report",
  "task": "string",
  "round": "int",
  "trust_scores": {
    "client_id_1": 0.85,
    "client_id_2": 0.0
  },
  "staleness_values": {
    "client_id_1": 0
  },
  "staleness_weights": {
    "client_id_1": 1.0
  },
  "rejected_clients": ["client_id_2"],
  "gatekeeper_rejected": ["client_id_3"]
}
```

| Field | Description |
|---|---|
| `trust_scores` | EMA-smoothed trust score per client in `[0.0, 1.0]`. Drops to `0.0` for suspicious clients |
| `staleness_values` | Rounds behind the current global model. `0` = fresh |
| `staleness_weights` | Staleness decay multiplier applied during aggregation weighting |
| `rejected_clients` | Clients dropped by Layer 2 — Statistical Outlier Filter (SABD / Multi-Krum) |
| `gatekeeper_rejected` | Clients dropped by Layer 1 — L2 Norm Gatekeeper |

---

### `rejected` — Direct Message
Sent immediately and only to the offending client when its update is dropped by the Layer 1 Gatekeeper.

```json
{
  "type": "rejected",
  "client_id": "string",
  "task": "string",
  "reason": "l2_norm_exceeded",
  "round_num": "int",
  "norm": "float",
  "threshold": "float"
}
```

| Field | Description |
|---|---|
| `reason` | Rejection cause. Currently: `"l2_norm_exceeded"` |
| `norm` | Actual L2 norm of the offending update |
| `threshold` | Server's configured L2 norm limit |

---

## Defense Pipeline

Updates pass through two layers before aggregation:

```
weight_update received
        │
        ▼
┌───────────────────┐
│  Layer 1          │  L2 Norm Gatekeeper
│  Gatekeeper       │  norm > threshold → send `rejected`, emit gatekeeper_rejected
└────────┬──────────┘
         │ passed
         ▼
┌───────────────────┐
│  Layer 2          │  Statistical Outlier Filter (SABD / Multi-Krum)
│  Outlier Filter   │  outlier detected → trust_score = 0.0, emit rejected_clients
└────────┬──────────┘
         │ passed
         ▼
┌───────────────────┐
│  Aggregation      │  trimmed_mean / coordinate_median / fedavg / krum
│  Strategy         │
└────────┬──────────┘
         │
         ▼
  Broadcast `global_model` + `trust_report`
```

---

## Client Limit

Maximum **10 concurrent clients**, one per MongoDB data chunk. Connections beyond this are rejected at the WebSocket handshake stage.
