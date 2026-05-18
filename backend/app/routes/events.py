from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
from uuid import UUID

from ..models.event import Event, EventCreate, EventType, EventSource
from ..services.incident_memory import IncidentMemory
from ..services.event_pipeline import EventPipeline
from ..websocket.manager import ws_manager

router = APIRouter(prefix="/api/events", tags=["events"])

memory = IncidentMemory()
pipeline = EventPipeline()


@router.post("/text")
async def create_text_event(
    incident_id: UUID,
    content: str,
    source: EventSource = EventSource.SLACK,
    actor: Optional[str] = None,
):
    result = await pipeline.process_text_event(
        incident_id=incident_id,
        content=content,
        source=source,
        actor=actor,
    )

    events = result.get("events", [])
    prediction = result.get("prediction", None)

    for event in events:
        await ws_manager.send_event(
            str(incident_id), event.model_dump(mode="json")
        )

    return {
        "events": [e.model_dump(mode="json") for e in events],
        "prediction": prediction,
    }


@router.post("/image")
async def create_image_event(
    incident_id: UUID,
    image: UploadFile = File(...),
    source: EventSource = EventSource.SCREEN,
    actor: Optional[str] = None,
):
    image_data = await image.read()

    result = await pipeline.process_image_event(
        incident_id=incident_id,
        image_data=image_data,
        source=source,
        actor=actor,
    )

    events = result.get("events", [])
    prediction = result.get("prediction", None)

    for event in events:
        await ws_manager.send_event(
            str(incident_id), event.model_dump(mode="json")
        )

    return {
        "events": [e.model_dump(mode="json") for e in events],
        "prediction": prediction,
    }


@router.get("/incident/{incident_id}", response_model=List[Event])
async def get_events_for_incident(
    incident_id: UUID,
    event_type: Optional[EventType] = None,
):
    return await memory.get_events(incident_id, event_type)


@router.get("/incident/{incident_id}/analysis")
async def get_ai_analysis(incident_id: UUID):
    try:
        analysis = await pipeline.get_ai_analysis(incident_id)
        return {"analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
