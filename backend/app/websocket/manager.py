import asyncio
import json
import logging
from typing import Dict, Set, Optional
from uuid import UUID
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._incident_connections: Dict[str, Set[WebSocket]] = {}
        self._ws_to_client: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        if client_id not in self._connections:
            self._connections[client_id] = set()
        self._connections[client_id].add(websocket)
        self._ws_to_client[websocket] = client_id
        logger.info(f"Client {client_id} connected. Total connections: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket, client_id: str):
        self._ws_to_client.pop(websocket, None)

        if client_id in self._connections:
            self._connections[client_id].discard(websocket)
            if not self._connections[client_id]:
                del self._connections[client_id]

        for connections in self._incident_connections.values():
            connections.discard(websocket)

        # Clean up empty incident connection sets
        empty_incidents = [
            iid for iid, conns in self._incident_connections.items() if not conns
        ]
        for iid in empty_incidents:
            del self._incident_connections[iid]

        logger.info(f"Client {client_id} disconnected")

    async def subscribe_to_incident(self, websocket: WebSocket, incident_id: str):
        if incident_id not in self._incident_connections:
            self._incident_connections[incident_id] = set()
        self._incident_connections[incident_id].add(websocket)
        logger.info(f"Client subscribed to incident {incident_id}")

    async def unsubscribe_from_incident(self, websocket: WebSocket, incident_id: str):
        if incident_id in self._incident_connections:
            self._incident_connections[incident_id].discard(websocket)
            if not self._incident_connections[incident_id]:
                del self._incident_connections[incident_id]

    async def broadcast_to_all(self, message: dict):
        message_json = json.dumps(message)
        disconnected = set()

        for client_id, connections in list(self._connections.items()):
            for websocket in list(connections):
                if not self._is_alive(websocket):
                    disconnected.add((client_id, websocket))
                    continue
                try:
                    await websocket.send_text(message_json)
                except Exception:
                    disconnected.add((client_id, websocket))

        for client_id, websocket in disconnected:
            await self.disconnect(websocket, client_id)

    async def broadcast_to_incident(self, incident_id: str, message: dict):
        if incident_id not in self._incident_connections:
            return

        message_json = json.dumps(message)
        disconnected = set()

        # Iterate over a copy to avoid modification during iteration
        connections = list(self._incident_connections.get(incident_id, []))
        for websocket in connections:
            if not self._is_alive(websocket):
                disconnected.add(websocket)
                continue
            try:
                await websocket.send_text(message_json)
            except Exception:
                disconnected.add(websocket)

        for websocket in disconnected:
            client_id = self._ws_to_client.get(websocket, "unknown")
            await self.disconnect(websocket, client_id)

    async def send_to_client(self, client_id: str, message: dict):
        if client_id not in self._connections:
            return

        message_json = json.dumps(message)
        disconnected = set()

        for websocket in list(self._connections[client_id]):
            if not self._is_alive(websocket):
                disconnected.add(websocket)
                continue
            try:
                await websocket.send_text(message_json)
            except Exception:
                disconnected.add(websocket)

        for websocket in disconnected:
            await self.disconnect(websocket, client_id)

    def _is_alive(self, websocket: WebSocket) -> bool:
        try:
            # FastAPI's WebSocket client_state indicates if the connection is still open
            return websocket.client_state.name == "CONNECTED"
        except Exception:
            return False

    async def send_event(self, incident_id: str, event: dict):
        await self.broadcast_to_incident(
            incident_id,
            {
                "type": "event",
                "data": event,
            },
        )

    async def send_warning(self, incident_id: str, warning: dict):
        await self.broadcast_to_incident(
            incident_id,
            {
                "type": "warning",
                "data": warning,
            },
        )

    async def send_prediction(self, incident_id: str, prediction: dict):
        await self.broadcast_to_incident(
            incident_id,
            {
                "type": "prediction",
                "data": prediction,
            },
        )

    async def send_intervention(self, incident_id: str, intervention: dict):
        await self.broadcast_to_incident(
            incident_id,
            {
                "type": "intervention",
                "data": intervention,
            },
        )

    async def send_postmortem(self, incident_id: str, postmortem: dict):
        await self.broadcast_to_incident(
            incident_id,
            {
                "type": "postmortem",
                "data": postmortem,
            },
        )

    async def send_status_update(self, incident_id: str, status: str):
        await self.broadcast_to_incident(
            incident_id,
            {
                "type": "status_update",
                "data": {"incident_id": incident_id, "status": status},
            },
        )

    @property
    def active_connections(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


ws_manager = ConnectionManager()
