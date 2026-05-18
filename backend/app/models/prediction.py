from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4


class PredictionOutcome(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNRESOLVED = "unresolved"


class CausalChainItem(BaseModel):
    signal: str
    source: str
    timestamp: str


class PredictionCreate(BaseModel):
    incident_id: UUID
    predicted_failure: str
    confidence: float = Field(ge=0.0, le=1.0)
    time_to_failure_minutes: Optional[int] = None
    causal_chain: List[CausalChainItem] = []
    suggested_action: Optional[str] = None


class Prediction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    predicted_failure: str
    confidence: float = Field(ge=0.0, le=1.0)
    time_to_failure_minutes: Optional[int] = None
    causal_chain: List[CausalChainItem] = []
    suggested_action: Optional[str] = None
    outcome: Optional[PredictionOutcome] = None
    actual_time_to_failure_minutes: Optional[int] = None

    class Config:
        from_attributes = True


class PredictionUpdate(BaseModel):
    outcome: Optional[PredictionOutcome] = None
    actual_time_to_failure_minutes: Optional[int] = None


class PredictionAccuracy(BaseModel):
    incident_id: UUID
    total_predictions: int
    correct_predictions: int
    incorrect_predictions: int
    unresolved_predictions: int
    avg_time_accuracy_minutes: Optional[float] = None
