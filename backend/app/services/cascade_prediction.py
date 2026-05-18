import asyncio
import logging
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime

from ..config import settings
from ..models.event import Event, EventType
from ..models.prediction import Prediction, PredictionCreate, PredictionOutcome, CausalChainItem
from .incident_memory import IncidentMemory
from .gemini_service import GeminiService
from ..websocket.manager import ws_manager

logger = logging.getLogger(__name__)

PREDICTION_INTERVAL_SECONDS = 8
CONFIDENCE_THRESHOLD = 0.50
PREDICTION_COOLDOWN_SECONDS = 3

class CascadePredictionService:
    def __init__(self, memory: IncidentMemory, gemini: GeminiService):
        self.memory = memory
        self.gemini = gemini
        self._active_loops: Dict[str, asyncio.Task] = {}
        self._last_prediction_time: Dict[str, datetime] = {}

    async def start_prediction_loop(self, incident_id: UUID):
        incident_id_str = str(incident_id)
        if incident_id_str in self._active_loops:
            logger.info(f"Prediction loop already running for incident {incident_id_str}")
            return

        task = asyncio.create_task(self._prediction_loop(incident_id))
        self._active_loops[incident_id_str] = task
        logger.info(f"Started prediction loop for incident {incident_id_str}")

    async def stop_prediction_loop(self, incident_id: UUID):
        incident_id_str = str(incident_id)
        task = self._active_loops.pop(incident_id_str, None)
        if task:
            task.cancel()
            logger.info(f"Stopped prediction loop for incident {incident_id_str}")

    async def _prediction_loop(self, incident_id: UUID):
        try:
            while True:
                await asyncio.sleep(PREDICTION_INTERVAL_SECONDS)

                try:
                    prediction = await self.generate_prediction(incident_id)
                    if prediction and prediction.confidence >= CONFIDENCE_THRESHOLD:
                        await self._store_and_broadcast(incident_id, prediction)
                except Exception as e:
                    logger.error(f"Prediction iteration failed for incident {incident_id}: {e}")
        except asyncio.CancelledError:
            logger.info(f"Prediction loop cancelled for incident {incident_id}")

    async def generate_prediction(self, incident_id: UUID) -> Optional[Prediction]:
        incident_id_str = str(incident_id)
        now = datetime.utcnow()
        last_time = self._last_prediction_time.get(incident_id_str)
        if last_time and (now - last_time).total_seconds() < PREDICTION_COOLDOWN_SECONDS:
            return None

        events = await self.memory.get_events(incident_id)
        if len(events) < 2:
            return None

        events_data = [
            {
                "timestamp": e.timestamp.isoformat(),
                "type": e.type.value,
                "actor": e.actor,
                "content": e.content,
                "source": e.source.value,
            }
            for e in events
        ]

        slack_messages = [e.content for e in events if e.source.value == "slack"]
        screenshot_descriptions = [e.content for e in events if e.source.value == "screen"]

        result = await self.gemini.predict_cascade(
            events=events_data,
            slack_messages=slack_messages,
            screenshot_descriptions=screenshot_descriptions,
        )

        if not result or not result.get("prediction"):
            return None

        causal_chain = [
            CausalChainItem(**item)
            for item in result.get("causal_chain", [])
        ]

        return Prediction(
            incident_id=incident_id,
            predicted_failure=result["prediction"],
            confidence=result.get("confidence", 0.0),
            time_to_failure_minutes=result.get("time_to_failure_minutes"),
            causal_chain=causal_chain,
            suggested_action=result.get("suggested_action"),
        )

    async def _store_and_broadcast(self, incident_id: UUID, prediction: Prediction):
        self._last_prediction_time[str(incident_id)] = datetime.utcnow()
        saved = await self.save_prediction(prediction)

        await ws_manager.send_prediction(
            str(incident_id),
            {
                "id": str(saved.id),
                "incident_id": str(saved.incident_id),
                "created_at": saved.created_at.isoformat(),
                "predicted_failure": saved.predicted_failure,
                "confidence": saved.confidence,
                "time_to_failure_minutes": saved.time_to_failure_minutes,
                "causal_chain": [item.model_dump() for item in saved.causal_chain],
                "suggested_action": saved.suggested_action,
                "outcome": saved.outcome.value if saved.outcome else None,
            },
        )

        logger.info(
            f"Prediction broadcast: {saved.predicted_failure} "
            f"(confidence: {saved.confidence:.2f}, "
            f"time: {saved.time_to_failure_minutes}min)"
        )

    async def save_prediction(self, prediction: Prediction) -> Prediction:
        data = {
            "incident_id": str(prediction.incident_id),
            "predicted_failure": prediction.predicted_failure,
            "confidence": prediction.confidence,
            "time_to_failure_minutes": prediction.time_to_failure_minutes,
            "causal_chain": [item.model_dump() for item in prediction.causal_chain],
            "suggested_action": prediction.suggested_action,
            "outcome": prediction.outcome.value if prediction.outcome else None,
            "actual_time_to_failure_minutes": prediction.actual_time_to_failure_minutes,
        }
        result = self.memory.client.table("predictions").insert(data).execute()
        row = result.data[0]
        return Prediction(
            id=UUID(row["id"]),
            incident_id=UUID(row["incident_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            predicted_failure=row["predicted_failure"],
            confidence=row["confidence"],
            time_to_failure_minutes=row.get("time_to_failure_minutes"),
            causal_chain=[CausalChainItem(**item) for item in row.get("causal_chain", [])],
            suggested_action=row.get("suggested_action"),
            outcome=PredictionOutcome(row["outcome"]) if row.get("outcome") else None,
            actual_time_to_failure_minutes=row.get("actual_time_to_failure_minutes"),
        )

    async def get_predictions(self, incident_id: UUID) -> List[Prediction]:
        result = (
            self.memory.client.table("predictions")
            .select("*")
            .eq("incident_id", str(incident_id))
            .order("created_at", desc=False)
            .execute()
        )
        return [
            Prediction(
                id=UUID(row["id"]),
                incident_id=UUID(row["incident_id"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                predicted_failure=row["predicted_failure"],
                confidence=row["confidence"],
                time_to_failure_minutes=row.get("time_to_failure_minutes"),
                causal_chain=[CausalChainItem(**item) for item in row.get("causal_chain", [])],
                suggested_action=row.get("suggested_action"),
                outcome=PredictionOutcome(row["outcome"]) if row.get("outcome") else None,
                actual_time_to_failure_minutes=row.get("actual_time_to_failure_minutes"),
            )
            for row in result.data
        ]

    async def update_prediction_outcome(
        self,
        prediction_id: UUID,
        outcome: PredictionOutcome,
        actual_time_to_failure_minutes: Optional[int] = None,
    ) -> Optional[Prediction]:
        data = {"outcome": outcome.value}
        if actual_time_to_failure_minutes is not None:
            data["actual_time_to_failure_minutes"] = actual_time_to_failure_minutes

        result = (
            self.memory.client.table("predictions")
            .update(data)
            .eq("id", str(prediction_id))
            .execute()
        )
        if not result.data:
            return None

        row = result.data[0]
        return Prediction(
            id=UUID(row["id"]),
            incident_id=UUID(row["incident_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            predicted_failure=row["predicted_failure"],
            confidence=row["confidence"],
            time_to_failure_minutes=row.get("time_to_failure_minutes"),
            causal_chain=[CausalChainItem(**item) for item in row.get("causal_chain", [])],
            suggested_action=row.get("suggested_action"),
            outcome=PredictionOutcome(row["outcome"]) if row.get("outcome") else None,
            actual_time_to_failure_minutes=row.get("actual_time_to_failure_minutes"),
        )

    async def get_prediction_accuracy(self, incident_id: UUID) -> Dict:
        predictions = await self.get_predictions(incident_id)
        total = len(predictions)
        correct = sum(1 for p in predictions if p.outcome == PredictionOutcome.CORRECT)
        incorrect = sum(1 for p in predictions if p.outcome == PredictionOutcome.INCORRECT)
        unresolved = sum(1 for p in predictions if p.outcome == PredictionOutcome.UNRESOLVED or p.outcome is None)

        time_accuracies = [
            abs(p.time_to_failure_minutes - p.actual_time_to_failure_minutes)
            for p in predictions
            if p.outcome == PredictionOutcome.CORRECT
            and p.time_to_failure_minutes is not None
            and p.actual_time_to_failure_minutes is not None
        ]
        avg_time_accuracy = sum(time_accuracies) / len(time_accuracies) if time_accuracies else None

        return {
            "incident_id": str(incident_id),
            "total_predictions": total,
            "correct_predictions": correct,
            "incorrect_predictions": incorrect,
            "unresolved_predictions": unresolved,
            "avg_time_accuracy_minutes": round(avg_time_accuracy, 1) if avg_time_accuracy else None,
        }
