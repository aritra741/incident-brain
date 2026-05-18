from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID, uuid4
import json


class EventType(str, Enum):
    ACTION = "action"
    HYPOTHESIS = "hypothesis"
    OBSERVATION = "observation"
    OUTCOME = "outcome"
    INTERVENTION = "intervention"


class EventSource(str, Enum):
    SLACK = "slack"
    SCREEN = "screen"
    AGENT = "agent"


class GeminiExtraction(BaseModel):
    type: EventType
    actor: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    references_prior_event: Optional[UUID] = None


class EventCreate(BaseModel):
    incident_id: UUID
    source: EventSource
    raw_content: str
    image_data: Optional[bytes] = None
    actor: Optional[str] = None


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: EventSource
    actor: str
    type: EventType
    content: str
    embedding: Optional[Any] = None
    raw_ref: Optional[str] = None
    confidence: float = 1.0
    references_prior_event: Optional[UUID] = None

    @field_validator("embedding", mode="before")
    @classmethod
    def parse_embedding(cls, v):
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    class Config:
        from_attributes = True


class WarningPayload(BaseModel):
    event_id: UUID
    action_content: str
    similar_event_id: UUID
    similar_action_content: str
    past_outcome: str
    similarity_score: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PostMortem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    summary: str
    timeline: List[dict]
    root_cause_hypothesis: str
    actions_and_outcomes: List[dict]
    contributing_factors: List[str]
    follow_up_items: List[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
