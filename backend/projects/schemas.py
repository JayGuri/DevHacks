# backend/projects/schemas.py — Pydantic schemas for Project endpoints
"""
Request/Response models for Projects API.
"""

from typing import Optional, List
from pydantic import BaseModel


class ProjectConfigSchema(BaseModel):
    numClients: int = 10
    byzantineFraction: float = 0.2
    attackType: str = "sign_flipping"
    aggregationMethod: str = "trimmed_mean"
    numRounds: int = 50
    dirichletAlpha: float = 0.5
    useDifferentialPrivacy: bool = True
    dpNoiseMultiplier: float = 0.1
    dpMaxGradNorm: float = 1.0
    sabdAlpha: float = 0.5
    localEpochs: int = 3


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    visibility: str = "public"
    numClients: int = 10
    byzantineFraction: float = 0.2
    attackType: str = "sign_flipping"
    aggregationMethod: str = "trimmed_mean"
    numRounds: int = 50
    dirichletAlpha: float = 0.5
    useDifferentialPrivacy: bool = True
    dpNoiseMultiplier: float = 0.1
    dpMaxGradNorm: float = 1.0
    sabdAlpha: float = 0.5
    localEpochs: int = 3


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    isActive: Optional[bool] = None
    visibility: Optional[str] = None
    config: Optional[ProjectConfigSchema] = None


class JoinByCodeRequest(BaseModel):
    inviteCode: Optional[str] = None


class ValidateCodeRequest(BaseModel):
    code: str


class MemberResponse(BaseModel):
    userId: str
    userName: str
    nodeId: Optional[str] = None
    role: str
    joinedAt: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    createdBy: str
    createdAt: str
    isActive: bool
    visibility: str
    inviteCode: Optional[str] = None
    maxMembers: int
    members: List[MemberResponse] = []
    config: ProjectConfigSchema
    joinRequests: list = []
