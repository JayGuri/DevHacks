import asyncio
import base64
import json
import os
import re
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone

import msgpack
import numpy as np
import websockets


def serialize_weights(weights: dict) -> str:
    """numpy arrays -> lists -> msgpack bytes -> zlib compress -> base64 string."""
    import zlib
    serializable = {}
    for key, val in weights.items():
        if hasattr(val, "tolist"):
            serializable[key] = val.tolist()
        else:
            serializable[key] = val
    packed = msgpack.packb(serializable, use_bin_type=True)
    compressed = zlib.compress(packed, level=6)
    return base64.b64encode(compressed).decode("utf-8")


def deserialize_weights(b64_str: str) -> dict:
    """Reverses serialize_weights. Auto-detects zlib compression."""
    import zlib
    raw = base64.b64decode(b64_str)
    # Auto-detect zlib compression
    try:
        raw = zlib.decompress(raw)
    except zlib.error:
        pass  # Not compressed — treat as raw msgpack
    unpacked = msgpack.unpackb(raw, raw=False)
    weights = {}
    for key, val in unpacked.items():
        k = key if isinstance(key, str) else key.decode("utf-8")
        weights[k] = np.array(val, dtype=np.float32)
    return weights


def register_node(base_http: str, role: str, display_name: str, task: str = "femnist") -> dict:
    payload = {
        "role": role,
        "display_name": display_name,
        "participant": "sim",
        "task": task,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_http}/nodes/register",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(
            f"Node registration failed: status={e.code}, display_name={display_name}, body={body}"
        ) from e


def register_node_unique(base_http: str, role: str, display_name_prefix: str, task: str = "femnist") -> dict:
    """Register a node with a unique display name to avoid 409 conflicts on reruns."""
    for _ in range(5):
        suffix = uuid.uuid4().hex[:8]
        display_name = f"{display_name_prefix}-{suffix}"
        try:
            return register_node(base_http, role, display_name, task)
        except RuntimeError as exc:
            if "status=409" not in str(exc):
                raise
    raise RuntimeError(f"Could not register unique node for prefix={display_name_prefix}")


def _load_demo_tokens_for_task(task: str) -> tuple[str, str] | tuple[None, None]:
    """Best-effort load of two demo tokens for a task from demo_tokens.txt."""
    demo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo_tokens.txt")
    if not os.path.exists(demo_path):
        return None, None

    with open(demo_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Prefer legitimate image clients for femnist simulation.
    if task == "femnist":
        labels = ["client-alice-img", "client-bob-img"]
    else:
        labels = ["client-alice-txt", "client-bob-txt"]

    tokens = []
    for label in labels:
        pattern = rf"---\s+{re.escape(label)}.*?TOKEN=([^\r\n]+)"
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            tokens.append(match.group(1).strip())

    if len(tokens) == 2:
        return tokens[0], tokens[1]
    return None, None


async def run_client(base_ws: str, token: str, task: str, delay_before_send: float, value: float):
    url = f"{base_ws}?token={token}&task={task}"
    async with websockets.connect(url, max_size=None, ping_interval=None, ping_timeout=None) as ws:
        first = json.loads(await ws.recv())
        global_round = int(first.get("round_num", 0))
        payload_weights = first.get("weights", {})
        if isinstance(payload_weights, str):
            global_weights = deserialize_weights(payload_weights)
        else:
            global_weights = {
                k: np.array(v, dtype=np.float32)
                for k, v in payload_weights.items()
            }

        if delay_before_send > 0:
            await asyncio.sleep(delay_before_send)

        weight_delta = {}
        for key, layer in global_weights.items():
            arr = np.array(layer, dtype=np.float32)
            weight_delta[key] = np.full_like(arr, value, dtype=np.float32)

        update = {
            "type": "weight_update",
            "client_id": "sim-client",
            "task": task,
            "round_num": global_round + 1,
            "global_round_received": global_round,
            "weights": serialize_weights(weight_delta),
            "num_samples": 10,
            "local_loss": 0.1,
            "privacy_budget": {"epsilon": 1.0, "delta": 1e-5},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await ws.send(json.dumps(update))

        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=20.0)
                parsed = json.loads(msg)
                if parsed.get("type") in {"trust_report", "rejected", "global_model"}:
                    print(f"[{task}] received: {parsed.get('type')}")
                    if parsed.get("type") == "trust_report":
                        print(json.dumps(parsed.get("trust_scores", {}), indent=2))
                        break
        except asyncio.TimeoutError:
            pass


async def main():
    base_http = "http://127.0.0.1:8765"
    base_ws = "ws://127.0.0.1:8765/ws/fl"
    task = "femnist"

    env_fast = os.environ.get("SIM_FAST_TOKEN", "").strip()
    env_slow = os.environ.get("SIM_SLOW_TOKEN", "").strip()

    if env_fast and env_slow:
        fast_token, slow_token = env_fast, env_slow
    else:
        try:
            fast = register_node_unique(base_http, "legitimate_client", "Sim Fast", task)
            slow = register_node_unique(base_http, "legitimate_client", "Sim Slow", task)
            fast_token, slow_token = fast["token"], slow["token"]
        except RuntimeError as exc:
            print(f"Registration fallback triggered: {exc}")
            demo_fast, demo_slow = _load_demo_tokens_for_task(task)
            if not demo_fast or not demo_slow:
                raise
            fast_token, slow_token = demo_fast, demo_slow

    await asyncio.gather(
        run_client(base_ws, fast_token, task, delay_before_send=0.0, value=0.05),
        run_client(base_ws, slow_token, task, delay_before_send=2.5, value=0.06),
    )


if __name__ == "__main__":
    asyncio.run(main())
