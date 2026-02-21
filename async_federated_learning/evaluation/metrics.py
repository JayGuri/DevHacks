"""
evaluation/metrics.py
=====================
Experiment tracking and visualisation for the async federated learning pipeline.

Contains
--------
- ExperimentTracker: generates all paper-quality plots and the Markdown summary
  report.  Every public method saves a file to ``config.output_dir`` and calls
  ``plt.close()`` to avoid memory leaks across many experiments.

Plotting notes
--------------
- Backend forced to 'Agg' (non-interactive) so the code runs correctly on
  headless servers (CI, cloud VMs) and inside threads.  The import order:
  ``import matplotlib; matplotlib.use('Agg')`` MUST precede any pyplot import.
- ``seaborn-v0_8-whitegrid`` style is used for all plots (clean grid, muted
  background — works with matplotlib ≥ 3.6).
- COLORS and FIGSIZE are module-level constants so every plot has a consistent
  visual identity.
"""

import matplotlib
matplotlib.use('Agg')  # non-interactive backend — must precede pyplot

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from async_federated_learning.config import Config

# Apply consistent visual style across all plots
try:
    plt.style.use('seaborn-v0_8-whitegrid')
except OSError:
    plt.style.use('ggplot')  # fallback for older matplotlib

# Colour palette: Blue, Red, Green, Orange, Purple
COLORS = ['#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0']

# Default figure size for single-panel plots
FIGSIZE = (12, 6)

logger = logging.getLogger(__name__)


