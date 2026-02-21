#!/usr/bin/env python3
# scripts/add_node.py — Register a new dynamic FL node with the server
# Replaces the static create_users.py workflow.
#
# Usage:
#   python add_node.py --server-url http://localhost:8765 \
#     --task femnist --role legitimate --name "Node1" [--output node1.env]
#
#   python add_node.py --server-url http://localhost:8765 \
#     --task femnist --role malicious --name "Attacker" \
#     --attack-type sign_flip_amplified --attack-scale -5.0 --output attacker.env
import os
import sys
import argparse

import requests


def make_ws_url(http_url: str) -> str:
    """Convert http(s):// URL to ws(s):// for WebSocket connections."""
    if http_url.startswith("https://"):
        return "wss://" + http_url[len("https://"):]
    if http_url.startswith("http://"):
        return "ws://" + http_url[len("http://"):]
    return http_url


def main():
    parser = argparse.ArgumentParser(
        description="Register a new FL node with the FedBuff server"
    )
    parser.add_argument(
        "--server-url", type=str, required=True,
        help="Server base URL (e.g. http://192.168.1.100:8765)"
    )
    parser.add_argument(
        "--task", type=str, required=True,
        choices=["femnist", "shakespeare"],
        help="FL task to assign to this node"
    )
    parser.add_argument(
        "--role", type=str, default="legitimate",
        choices=["legitimate", "malicious"],
        help="Node role (default: legitimate)"
    )
    parser.add_argument(
        "--name", type=str, default=None,
        help="Human-readable display name for this node (auto-generated if omitted)"
    )
    parser.add_argument(
        "--attack-type", type=str, default=None,
        choices=["sign_flip_amplified", "sign_flipping", "gradient_scaling", "random_noise", "gaussian_noise"],
        help="Attack type (only for malicious nodes)"
    )
    parser.add_argument(
        "--attack-scale", type=float, default=None,
        help="Attack scale factor (only for malicious nodes, e.g. -5.0 for sign_flip)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output env file path (default: <node_id>.env)"
    )
    parser.add_argument(
        "--local-epochs", type=int, default=5,
        help="Local training epochs per round (default: 5)"
    )
    parser.add_argument(
        "--learning-rate", type=float, default=0.01,
        help="Local learning rate (default: 0.01)"
    )
    parser.add_argument(
        "--mu", type=float, default=0.01,
        help="FedProx proximal term mu (default: 0.01)"
    )
    parser.add_argument(
        "--dp-noise-multiplier", type=float, default=1.1,
        help="DP noise multiplier (default: 1.1)"
    )
    parser.add_argument(
        "--dp-max-grad-norm", type=float, default=1.0,
        help="DP max gradient norm (default: 1.0)"
    )
    args = parser.parse_args()

    # Validate malicious config
    if args.role == "malicious" and not args.attack_type:
        parser.error("--attack-type is required for malicious nodes")

    server_url = args.server_url.rstrip("/")
    register_url = f"{server_url}/nodes/register"

    # Map role name to internal role string
    role_map = {
        "legitimate": "legitimate_client",
        "malicious": "malicious_client",
    }
    internal_role = role_map[args.role]

    # Build display name
    display_name = args.name or f"{args.task.capitalize()}-Node"

    # Build request payload
    payload = {
        "task": args.task,
        "role": internal_role,
        "display_name": display_name,
    }
    if args.attack_type:
        payload["attack_type"] = args.attack_type
    if args.attack_scale is not None:
        payload["attack_scale"] = args.attack_scale

    print(f"Registering node with {register_url} ...")
    try:
        resp = requests.post(register_url, json=payload, timeout=10)
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Could not connect to server at {server_url}")
        print("Make sure the server is running (uvicorn main:app --env-file server.env)")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"ERROR: Server returned {resp.status_code}: {resp.text}")
        sys.exit(1)

    result = resp.json()
    node_id = result["node_id"]
    node_index = result["node_index"]
    total_nodes = result["total_nodes"]
    token = result["token"]
    task = result["task"]

    print(f"  node_id:     {node_id}")
    print(f"  task:        {task}")
    print(f"  role:        {result['role']}")
    print(f"  node_index:  {node_index} / {total_nodes}")
    print(f"  data slice:  users {node_index}/{total_nodes} (non-IID partition)")

    # Determine output env file
    ws_url = make_ws_url(server_url)
    env_file = args.output or f"{node_id}.env"

    env_lines = [
        f"# FL Node env — {display_name} ({node_id})",
        f"CLIENT_ID={node_id}",
        f"CLIENT_ROLE={internal_role}",
        f"DISPLAY_NAME={display_name}",
        f"SERVER_URL={ws_url}/ws/fl",
        f"AUTH_TOKEN={token}",
        f"DATASET={task}",
        f"NODE_INDEX={node_index}",
        f"TOTAL_NODES={total_nodes}",
        f"LOCAL_EPOCHS={args.local_epochs}",
        f"LEARNING_RATE={args.learning_rate}",
        f"MU={args.mu}",
        f"DP_MAX_GRAD_NORM={args.dp_max_grad_norm}",
        f"DP_NOISE_MULTIPLIER={args.dp_noise_multiplier}",
    ]
    if args.attack_type:
        env_lines.append(f"ATTACK_TYPE={args.attack_type}")
    if args.attack_scale is not None:
        env_lines.append(f"ATTACK_SCALE={args.attack_scale}")

    with open(env_file, "w") as f:
        f.write("\n".join(env_lines) + "\n")

    print(f"\nWritten: {env_file}")
    print(f"\nStart client:  python client/fl_client.py --env-file {env_file}")


if __name__ == "__main__":
    main()
