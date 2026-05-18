from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from uuid import UUID

from ..services.postmortem_engine import PostMortemEngine
from ..services.incident_memory import IncidentMemory
from ..services.gemini_service import GeminiService
from ..websocket.manager import ws_manager

router = APIRouter(prefix="/api/postmortems", tags=["postmortems"])

memory = IncidentMemory()
gemini = GeminiService()
postmortem_engine = PostMortemEngine(memory, gemini)


@router.post("/generate/{incident_id}")
async def generate_postmortem(incident_id: UUID):
    try:
        postmortem = await postmortem_engine.generate_post_mortem(incident_id)
        await ws_manager.send_postmortem(str(incident_id), postmortem)
        return postmortem
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate post-mortem: {str(e)}")


@router.get("/incident/{incident_id}")
async def get_postmortem(incident_id: UUID):
    postmortem = await memory.get_post_mortem(incident_id)
    if not postmortem:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    return postmortem


@router.get("/incident/{incident_id}/markdown", response_class=PlainTextResponse)
async def export_postmortem_markdown(incident_id: UUID):
    try:
        markdown = await postmortem_engine.export_as_markdown(incident_id)
        return PlainTextResponse(
            content=markdown,
            headers={"Content-Disposition": f"attachment; filename=postmortem_{incident_id}.md"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
