# scripts/create_users.py — Generate users.json, env files, and demo tokens
import os
import sys
import json
import secrets
import argparse
from datetime import datetime, timedelta, timezone

import jwt


# User definitions
USERS = {
    "client-alice-img": {
        "display_name": "Alice_Image",
        "role": "legitimate_client",
        "task": "femnist",
        "participant": "Alice",
        "pc": "PC-2",
        "data_partition": 0,
    },
    "client-alice-txt": {
        "display_name": "Alice_Text",
        "role": "legitimate_client",
        "task": "shakespeare",
        "participant": "Alice",
        "pc": "PC-2",
        "data_partition": 0,
    },
    "client-bob-img": {
        "display_name": "Bob_Image",
        "role": "legitimate_client",
        "task": "femnist",
        "participant": "Bob",
        "pc": "PC-3",
        "data_partition": 1,
    },
    "client-bob-txt": {
        "display_name": "Bob_Text",
        "role": "legitimate_client",
        "task": "shakespeare",
        "participant": "Bob",
        "pc": "PC-3",
        "data_partition": 1,
    },
    "client-mallory-img": {
        "display_name": "Mallory_Image",
        "role": "malicious_client",
        "task": "femnist",
        "participant": "Mallory",
        "pc": "PC-4",
        "data_partition": 2,
    },
    "client-mallory-txt": {
        "display_name": "Mallory_Text",
        "role": "malicious_client",
        "task": "shakespeare",
        "participant": "Mallory",
        "pc": "PC-4",
        "data_partition": 2,
    },
    "server-admin": {
        "display_name": "Server Admin",
        "role": "server",
        "task": None,
        "participant": "Admin",
        "pc": "PC-1",
        "data_partition": None,
    },
}

# PC to env file mapping
PC_ENV_MAP = {
    "PC-2": {"img": "pc2_img.env", "txt": "pc2_txt.env"},
    "PC-3": {"img": "pc3_img.env", "txt": "pc3_txt.env"},
    "PC-4": {"img": "pc4_img.env", "txt": "pc4_txt.env"},
}


def main():
    parser = argparse.ArgumentParser(
        description="Generate users.json, env files, and demo tokens for FedBuff"
    )
    parser.add_argument(
        "--server-ip", type=str, required=True,
        help="Server IP address (LAN IP of PC-1)"
    )
    args = parser.parse_args()

    server_ip = args.server_ip

    # Step 1: Generate JWT secret
    jwt_secret = secrets.token_hex(32)
    print(f"Generated JWT secret: {jwt_secret[:16]}...")

    # Step 2: Generate JWTs for each user
    now = datetime.now(timezone.utc)
    tokens = {}
    expiry_times = {}

    for client_id, user_info in USERS.items():
        payload = {
            "sub": client_id,
            "display_name": user_info["display_name"],
            "role": user_info["role"],
            "task": user_info["task"],
            "participant": user_info["participant"],
            "iat": now,
            "exp": now + timedelta(hours=24),
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        tokens[client_id] = token
        expiry_times[client_id] = (now + timedelta(hours=24)).isoformat()

    # Step 3: Write users.json
    users_json = {
        "jwt_secret": jwt_secret,
        "users": {},
    }
    for client_id, user_info in USERS.items():
        users_json["users"][client_id] = {
            "display_name": user_info["display_name"],
            "role": user_info["role"],
            "task": user_info["task"],
            "participant": user_info["participant"],
        }

    with open("users.json", "w") as f:
        json.dump(users_json, f, indent=2)
    print("Written: users.json")

    # Step 4: Write pc1.env (server)
    pc1_env = f"""JWT_SECRET={jwt_secret}
USERS_FILE=./users.json
BUFFER_SIZE_K=3
SERVER_HOST=0.0.0.0
SERVER_PORT=8765
MODEL_CHECKPOINT_DIR=./results/checkpoints
AGGREGATION_STRATEGY=krum
L2_NORM_THRESHOLD=500.0
"""
    with open("pc1.env", "w") as f:
        f.write(pc1_env)
    print("Written: pc1.env")

    # Step 5: Write client env files
    for client_id, user_info in USERS.items():
        if user_info["role"] == "server":
            continue

        pc = user_info["pc"]
        task = user_info["task"]
        suffix = "img" if task == "femnist" else "txt"
        env_filename = PC_ENV_MAP[pc][suffix]

        env_content = f"""CLIENT_ID={client_id}
CLIENT_ROLE={user_info["role"]}
DISPLAY_NAME={user_info["display_name"]}
PARTICIPANT={user_info["participant"]}
SERVER_URL=ws://{server_ip}:8765/ws/fl
AUTH_TOKEN={tokens[client_id]}
DATASET={task}
DATA_PARTITION={user_info["data_partition"]}
LOCAL_EPOCHS=5
LEARNING_RATE=0.01
MU=0.01
DP_MAX_GRAD_NORM=1.0
DP_NOISE_MULTIPLIER=1.1
"""
        # Add malicious client settings
        if user_info["role"] == "malicious_client":
            env_content += """ATTACK_SCALE=-5.0
ATTACK_TYPE=sign_flip_amplified
"""

        with open(env_filename, "w") as f:
            f.write(env_content)
        print(f"Written: {env_filename}")

    # Step 6: Write demo_tokens.txt
    with open("demo_tokens.txt", "w") as f:
        f.write("=" * 80 + "\n")
        f.write("FedBuff Demo Tokens\n")
        f.write(f"Generated: {now.isoformat()}\n")
        f.write(f"Server IP: {server_ip}\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"JWT_SECRET={jwt_secret}\n\n")

        for client_id, user_info in USERS.items():
            pc = user_info["pc"]
            task = user_info["task"] or "N/A"
            f.write(f"--- {client_id} ({pc}, task={task}) ---\n")
            f.write(f"TOKEN={tokens[client_id]}\n")
            f.write(f"EXPIRES={expiry_times[client_id]}\n\n")

    print("Written: demo_tokens.txt")

    # Step 7: Print summary table
    print("\n" + "=" * 95)
    print(f"{'Env File':<18} {'Client ID':<25} {'Task':<14} {'PC':<6} {'Token Expiry'}")
    print("-" * 95)

    print(f"{'pc1.env':<18} {'server-admin':<25} {'N/A':<14} {'PC-1':<6} {expiry_times['server-admin']}")

    for client_id, user_info in USERS.items():
        if user_info["role"] == "server":
            continue
        pc = user_info["pc"]
        task = user_info["task"]
        suffix = "img" if task == "femnist" else "txt"
        env_filename = PC_ENV_MAP[pc][suffix]
        print(f"{env_filename:<18} {client_id:<25} {task:<14} {pc:<6} {expiry_times[client_id]}")

    print("=" * 95)
    print(f"\nSetup complete! Copy the appropriate env files to each PC.")
    print(f"  PC-1 (Server): pc1.env, users.json")
    print(f"  PC-2 (Alice):  pc2_img.env, pc2_txt.env")
    print(f"  PC-3 (Bob):    pc3_img.env, pc3_txt.env")
    print(f"  PC-4 (Mallory): pc4_img.env, pc4_txt.env")


if __name__ == "__main__":
    main()
