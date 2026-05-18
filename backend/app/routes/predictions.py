from fastapi import APIRouter, HTTPException
from typing import List, Optional
from uuid import UUID
import logging

from ..models.prediction import Prediction, PredictionOutcome, PredictionUpdate
from ..services.incident_memory import IncidentMemory
from ..services.gemini_service import GeminiService
from ..services.cascade_prediction import CascadePredictionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])

memory = IncidentMemory()
gemini = GeminiService()
prediction_service = CascadePredictionService(memory, gemini)


@router.get("/incident/{incident_id}", response_model=List[Prediction])
async def get_predictions_for_incident(incident_id: UUID):
    return await prediction_service.get_predictions(incident_id)


@router.get("/incident/{incident_id}/accuracy")
async def get_prediction_accuracy(incident_id: UUID):
    return await prediction_service.get_prediction_accuracy(incident_id)


@router.post("/{prediction_id}/outcome")
async def update_prediction_outcome(
    prediction_id: UUID,
    outcome: PredictionOutcome,
    actual_time_to_failure_minutes: Optional[int] = None,
):
    result = await prediction_service.update_prediction_outcome(
        prediction_id, outcome, actual_time_to_failure_minutes
    )
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result


@router.post("/generate/{incident_id}")
async def generate_prediction(incident_id: UUID):
    try:
        prediction = await prediction_service.generate_prediction(incident_id)
        if not prediction:
            return {"message": "Not enough data to generate prediction"}
        if prediction.confidence < 0.55:
            return {
                "message": "Confidence too low",
                "prediction": prediction.model_dump(mode="json"),
            }
        saved = await prediction_service._store_and_broadcast(incident_id, prediction)
        return saved.model_dump(mode="json")
    except Exception as e:
        logger.error(f"Generate prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
