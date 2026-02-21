# aggregation/__init__.py
from aggregation.aggregator import Aggregator, AggregationResult, get_aggregator, list_available_methods
from aggregation.fedavg import fedavg
from aggregation.coordinate_median import coordinate_median
from aggregation.trimmed_mean import trimmed_mean
from aggregation.reputation import reputation_aggregated
