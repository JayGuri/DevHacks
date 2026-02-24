import asyncio
import os
import sys
import argparse
import subprocess
import urllib.request
import json
import uuid
import signal

def register_node(base_http: str, role: str, display_name: str, task: str) -> dict:
    """Registers a node with the server and returns the auth token and node ID."""
    payload = {
        "role": role,
        "display_name": display_name,
        "participant": "spawn_script",
        "task": task,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_http}/nodes/register",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Conflict, append a random suffix and try again
                payload["display_name"] = f"{display_name}-{uuid.uuid4().hex[:4]}"
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{base_http}/nodes/register",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                continue
            body = e.read().decode("utf-8")
            raise RuntimeError(f"Registration failed: {e.code}, {body}")
        except Exception as e:
            import time
            print(f"Attempt {attempt+1} failed to register {display_name}: {e}. Retrying...")
            time.sleep(2)
            continue
    raise RuntimeError(f"Failed to register node {display_name} after 5 attempts due to network errors or conflicts.")


async def main():
    parser = argparse.ArgumentParser(description="Spawn multiple configured FL clients")
    parser.add_argument("--url", type=str, required=True, help="WebSocket URL of the server (e.g., ws://localhost:8765/ws/fl or wss://<id>.ngrok-free.app/ws/fl)")
    parser.add_argument("--task", type=str, default="femnist", help="Dataset/Task (femnist or shakespeare)")
    parser.add_argument("--num-legit", type=int, default=2, help="Number of legitimate clients to spawn")
    parser.add_argument("--num-malicious", type=int, default=0, help="Number of malicious clients to spawn")
    parser.add_argument("--num-stale", type=int, default=0, help="Number of stale clients to spawn (out of the legitimate ones)")
    parser.add_argument("--stale-delay", type=float, default=10.0, help="Staleness delay in seconds for stale clients")
    args = parser.parse_args()

    # Determine HTTP URL for registration
    if args.url.startswith("wss://"):
        base_http = args.url.replace("wss://", "https://").replace("/ws/fl", "")
    elif args.url.startswith("ws://"):
        base_http = args.url.replace("ws://", "http://").replace("/ws/fl", "")
    else:
        print("Error: --url must start with ws:// or wss://")
        sys.exit(1)

    print(f"Server WebSocket URL: {args.url}")
    print(f"Server HTTP Base URL: {base_http} (for registration)")

    processes = []
    
    def cleanup(signum, frame):
        print("\nShutting down all clients...")
        for p in processes:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    total_clients = args.num_legit + args.num_malicious
    if args.num_stale > args.num_legit:
        print("Warning: --num-stale is larger than --num-legit. Only legitimate clients will be made stale.")

    client_configs = []

    # Prepare Legitimate Clients
    for i in range(args.num_legit):
        is_stale = i < args.num_stale
        display_name = f"LegitClient-{i+1}"
        staleness = args.stale_delay if is_stale else 0.0
        client_configs.append({
            "role": "legitimate_client",
            "name": display_name,
            "stale": staleness,
            "partition": i % 10 # Spread across partitions
        })

    # Prepare Malicious Clients
    for i in range(args.num_malicious):
        display_name = f"MaliciousClient-{i+1}"
        client_configs.append({
            "role": "malicious_client",
            "name": display_name,
            "stale": 0.0,
            "partition": (args.num_legit + i) % 10
        })

    client_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "client", "fl_client.py")

    print(f"Spawning {len(client_configs)} clients...")

    for config in client_configs:
        print(f"Registering {config['name']}...")
        try:
            reg_info = register_node(base_http, config["role"], config["name"], args.task)
            token = reg_info["token"]
            node_id = reg_info.get("node_id", config["name"])
        except Exception as e:
            print(f"Failed to register {config['name']}: {e}")
            continue

        env = os.environ.copy()
        env["CLIENT_ID"] = node_id
        env["CLIENT_ROLE"] = config["role"]
        env["DISPLAY_NAME"] = config["name"]
        env["PARTICIPANT"] = "SpawnScript"
        env["SERVER_URL"] = args.url
        env["AUTH_TOKEN"] = token
        env["DATASET"] = args.task
        env["NODE_INDEX"] = str(config["partition"])
        env["TOTAL_NODES"] = str(total_clients)
        env["LOCAL_EPOCHS"] = "2" # faster training for demo
        env["STALENESS_DELAY"] = str(config["stale"])
        
        if config["role"] == "malicious_client":
            env["ATTACK_SCALE"] = "-5.0"
            env["ATTACK_TYPE"] = "sign_flip_amplified"

        print(f"Starting client process for {config['name']} (PID will be independent)...")
        p = subprocess.Popen(
            [sys.executable, client_py],
            env=env,
            stdout=sys.stdout, # Stream output directly
            stderr=sys.stderr
        )
        processes.append(p)

    print(f"\nAll {len(processes)} clients spawned successfully. Press Ctrl+C to terminate.")
    
    # Wait for all processes to complete
    for p in processes:
        p.wait()

if __name__ == "__main__":
    asyncio.run(main())
