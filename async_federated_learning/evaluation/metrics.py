# evaluation/metrics.py — Prometheus metrics, SSE broadcaster + ExperimentTracker
"""
evaluation/metrics.py
=====================
Contains:
- Prometheus metrics for live monitoring (akshat).
- SSE broadcaster for real-time dashboard event streaming (akshat).
- ExperimentTracker: matplotlib plotting and summary reports (ayush).
- compute_accuracy(): simple accuracy from logits/labels.
- compute_asr(): Attack Success Rate metric.
- compute_defense_rate(): defense rate metric.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from prometheus_client import Gauge, Counter, Histogram

logger = logging.getLogger("fedbuff.evaluation.metrics")

# ---------------------------------------------------------------------------
# Prometheus metrics (from akshat — live server monitoring)
# ---------------------------------------------------------------------------

fl_connected_clients = Gauge(
    "fl_connected_clients", "Total connected clients"
)
fl_global_round = Gauge(
    "fl_global_round", "Current FL round", ["task"]
)
fl_updates_received_total = Counter(
    "fl_updates_received_total", "Updates received", ["client_id", "task"]
)
fl_updates_rejected_total = Counter(
    "fl_updates_rejected_total", "Updates rejected", ["client_id", "task", "reason"]
)
fl_global_loss = Gauge(
    "fl_global_loss", "Current global loss", ["task"]
)
fl_buffer_size = Gauge(
    "fl_buffer_size", "Buffer occupancy", ["task"]
)
fl_aggregation_duration = Histogram(
    "fl_aggregation_duration_seconds", "Aggregation time", ["task"]
)
fl_client_trust_score = Gauge(
    "fl_client_trust_score", "Client trust score", ["client_id", "task"]
)


# ---------------------------------------------------------------------------
# SSE broadcaster (from akshat — real-time dashboard)
# ---------------------------------------------------------------------------

sse_subscribers: list = []


async def subscribe_sse() -> asyncio.Queue:
    """Create and register a new SSE subscriber queue."""
    q = asyncio.Queue()
    sse_subscribers.append(q)
    logger.debug("SSE subscriber added. Total subscribers: %d", len(sse_subscribers))
    return q


async def unsubscribe_sse(q: asyncio.Queue) -> None:
    """Remove an SSE subscriber queue."""
    if q in sse_subscribers:
        sse_subscribers.remove(q)
        logger.debug("SSE subscriber removed. Total subscribers: %d", len(sse_subscribers))


async def emit_event(event_type: str, data: dict) -> None:
    """Serialises the event and distributes to SSE subscribers + updates Prometheus."""
    event = {
        "event": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    event_json = json.dumps(event, default=str)

    for q in list(sse_subscribers):
        try:
            q.put_nowait(event_json)
        except asyncio.QueueFull:
            logger.warning("SSE subscriber queue full, dropping event")
        except Exception as e:
            logger.warning("Failed to put event to SSE subscriber: %s", e)

    # Update Prometheus metrics
    try:
        if event_type == "update_received":
            client_id = data.get("client_id", "unknown")
            task = data.get("task", "unknown")
            fl_updates_received_total.labels(client_id=client_id, task=task).inc()

        elif event_type == "update_rejected":
            client_id = data.get("client_id", "unknown")
            task = data.get("task", "unknown")
            reason = data.get("reason", "unknown")
            fl_updates_rejected_total.labels(
                client_id=client_id, task=task, reason=reason
            ).inc()

        elif event_type == "round_complete":
            task = data.get("task", "unknown")
            round_num = data.get("round", 0)
            loss = data.get("loss", 0.0)
            fl_global_round.labels(task=task).set(round_num)
            fl_global_loss.labels(task=task).set(loss)

        elif event_type == "client_joined":
            fl_connected_clients.inc()

        elif event_type == "client_left":
            fl_connected_clients.dec()

        elif event_type == "trust_score":
            client_id = data.get("client_id", "unknown")
            task = data.get("task", "unknown")
            score = data.get("score", 0.0)
            fl_client_trust_score.labels(client_id=client_id, task=task).set(score)

        elif event_type == "buffer_size":
            task = data.get("task", "unknown")
            size = data.get("size", 0)
            fl_buffer_size.labels(task=task).set(size)

    except Exception as e:
        logger.warning("Failed to update Prometheus metric for %s: %s", event_type, e)


# ---------------------------------------------------------------------------
# Simple evaluation utilities
# ---------------------------------------------------------------------------

def compute_accuracy(logits: np.ndarray, labels: np.ndarray) -> float:
    """Returns top-1 accuracy as a float in [0.0, 1.0]."""
    predictions = np.argmax(logits, axis=-1)
    return float(np.mean(predictions == labels))


def compute_asr(poisoned_predictions: np.ndarray, target_label: int) -> float:
    """Attack Success Rate: fraction of poisoned predictions matching target label."""
    if len(poisoned_predictions) == 0:
        return 0.0
    return float(np.mean(poisoned_predictions == target_label))


def compute_defense_rate(total_byzantine: int, detected_byzantine: int) -> float:
    """Defense rate: fraction of Byzantine clients successfully detected."""
    if total_byzantine == 0:
        return 1.0
    return detected_byzantine / total_byzantine


# ---------------------------------------------------------------------------
# ExperimentTracker (from ayush — matplotlib plotting + reports)
# ---------------------------------------------------------------------------

# Lazy import to avoid forcing matplotlib on server-only deployments
_matplotlib_available = False


def _ensure_matplotlib():
    """Import matplotlib on demand. Does NOT block if unavailable."""
    global _matplotlib_available
    if _matplotlib_available:
        return True
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        try:
            plt.style.use('seaborn-v0_8-whitegrid')
        except OSError:
            plt.style.use('ggplot')
        _matplotlib_available = True
        return True
    except ImportError:
        logger.warning("matplotlib not available — ExperimentTracker plots disabled.")
        return False


# Colour palette: Blue, Red, Green, Orange, Purple
COLORS = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0']
FIGSIZE = (12, 6)


class ExperimentTracker:
    """Generates paper-quality plots and summary reports for FL experiments.

    Parameters
    ----------
    config : Settings or Config — experiment configuration with output_dir attribute.
    """

    def __init__(self, config):
        self.config = config
        output_dir = getattr(config, 'RESULTS_DIR', getattr(config, 'output_dir', './results'))
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_convergence_comparison(self, results_dict: dict,
                                     filename: str = 'convergence.png') -> None:
        """Plot accuracy curves for multiple experiments."""
        if not _ensure_matplotlib():
            return
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=FIGSIZE)
        for idx, (name, data) in enumerate(results_dict.items()):
            color = COLORS[idx % len(COLORS)]
            ax.plot(data['rounds'], data['accuracy'], label=name,
                    color=color, linewidth=2, marker='o', markersize=4)

        ax.axhline(y=0.1, color='gray', linestyle='--', linewidth=1.5, label='Random Chance')
        ax.set_title('Convergence: FedAvg vs Robust Aggregation Under Attack',
                      fontsize=14, fontweight='bold')
        ax.set_xlabel('Global Round')
        ax.set_ylabel('Test Accuracy')
        ax.set_ylim(0, 1.05)
        ax.legend(loc='lower right')
        plt.tight_layout()

        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('Convergence plot saved to %s', save_path)

    def plot_sabd_proof(self, raw_divs_by_group: dict,
                        corrected_divs_by_group: dict,
                        filename: str = 'sabd_proof.png') -> None:
        """Side-by-side violin plots showing SABD's divergence separation."""
        if not _ensure_matplotlib():
            return
        import matplotlib.pyplot as plt

        groups = list(raw_divs_by_group.keys())
        group_colors = {'honest_slow': COLORS[2], 'byzantine': COLORS[1]}

        fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

        def _draw_violin(ax, data_by_group, title):
            data_lists = [data_by_group.get(g, [0.0]) or [0.0] for g in groups]
            parts = ax.violinplot(data_lists, positions=range(len(groups)),
                                  showmeans=True, showmedians=False)
            for i, pc in enumerate(parts['bodies']):
                g = groups[i]
                pc.set_facecolor(group_colors.get(g, COLORS[i % len(COLORS)]))
                pc.set_alpha(0.75)
            ax.set_xticks(range(len(groups)))
            ax.set_xticklabels([g.replace('_', '\n') for g in groups])
            ax.set_title(title, fontsize=12)

        _draw_violin(ax_left, raw_divs_by_group, 'Before SABD (Raw Divergence)')
        _draw_violin(ax_right, corrected_divs_by_group, 'After SABD Correction')
        ax_left.set_ylabel('Cosine Divergence')

        fig.suptitle('SABD Proof: Divergence Distribution Separation',
                      fontsize=14, fontweight='bold')
        plt.tight_layout(rect=[0, 0.04, 1, 1])
        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('SABD proof plot saved to %s', save_path)

    def plot_staleness_distribution(self, all_staleness: list,
                                     filename: str = 'staleness.png') -> None:
        """Histogram of staleness values with mean and max annotations."""
        if not _ensure_matplotlib() or not all_staleness:
            return
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=FIGSIZE)
        ax.hist(all_staleness, bins=max(10, len(set(all_staleness))),
                color=COLORS[0], edgecolor='white', alpha=0.85)

        mean_s = float(np.mean(all_staleness))
        max_s = float(np.max(all_staleness))
        ax.axvline(mean_s, color=COLORS[1], linestyle='--', linewidth=2,
                    label=f'Mean = {mean_s:.2f}')
        ax.axvline(max_s, color=COLORS[4], linestyle=':', linewidth=2,
                    label=f'Max = {max_s:.0f}')

        ax.set_title('Distribution of Update Staleness in Async FL',
                      fontsize=14, fontweight='bold')
        ax.set_xlabel('Staleness (rounds behind)')
        ax.set_ylabel('Frequency')
        ax.legend()
        plt.tight_layout()

        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('Staleness distribution plot saved to %s', save_path)

    def plot_privacy_accuracy_tradeoff(self, noise_levels: list, accuracies: list,
                                        filename: str = 'privacy_tradeoff.png') -> None:
        """Line plot of accuracy vs. DP noise multiplier."""
        if not _ensure_matplotlib():
            return
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=FIGSIZE)
        ax.plot(noise_levels, accuracies, color=COLORS[0], linewidth=2,
                marker='o', markersize=8)

        for x, y in zip(noise_levels, accuracies):
            ax.annotate(f'{y:.3f}', (x, y), textcoords='offset points',
                        xytext=(0, 10), ha='center', fontsize=9)

        ax.set_title('Privacy-Utility Tradeoff', fontsize=14, fontweight='bold')
        ax.set_xlabel('DP Noise Multiplier')
        ax.set_ylabel('Test Accuracy')
        plt.tight_layout()

        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('Privacy-accuracy tradeoff plot saved to %s', save_path)

    def generate_summary_report(self, results_dict: dict,
                                 filename: str = 'summary_report.md') -> None:
        """Write a Markdown report with config table and results table."""
        lines = [
            '# Federated Learning Experiment Summary\n',
            '## Configuration\n',
            '| Parameter | Value |',
            '|---|---|',
        ]

        # Support both Settings (dict()) and Config (to_dict())
        config_dict = {}
        if hasattr(self.config, 'to_dict'):
            config_dict = self.config.to_dict()
        elif hasattr(self.config, 'model_dump'):
            config_dict = self.config.model_dump()
        else:
            config_dict = vars(self.config)

        for k, v in config_dict.items():
            lines.append(f'| `{k}` | {v} |')

        lines += [
            '\n## Results\n',
            '| Experiment | Final Accuracy | Best Accuracy | Eval Rounds |',
            '|---|---|---|---|',
        ]
        for name, data in results_dict.items():
            accs = data.get('accuracy', [])
            if accs:
                final = f'{accs[-1]:.4f}'
                best = f'{max(accs):.4f}'
                rounds = str(len(accs))
            else:
                final, best, rounds = 'N/A', 'N/A', '0'
            lines.append(f'| {name} | {final} | {best} | {rounds} |')

        lines += [
            '\n## Observations\n',
            '- Byzantine-robust aggregation (Trimmed Mean, Coordinate Median) '
            'maintains higher accuracy under attack vs. FedAvg.',
            '- SABD correction reduces false positives on honest-but-stale clients.',
            '- Differential privacy adds calibrated noise; slight accuracy drop '
            'is the privacy-utility trade-off.',
        ]

        report_path = self.output_dir / filename
        report_path.write_text('\n'.join(lines), encoding='utf-8')
        logger.info('Summary report saved to %s', report_path)

    def save_round_metrics_csv(self, results_dict: dict,
                                filename: str = 'metrics.csv') -> None:
        """Export per-round accuracy for all experiments as a tidy CSV."""
        try:
            import pandas as pd
        except ImportError:
            logger.warning("pandas not available — CSV export skipped.")
            return

        rows = []
        for name, data in results_dict.items():
            rounds = data.get('rounds', [])
            accuracies = data.get('accuracy', [])
            for r, a in zip(rounds, accuracies):
                rows.append({'experiment_name': name, 'round': r, 'accuracy': a})

        df = pd.DataFrame(rows, columns=['experiment_name', 'round', 'accuracy'])
        csv_path = self.output_dir / filename
        df.to_csv(csv_path, index=False)
        logger.info('Round metrics CSV saved to %s', csv_path)
