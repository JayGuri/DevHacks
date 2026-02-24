# backend/join_requests/schemas.py — Join Request schemas
from pydantic import BaseModel


class JoinRequestCreate(BaseModel):
    projectId: str
    message: str = ""