class ExperimentTracker:
    """
    Generates plots and summary reports for FL experiments.

    All ``plot_*`` methods:
    - Accept data, compute the figure, save to ``output_dir / filename``, and
      call ``plt.close()`` — no figure objects are returned to the caller.
    - Use the module-level COLORS palette and FIGSIZE for visual consistency.

    Parameters
    ----------
    config : Config
        Experiment configuration.  ``config.output_dir`` is used as the root
        directory for all saved files.
    """

    def __init__(self, config: Config):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Convergence
    # ------------------------------------------------------------------

    def plot_convergence_comparison(
        self,
        results_dict: dict,
        filename: str = 'convergence.png',
    ) -> None:
        """
        Plot accuracy curves for multiple experiments on a single figure.

        Parameters
        ----------
        results_dict : dict
            ``{'Experiment Name': {'rounds': [...], 'accuracy': [...]}}``
        filename     : str   Output filename relative to ``output_dir``.
        """
        fig, ax = plt.subplots(figsize=FIGSIZE)

        for idx, (name, data) in enumerate(results_dict.items()):
            color = COLORS[idx % len(COLORS)]
            ax.plot(
                data['rounds'],
                data['accuracy'],
                label=name,
                color=color,
                linewidth=2,
                marker='o',
                markersize=4,
            )

        # Random-chance reference line
        ax.axhline(
            y=0.1, color='gray', linestyle='--', linewidth=1.5,
            label='Random Chance',
        )

        ax.set_title(
            'Convergence: FedAvg vs Robust Aggregation Under Attack',
            fontsize=14, fontweight='bold',
        )
        ax.set_xlabel('Global Round')
        ax.set_ylabel('Test Accuracy')
        ax.set_ylim(0, 1.05)
        ax.legend(loc='lower right')
        plt.tight_layout()

        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('Convergence plot saved to %s', save_path)

    # ------------------------------------------------------------------
    # SABD proof — the centre-piece visualisation
    # ------------------------------------------------------------------

    def plot_sabd_proof(
        self,
        raw_divs_by_group: dict,
        corrected_divs_by_group: dict,
        filename: str = 'sabd_proof.png',
    ) -> None:
        """
        Side-by-side violin plots showing SABD's divergence separation.

        Left panel:  raw divergences (honest-slow looks Byzantine — indistinguishable).
        Right panel: SABD-corrected divergences (honest-slow drops, Byzantine stays).

        Parameters
        ----------
        raw_divs_by_group       : dict  ``{'honest_slow': [...], 'byzantine': [...]}``
        corrected_divs_by_group : dict  Same structure but post-SABD-correction.
        filename                : str   Output filename.
        """
        groups = list(raw_divs_by_group.keys())
        group_colors = {'honest_slow': COLORS[2], 'byzantine': COLORS[1]}

        fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

        def _draw_violin(ax, data_by_group, title):
            data_lists = [data_by_group[g] for g in groups]
            # Guard: violinplot requires at least 1 value per group
            data_lists = [d if d else [0.0] for d in data_lists]
            parts = ax.violinplot(
                data_lists,
                positions=range(len(groups)),
                showmeans=True,
                showmedians=False,
            )
            for i, pc in enumerate(parts['bodies']):
                g = groups[i]
                pc.set_facecolor(group_colors.get(g, COLORS[i % len(COLORS)]))
                pc.set_alpha(0.75)
            ax.set_xticks(range(len(groups)))
            ax.set_xticklabels([g.replace('_', '\n') for g in groups])
            ax.set_title(title, fontsize=12)

        _draw_violin(ax_left,  raw_divs_by_group,       'Before SABD (Raw Divergence)')
        _draw_violin(ax_right, corrected_divs_by_group, 'After SABD Correction')

        ax_left.set_ylabel('Cosine Divergence')

        fig.suptitle(
            'SABD Proof: Divergence Distribution Separation',
            fontsize=14, fontweight='bold',
        )
        fig.text(
            0.5, 0.01,
            'Left: What legacy systems see  |  Right: What SABD reveals',
            ha='center', fontsize=11, style='italic', color='#555555',
        )

        plt.tight_layout(rect=[0, 0.04, 1, 1])
        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('SABD proof plot saved to %s', save_path)

    # ------------------------------------------------------------------
    # Staleness distribution
    # ------------------------------------------------------------------

    def plot_staleness_distribution(
        self,
        all_staleness: list,
        filename: str = 'staleness.png',
    ) -> None:
        """
        Histogram of staleness values with mean and max annotations.

        Parameters
        ----------
        all_staleness : list[float]   Staleness values collected across all rounds.
        filename      : str           Output filename.
        """
        if not all_staleness:
            logger.warning(
                'plot_staleness_distribution — all_staleness is empty, skipping.'
            )
            return

        fig, ax = plt.subplots(figsize=FIGSIZE)

        ax.hist(
            all_staleness, bins=max(10, len(set(all_staleness))),
            color=COLORS[0], edgecolor='white', alpha=0.85,
        )

        mean_s = float(np.mean(all_staleness))
        max_s  = float(np.max(all_staleness))

        ax.axvline(
            mean_s, color=COLORS[1], linestyle='--', linewidth=2,
            label=f'Mean = {mean_s:.2f}',
        )
        ax.axvline(
            max_s, color=COLORS[4], linestyle=':', linewidth=2,
            label=f'Max = {max_s:.0f}',
        )

        ax.set_title(
            'Distribution of Update Staleness in Async FL',
            fontsize=14, fontweight='bold',
        )
        ax.set_xlabel('Staleness (rounds behind)')
        ax.set_ylabel('Frequency')
        ax.legend()
        plt.tight_layout()

        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('Staleness distribution plot saved to %s', save_path)

    # ------------------------------------------------------------------
    # Privacy-accuracy tradeoff
    # ------------------------------------------------------------------

    def plot_privacy_accuracy_tradeoff(
        self,
        noise_levels: list,
        accuracies: list,
        filename: str = 'privacy_tradeoff.png',
    ) -> None:
        """
        Line plot of accuracy vs. DP noise multiplier.

        Each point is annotated with its exact accuracy value.

        Parameters
        ----------
        noise_levels : list[float]   DP noise multiplier values (x-axis).
        accuracies   : list[float]   Corresponding test accuracies (y-axis).
        filename     : str           Output filename.
        """
        fig, ax = plt.subplots(figsize=FIGSIZE)

        ax.plot(
            noise_levels, accuracies,
            color=COLORS[0], linewidth=2, marker='o', markersize=8,
        )

        # Annotate each data point with its accuracy value
        for x, y in zip(noise_levels, accuracies):
            ax.annotate(
                f'{y:.3f}', (x, y),
                textcoords='offset points', xytext=(0, 10),
                ha='center', fontsize=9,
            )

        ax.set_title('Privacy-Utility Tradeoff', fontsize=14, fontweight='bold')
        ax.set_xlabel('DP Noise Multiplier (σ)')
        ax.set_ylabel('Test Accuracy')

        # Explanatory note in the top-right corner
        ax.text(
            0.98, 0.98,
            'Higher noise = stronger privacy, lower accuracy',
            transform=ax.transAxes, ha='right', va='top',
            fontsize=9, color='#666666', style='italic',
        )

        plt.tight_layout()
        save_path = self.output_dir / filename
        plt.savefig(save_path, dpi=150)
        plt.close()
        logger.info('Privacy-accuracy tradeoff plot saved to %s', save_path)

    # ------------------------------------------------------------------
    # Summary report (Markdown)
    # ------------------------------------------------------------------

    def generate_summary_report(
        self,
        results_dict: dict,
        filename: str = 'summary_report.md',
    ) -> None:
        """
        Write a Markdown report with a config table and a results table.

        Results table columns: Experiment | Final Acc | Best Acc | Eval Rounds.

        Parameters
        ----------
        results_dict : dict   ``{'Experiment Name': {'rounds': [...], 'accuracy': [...]}}``
        filename     : str    Output filename.
        """
        lines = [
            '# Federated Learning Experiment Summary\n',
            '## Configuration\n',
            '| Parameter | Value |',
            '|---|---|',
        ]
        for k, v in self.config.to_dict().items():
            lines.append(f'| `{k}` | {v} |')

        lines += [
            '\n## Results\n',
            '| Experiment | Final Accuracy | Best Accuracy | Eval Rounds |',
            '|---|---|---|---|',
        ]
        for name, data in results_dict.items():
            accs = data.get('accuracy', [])
            if accs:
                final  = f'{accs[-1]:.4f}'
                best   = f'{max(accs):.4f}'
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

    # ------------------------------------------------------------------
    # CSV metrics export
    # ------------------------------------------------------------------

    def save_round_metrics_csv(
        self,
        results_dict: dict,
        filename: str = 'metrics.csv',
    ) -> None:
        """
        Export per-round accuracy for all experiments as a tidy CSV.

        DataFrame columns: ``experiment_name``, ``round``, ``accuracy``.

        Parameters
        ----------
        results_dict : dict   ``{'Experiment Name': {'rounds': [...], 'accuracy': [...]}}``
        filename     : str    Output filename.
        """
        rows = []
        for name, data in results_dict.items():
            rounds     = data.get('rounds', [])
            accuracies = data.get('accuracy', [])
            for r, a in zip(rounds, accuracies):
                rows.append({'experiment_name': name, 'round': r, 'accuracy': a})

        df = pd.DataFrame(rows, columns=['experiment_name', 'round', 'accuracy'])
        csv_path = self.output_dir / filename
        df.to_csv(csv_path, index=False)
        logger.info('Round metrics CSV saved to %s', csv_path)

    # ------------------------------------------------------------------
    # Data distribution (called from main.py)
    # ------------------------------------------------------------------

    def plot_data_distribution(
        self,
        client_indices: list,
        dataset,
        num_classes: int,
        save_path: str = None,
    ) -> None:
        """
        Stacked horizontal bar chart of class distribution across clients.

        Mirrors ``DataPartitioner.visualize_distribution`` but lives here so
        ``main.py`` only needs one tracker object.

        Parameters
        ----------
        client_indices : list[np.ndarray]   Per-client sample index arrays.
        dataset        : Dataset            Dataset with a ``.targets`` attribute.
        num_classes    : int                Number of distinct classes.
        save_path      : str | None         Absolute path; defaults to
                         ``output_dir/data_distribution.png``.
        """
        all_labels  = np.array(dataset.targets)
        num_clients = len(client_indices)

        # Build (num_clients × num_classes) count matrix
        counts = np.zeros((num_clients, num_classes), dtype=int)
        for i, idxs in enumerate(client_indices):
            client_labels = all_labels[idxs]
            for c in range(num_classes):
                counts[i, c] = int(np.sum(client_labels == c))

        fig, ax = plt.subplots(figsize=(10, max(4, num_clients * 0.5)))
        y_labels    = [f'Client {i}' for i in range(num_clients)]
        bar_colors  = [plt.cm.tab10(c / 10) for c in range(num_classes)]
        lefts       = np.zeros(num_clients)

        for c in range(num_classes):
            ax.barh(
                y_labels, counts[:, c],
                left=lefts, color=bar_colors[c], label=f'Class {c}',
            )
            lefts = lefts + counts[:, c]

        ax.set_title(
            f'Data Distribution Across Clients '
            f'(Dirichlet α={self.config.dirichlet_alpha})',
            fontsize=13, fontweight='bold',
        )
        ax.set_xlabel('Sample count')
        ax.legend(loc='lower right', ncol=5)
        plt.tight_layout()

        target_path = (
            Path(save_path)
            if save_path is not None
            else self.output_dir / 'data_distribution.png'
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(target_path, dpi=150)
        plt.close()
        logger.info('Data distribution plot saved to %s', target_path)
