"""
main.py
=======
Entry point for the async federated learning framework.

Will contain:
- Argument parsing via argparse.
- Top-level orchestration: instantiate server, clients, and kick off training.
- WandB run initialisation and final results logging.
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    pass
