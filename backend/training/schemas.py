# backend/training/schemas.py — Pydantic models for training data (RoundMetrics, Node, GanttBlock)
"""
These schemas define the exact JSON shapes the frontend expects
for real-time training data pushed via WebSocket.
"""

from typing import Optional, List
from pydantic import BaseModel


class NodeSchema(BaseModel):
    """Per-node state updated every training round."""
    nodeId: str               # e.g. "node-0"
    displayId: str            # e.g. "NODE_A1"
    userId: Optional[str] = None
    status: str               # ACTIVE | SLOW | BYZANTINE | BLOCKED
    trust: float              # 0.0–1.0
    cosineDistance: float      # 0.0–1.0
    staleness: int            # rounds since last contribution
    roundsContributed: int
    isByzantine: bool
    isSlow: bool
    isBlocked: bool


class RoundMetricsSchema(BaseModel):
    """Output of a single FL training round — drives all frontend charts."""
    round: int
    timestamp: str
    fedavgAccuracy: float     # Baseline FedAvg accuracy (%)
    trimmedAccuracy: float    # Trimmed Mean accuracy (%)
    medianAccuracy: float     # Coordinate Median accuracy (%)
    globalAccuracy: float     # Active aggregator's accuracy (%)
    globalLoss: float
    epsilonSpent: float       # Cumulative DP budget
    flaggedNodes: int
    activeNodes: int
    sabdFPR: float            # SABD false positive rate, 0.0–1.0
    sabdRecall: float         # SABD recall / detection rate, 0.0–1.0
    aggregationMethod: str


class GanttBlockSchema(BaseModel):
    """Timeline event for the Gantt chart."""
    nodeId: str
    displayId: str
    clientIdx: int
    startSec: float           # Unix timestamp in seconds
    endSec: float
    isByzantine: bool
    isSlow: bool


class TrainingConfigUpdate(BaseModel):
    """Partial config update during training."""
    aggregationMethod: Optional[str] = None
    sabdAlpha: Optional[float] = None


class GradientSubmission(BaseModel):
    """Gradient update submitted by a real contributor node.

    The contributor runs local training on their private data and sends
    the resulting gradient deltas (NOT raw data or model code).
    These pass through L2 norm clipping and zero-sum masking before
    entering the FL aggregation pipeline.
    """
    nodeId: str                       # Contributor's node identifier
    gradients: dict                   # {layer_name: [flat gradient values]}
    dataSize: Optional[int] = 100     # Number of local training samples used
    round: Optional[int] = None       # Expected round number (for staleness check)


class TrainingStatusResponse(BaseModel):
    status: str               # running | paused | completed | idle | error
    currentRound: int
    totalRounds: int
