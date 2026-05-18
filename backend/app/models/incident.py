from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


class IncidentStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class IncidentCreate(BaseModel):
    title: str
    status: IncidentStatus = IncidentStatus.ACTIVE


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[IncidentStatus] = None
    resolved_at: Optional[datetime] = None


class Incident(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    status: IncidentStatus = IncidentStatus.ACTIVE
    started_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    warning_count: int = 0

    class Config:
        from_attributes = True
