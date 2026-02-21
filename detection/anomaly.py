# detection/anomaly.py — Gatekeeper: L2 norm pre-filter (first defense layer)
import numpy as np
import logging

logger = logging.getLogger("fedbuff.detection.anomaly")


def check_l2_norm(weight_diff: dict, threshold: float) -> tuple:
    """
    First line of defense. Runs in the WebSocket router before an update enters the buffer.
    Flattens all numpy arrays in weight_diff into a single 1D vector.
    Computes np.linalg.norm of that vector.

    Returns:
        (passed: bool, norm: float)
        passed = True  if norm <= threshold  (safe; forward to buffer)
        passed = False if norm > threshold   (flagged; reject immediately)

    Mallory's sign-flip amplified attack (scale -5.0) typically produces norms
    5x larger than honest updates, making this check highly effective as a first filter.
    """
    flat = np.concatenate([v.flatten() for v in weight_diff.values()])
    norm = float(np.linalg.norm(flat))
    passed = norm <= threshold
    if not passed:
        logger.warning(
            "L2 norm check FAILED: norm=%.4f > threshold=%.4f", norm, threshold
        )
    else:
        logger.debug(
            "L2 norm check passed: norm=%.4f <= threshold=%.4f", norm, threshold
        )
    return passed, norm
