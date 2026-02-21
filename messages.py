# messages.py — WebSocket message protocol (Pydantic models)
from pydantic import BaseModel
from typing import Literal, Optional


class WeightUpdateMessage(BaseModel):
    type: Literal["weight_update"]
    client_id: str
    task: str
    round_num: int
    global_round_received: int
    weights: str  # base64-encoded msgpack of weight diffs
    num_samples: int
    local_loss: float
    privacy_budget: dict
    timestamp: str


class PingMessage(BaseModel):
    type: Literal["ping"]
    client_id: str


class GlobalModelMessage(BaseModel):
    type: Literal["global_model"]
    task: str
    round_num: int
    weights: str
    version: str
    timestamp: str


class RejectedMessage(BaseModel):
    type: Literal["rejected"]
    client_id: str
    task: str
    reason: str  # "l2_norm_exceeded" | "anomaly_detected" | "staleness" | "auth_failed"
    round_num: int


class StatusBroadcast(BaseModel):
    type: Literal["status"]
    event: str  # "round_complete" | "client_joined" | "client_left" | "client_rejected"
    task: str
    data: dict
    timestamp: str
