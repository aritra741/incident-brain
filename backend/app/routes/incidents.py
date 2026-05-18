from fastapi import APIRouter, HTTPException
from typing import List, Optional
from uuid import UUID

from ..models.incident import Incident, IncidentCreate, IncidentUpdate, IncidentStatus
from ..services.incident_memory import IncidentMemory
from ..services.event_pipeline import EventPipeline
from ..websocket.manager import ws_manager

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

memory = IncidentMemory()
pipeline = EventPipeline()


@router.post("/", response_model=Incident)
async def create_incident(incident: IncidentCreate):
    result = await memory.create_incident(incident)
    await pipeline.start_predictions(result.id)
    await ws_manager.broadcast_to_all(
        {"type": "incident_created", "data": result.model_dump(mode="json")}
    )
    return result


@router.get("/", response_model=List[Incident])
async def list_incidents(status: Optional[IncidentStatus] = None):
    return await memory.list_incidents(status)


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: UUID):
    incident = await memory.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=Incident)
async def update_incident(incident_id: UUID, update: IncidentUpdate):
    incident = await memory.update_incident(incident_id, update)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if update.status == IncidentStatus.RESOLVED:
        await pipeline.resolve_incident(incident_id)
        await ws_manager.send_status_update(str(incident_id), "resolved")

    return incident


@router.post("/{incident_id}/resolve", response_model=Incident)
async def resolve_incident(incident_id: UUID):
    from datetime import datetime

    update = IncidentUpdate(
        status=IncidentStatus.RESOLVED,
        resolved_at=datetime.utcnow(),
    )
    incident = await memory.update_incident(incident_id, update)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await pipeline.resolve_incident(incident_id)
    await ws_manager.send_status_update(str(incident_id), "resolved")
    return incident


@router.delete("/{incident_id}")
async def delete_incident(incident_id: UUID):
    try:
        await pipeline.stop_predictions(incident_id)
        memory.client.table("predictions").delete().eq("incident_id", str(incident_id)).execute()
        memory.client.table("events").delete().eq("incident_id", str(incident_id)).execute()
        memory.client.table("post_mortems").delete().eq("incident_id", str(incident_id)).execute()
        memory.client.table("incidents").delete().eq("id", str(incident_id)).execute()
        return {"message": "Incident deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")
