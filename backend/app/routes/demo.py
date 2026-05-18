from fastapi import APIRouter
from uuid import uuid4
from datetime import datetime, timedelta
import asyncio

from ..services.incident_memory import IncidentMemory
from ..services.event_pipeline import EventPipeline
from ..services.cascade_prediction import CascadePredictionService
from ..services.gemini_service import GeminiService
from ..models.incident import IncidentCreate, IncidentStatus
from ..models.event import EventType, EventSource
from ..websocket.manager import ws_manager

router = APIRouter(prefix="/api/demo", tags=["demo"])

memory = IncidentMemory()
pipeline = EventPipeline()
gemini = GeminiService()
prediction_service = CascadePredictionService(memory, gemini)

DEMO_MESSAGES = [
    {"text": "Seeing a spike in 500 errors on the payment API. Error rate jumped from 0.1% to 12% in the last 5 minutes.", "actor": "sarah", "source": "slack", "delay": 0},
    {"text": "Alert: Payment service latency p99 exceeded 5000ms threshold. Current p99 is 8200ms.", "actor": "monitoring-bot", "source": "slack", "delay": 2},
    {"text": "Could this be the new deploy from 30 minutes ago? v2.14.0 included changes to the payment gateway integration.", "actor": "james", "source": "slack", "delay": 4},
    {"text": "Restarting the payment service pods to clear any stuck connections.", "actor": "james", "source": "slack", "delay": 6},
    {"text": "Restart failed - service still returning 500 errors. Connection pool still exhausted.", "actor": "sarah", "source": "slack", "delay": 8},
    {"text": "Checking the database connection pool metrics. Seeing connections not being released after transactions complete. Connection leak suspected.", "actor": "sarah", "source": "slack", "delay": 10},
    {"text": "Found it. The new Stripe webhook handler in PR #1847 removed the finally block that closes DB sessions. Connections are leaking on every webhook call.", "actor": "james", "source": "slack", "delay": 12},
    {"text": "Rolling back payment service to v2.13.2 while we prepare the hotfix.", "actor": "james", "source": "slack", "delay": 14},
    {"text": "Rollback complete. DB connections dropping back to normal levels. Error rate decreasing.", "actor": "sarah", "source": "slack", "delay": 16},
    {"text": "Payment service error rate returned to baseline 0.1%. Latency p99 back to 340ms. All systems nominal.", "actor": "monitoring-bot", "source": "slack", "delay": 18},
    {"text": "Hotfix PR #1852 created with the connection leak fix. Added integration tests for connection pool cleanup. Merging now.", "actor": "sarah", "source": "slack", "delay": 20},
    {"text": "Hotfix deployed as v2.14.1. Monitoring shows stable connection pool and zero errors. Incident resolved.", "actor": "james", "source": "slack", "delay": 22},
]

FAKE_PREDICTION = {
    "prediction": "Auth service will cascade",
    "confidence": 0.87,
    "time_to_failure_minutes": 5,
    "causal_chain": [
        {"signal": "CPU saturation at 94%", "source": "screenshot", "timestamp": "14:23:01"},
        {"signal": "Retry storm mentioned, 3400 retries/sec", "source": "slack", "timestamp": "14:21:44"},
        {"signal": "Payment and auth share connection pool", "source": "log", "timestamp": "14:19:12"},
    ],
    "suggested_action": "Increase connection pool limit or circuit break payment before auth degrades",
}


@router.post("/seed")
async def seed_demo_data():
    incident = await memory.create_incident(
        IncidentCreate(title="Payment API 500 errors - Connection pool exhaustion")
    )
    incident_id = incident.id

    for msg in DEMO_MESSAGES:
        await pipeline.process_text_event(
            incident_id=incident_id,
            content=msg["text"],
            source=EventSource(msg["source"]),
            actor=msg["actor"],
        )

    from datetime import datetime
    await memory.update_incident(
        incident_id,
        {"status": IncidentStatus.RESOLVED, "resolved_at": datetime.utcnow().isoformat()},
    )

    return {
        "incident_id": str(incident_id),
        "events_count": len(DEMO_MESSAGES),
        "message": "Demo data seeded through Gemini pipeline",
    }


@router.post("/seed-warnings")
async def seed_warning_demo():
    incident = await memory.create_incident(
        IncidentCreate(title="Database failover - primary node unresponsive")
    )
    incident_id = incident.id

    warning_messages = [
        {"text": "Primary database node unresponsive. Automatic failover to replica initiated.", "actor": "alert-system", "source": "slack"},
        {"text": "Restarting the primary database node to recover from unresponsive state.", "actor": "mike", "source": "slack"},
        {"text": "Restart failed - node still unresponsive. Hardware issue suspected.", "actor": "mike", "source": "slack"},
        {"text": "Attempting to restart the primary database node again with forced cache clear.", "actor": "mike", "source": "slack"},
    ]

    for msg in warning_messages:
        await pipeline.process_text_event(
            incident_id=incident_id,
            content=msg["text"],
            source=EventSource(msg["source"]),
            actor=msg["actor"],
        )

    return {
        "incident_id": str(incident_id),
        "events_count": len(warning_messages),
        "message": "Warning demo seeded through Gemini pipeline",
    }


@router.post("/replay")
async def replay_demo():
    incident = await memory.create_incident(
        IncidentCreate(title="[DEMO] Auth Cascade Prediction - Live Replay")
    )
    incident_id = incident.id

    await pipeline.start_predictions(incident_id)
    asyncio.create_task(_replay_events(incident_id))

    return {
        "incident_id": str(incident_id),
        "message": "Demo replay started. Events will stream in real-time.",
    }


async def _replay_events(incident_id):
    from ..models.prediction import Prediction, CausalChainItem

    prev_delay = 0
    for msg in DEMO_MESSAGES:
        current_delay = msg.get("delay", 0)
        wait_time = max(0, current_delay - prev_delay)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        prev_delay = current_delay

        result = await pipeline.process_text_event(
            incident_id=incident_id,
            content=msg["text"],
            source=EventSource(msg["source"]),
            actor=msg["actor"],
        )

        for event in result.get("events", []):
            await ws_manager.send_event(str(incident_id), event.model_dump(mode="json"))

        if current_delay == 10:
            await asyncio.sleep(1.5)
            prediction = Prediction(
                incident_id=incident_id,
                predicted_failure=FAKE_PREDICTION["prediction"],
                confidence=FAKE_PREDICTION["confidence"],
                time_to_failure_minutes=FAKE_PREDICTION["time_to_failure_minutes"],
                causal_chain=[CausalChainItem(**item) for item in FAKE_PREDICTION["causal_chain"]],
                suggested_action=FAKE_PREDICTION["suggested_action"],
            )
            saved = await prediction_service.save_prediction(prediction)
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
                    "outcome": None,
                },
            )

    await asyncio.sleep(3)
    await memory.update_incident(
        incident_id,
        {"status": IncidentStatus.RESOLVED, "resolved_at": datetime.utcnow().isoformat()},
    )
    await ws_manager.send_status_update(str(incident_id), "resolved")
