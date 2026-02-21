"""
aggregation/aggregator.py
=========================
Unified aggregation interface routing to the selected strategy.

Will contain:
- Aggregator class: thin router that accepts an AggregationStrategy enum value
  from config and delegates aggregate() calls to the appropriate implementation
  (FedAvg, TrimmedMean, CoordinateMedian), optionally re-weighting by
  ReputationSystem scores before aggregation.
- aggregate(updates, reputations=None) → state_dict method.
- Logging of which strategy was used and summary stats per round.
"""
