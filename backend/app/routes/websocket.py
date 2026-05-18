from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..websocket.manager import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "subscribe_incident":
                incident_id = data.get("incident_id")
                if incident_id:
                    await ws_manager.subscribe_to_incident(websocket, incident_id)
                    try:
                        await websocket.send_json(
                            {"type": "subscribed", "incident_id": incident_id}
                        )
                    except Exception:
                        pass

            elif action == "unsubscribe_incident":
                incident_id = data.get("incident_id")
                if incident_id:
                    await ws_manager.unsubscribe_from_incident(websocket, incident_id)
                    try:
                        await websocket.send_json(
                            {"type": "unsubscribed", "incident_id": incident_id}
                        )
                    except Exception:
                        pass

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, client_id)
    except RuntimeError:
        # Client closed connection while we were processing
        await ws_manager.disconnect(websocket, client_id)
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(f"WebSocket error for client {client_id}: {e}")
        await ws_manager.disconnect(websocket, client_id)
