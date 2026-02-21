# aggregation/__init__.py
from aggregation.aggregator import Aggregator, AggregationResult
from aggregation.fedavg import fedavg
from aggregation.coordinate_median import coordinate_median
from aggregation.trimmed_mean import trimmed_mean
from aggregation.reputation import (
    compute_staleness_weight,
    compute_sample_reputation_weights,
    compute_combined_weights,
)
