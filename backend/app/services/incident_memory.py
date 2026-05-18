from supabase import create_client, Client
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import logging
import re

from ..config import settings
from ..models.incident import Incident, IncidentCreate, IncidentUpdate, IncidentStatus
from ..models.event import Event, EventCreate, EventType, EventSource

logger = logging.getLogger(__name__)


class IncidentMemory:
    def __init__(self):
        self.client: Client = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_KEY
        )

    async def create_incident(self, incident: IncidentCreate) -> Incident:
        data = {
            "title": incident.title,
            "status": incident.status.value,
            "started_at": datetime.utcnow().isoformat(),
            "warning_count": 0,
        }
        result = self.client.table("incidents").insert(data).execute()
        row = result.data[0]
        return Incident(
            id=UUID(row["id"]),
            title=row["title"],
            status=IncidentStatus(row["status"]),
            started_at=self._to_datetime(row["started_at"]),
            resolved_at=(
                self._to_datetime(row["resolved_at"])
                if row.get("resolved_at")
                else None
            ),
            warning_count=row.get("warning_count", 0),
        )

    async def get_incident(self, incident_id: UUID) -> Optional[Incident]:
        result = (
            self.client.table("incidents")
            .select("*")
            .eq("id", str(incident_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        return Incident(
            id=UUID(row["id"]),
            title=row["title"],
            status=IncidentStatus(row["status"]),
            started_at=self._to_datetime(row["started_at"]),
            resolved_at=(
                self._to_datetime(row["resolved_at"])
                if row.get("resolved_at")
                else None
            ),
            warning_count=row.get("warning_count", 0),
        )

    async def list_incidents(
        self, status: Optional[IncidentStatus] = None
    ) -> List[Incident]:
        query = self.client.table("incidents").select("*")
        if status:
            query = query.eq("status", status.value)
        query = query.order("started_at", desc=True)
        result = query.execute()

        return [
            Incident(
                id=UUID(row["id"]),
                title=row["title"],
                status=IncidentStatus(row["status"]),
                started_at=self._to_datetime(row["started_at"]),
                resolved_at=(
                    self._to_datetime(row["resolved_at"])
                    if row.get("resolved_at")
                    else None
                ),
                warning_count=row.get("warning_count", 0),
            )
            for row in result.data
        ]

    async def update_incident(
        self, incident_id: UUID, update
    ) -> Optional[Incident]:
        data = {}
        if isinstance(update, dict):
            for k, v in update.items():
                if v is not None:
                    if k == "status" and hasattr(v, "value"):
                        data[k] = v.value
                    elif k == "resolved_at" and hasattr(v, "isoformat"):
                        data[k] = v.isoformat()
                    else:
                        data[k] = v
        else:
            if update.title is not None:
                data["title"] = update.title
            if update.status is not None:
                data["status"] = update.status.value
            if update.resolved_at is not None:
                data["resolved_at"] = update.resolved_at.isoformat()

        if not data:
            return await self.get_incident(incident_id)

        result = (
            self.client.table("incidents")
            .update(data)
            .eq("id", str(incident_id))
            .execute()
        )
        if not result.data:
            return None

        return await self.get_incident(incident_id)

    async def create_event(
        self,
        event_data: dict,
    ) -> Event:
        raw_embedding = event_data.get("embedding")
        data = {
            "incident_id": str(event_data["incident_id"]),
            "timestamp": datetime.utcnow().isoformat(),
            "source": event_data["source"],
            "actor": event_data["actor"],
            "type": event_data["type"],
            "content": event_data["content"],
            "embedding": self._format_embedding(raw_embedding),
            "raw_ref": event_data.get("raw_ref"),
            "confidence": event_data.get("confidence", 1.0),
            "references_prior_event": (
                str(event_data["references_prior_event"])
                if event_data.get("references_prior_event")
                else None
            ),
        }
        try:
            result = self.client.table("events").insert(data).execute()
        except Exception as e:
            expected_dim = self._extract_expected_dimension_from_error(e)
            if expected_dim and raw_embedding:
                logger.warning(
                    "Embedding dimension mismatch detected. Retrying insert with %s dimensions.",
                    expected_dim,
                )
                adjusted = self._normalize_embedding_to_dimension(raw_embedding, expected_dim)
                data["embedding"] = self._format_embedding(adjusted, expected_dim)
                result = self.client.table("events").insert(data).execute()
            else:
                raise
        row = result.data[0]
        return Event(
            id=UUID(row["id"]),
            incident_id=UUID(row["incident_id"]),
            timestamp=self._to_datetime(row["timestamp"]),
            source=EventSource(row["source"]),
            actor=row["actor"],
            type=EventType(row["type"]),
            content=row["content"],
            embedding=row.get("embedding"),
            raw_ref=row.get("raw_ref"),
            confidence=row.get("confidence", 1.0),
            references_prior_event=(
                UUID(row["references_prior_event"])
                if row.get("references_prior_event")
                else None
            ),
        )

    async def get_events(
        self,
        incident_id: UUID,
        event_type: Optional[EventType] = None,
    ) -> List[Event]:
        query = (
            self.client.table("events")
            .select("*")
            .eq("incident_id", str(incident_id))
        )
        if event_type:
            query = query.eq("type", event_type.value)
        query = query.order("timestamp", desc=False)
        result = query.execute()

        return [
            Event(
                id=UUID(row["id"]),
                incident_id=UUID(row["incident_id"]),
                timestamp=self._to_datetime(row["timestamp"]),
                source=EventSource(row["source"]),
                actor=row["actor"],
                type=EventType(row["type"]),
                content=row["content"],
                embedding=row.get("embedding"),
                raw_ref=row.get("raw_ref"),
                confidence=row.get("confidence", 1.0),
                references_prior_event=(
                    UUID(row["references_prior_event"])
                    if row.get("references_prior_event")
                    else None
                ),
            )
            for row in result.data
        ]

    async def search_similar_events(
        self,
        embedding: List[float],
        event_type: Optional[EventType] = None,
        threshold: float = 0.85,
        limit: int = 5,
    ) -> List[Dict]:
        payload = {
            "query_embedding": self._format_embedding(embedding),
            "match_threshold": threshold,
            "match_count": limit,
            "filter_type": event_type.value if event_type else None,
        }
        try:
            query = self.client.rpc("search_similar_events", payload)
            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            expected_dim = self._extract_expected_dimension_from_error(e)
            if not expected_dim:
                raise

            adjusted = self._normalize_embedding_to_dimension(embedding, expected_dim)
            payload["query_embedding"] = self._format_embedding(adjusted, expected_dim)
            query = self.client.rpc("search_similar_events", payload)
            result = query.execute()
            return result.data if result.data else []

    async def get_event_by_id(self, event_id: UUID) -> Optional[Event]:
        result = (
            self.client.table("events")
            .select("*")
            .eq("id", str(event_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        return Event(
            id=UUID(row["id"]),
            incident_id=UUID(row["incident_id"]),
            timestamp=self._to_datetime(row["timestamp"]),
            source=EventSource(row["source"]),
            actor=row["actor"],
            type=EventType(row["type"]),
            content=row["content"],
            embedding=row.get("embedding"),
            raw_ref=row.get("raw_ref"),
            confidence=row.get("confidence", 1.0),
            references_prior_event=(
                UUID(row["references_prior_event"])
                if row.get("references_prior_event")
                else None
            ),
        )

    async def save_post_mortem(self, post_mortem: dict) -> dict:
        data = {
            "incident_id": str(post_mortem["incident_id"]),
            "summary": post_mortem["summary"],
            "timeline": post_mortem["timeline"],
            "root_cause_hypothesis": post_mortem["root_cause_hypothesis"],
            "actions_and_outcomes": post_mortem["actions_and_outcomes"],
            "contributing_factors": post_mortem["contributing_factors"],
            "follow_up_items": post_mortem["follow_up_items"],
            "generated_at": datetime.utcnow().isoformat(),
        }
        if "prediction_retrospective" in post_mortem:
            data["prediction_retrospective"] = post_mortem["prediction_retrospective"]
        result = self.client.table("post_mortems").insert(data).execute()
        return result.data[0]

    async def get_post_mortem(self, incident_id: UUID) -> Optional[Dict]:
        result = (
            self.client.table("post_mortems")
            .select("*")
            .eq("incident_id", str(incident_id))
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    async def increment_warning_count(self, incident_id: UUID) -> int:
        result = self.client.rpc(
            "increment_warning_count",
            {"p_incident_id": str(incident_id)},
        ).execute()
        return result.data if result.data else 0

    async def reset_warning_count(self, incident_id: UUID) -> None:
        self.client.table("incidents").update(
            {"warning_count": 0}
        ).eq("id", str(incident_id)).execute()

    async def get_historical_resolution_paths(
        self, incident_ids: List[UUID]
    ) -> List[Dict]:
        if not incident_ids:
            return []

        results = []
        for incident_id in incident_ids:
            incident = await self.get_incident(incident_id)
            if not incident:
                continue
            if incident.status != IncidentStatus.RESOLVED:
                continue

            events = await self.get_events(incident_id)
            if not events:
                continue

            inflection_idx = self._find_inflection_index(events)
            resolution_events = events[inflection_idx:] if inflection_idx is not None else []
            resolution_actions = [
                e for e in resolution_events if e.type in (EventType.ACTION, EventType.OUTCOME)
            ]

            resolution_time = None
            if incident.resolved_at and incident.started_at:
                resolution_time = (
                    incident.resolved_at - incident.started_at
                ).total_seconds() / 60

            results.append({
                "incident_id": str(incident_id),
                "title": incident.title,
                "events": [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "type": e.type.value,
                        "actor": e.actor,
                        "content": e.content,
                    }
                    for e in events
                ],
                "resolution_events": [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "type": e.type.value,
                        "actor": e.actor,
                        "content": e.content,
                    }
                    for e in resolution_events
                ],
                "resolution_actions": [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "type": e.type.value,
                        "actor": e.actor,
                        "content": e.content,
                    }
                    for e in resolution_actions
                ],
                "resolution_time_minutes": resolution_time,
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            })

        return results

    def _find_inflection_index(self, events: List[Event]) -> Optional[int]:
        seen_negative = False
        for idx, event in enumerate(events):
            if event.type != EventType.OUTCOME:
                continue
            if self._is_negative_outcome(event.content):
                seen_negative = True
                continue
            if seen_negative:
                return idx
        return None

    def _is_negative_outcome(self, outcome: str) -> bool:
        negative = [
            "failed", "failure", "error", "rolled back", "rollback",
            "no effect", "no change", "worsened", "degraded", "crashed",
            "timeout", "rejected", "unsuccessful", "broken", "didn't work",
            "still down", "still failing", "made it worse", "didn't fix",
            "no improvement", "same issue", "still broken", "not working",
        ]
        outcome_lower = outcome.lower()
        return any(word in outcome_lower for word in negative)

    def _to_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)

    def _format_embedding(self, embedding: Optional[List[float]], dimension: Optional[int] = None) -> Optional[str]:
        if not embedding:
            return None
        if dimension:
            embedding = self._normalize_embedding_to_dimension(embedding, dimension)
        return "[" + ",".join(str(x) for x in embedding) + "]"

    def _normalize_embedding_to_dimension(self, embedding: List[float], dimension: int) -> List[float]:
        if len(embedding) == dimension:
            return embedding
        if len(embedding) > dimension:
            return embedding[:dimension]
        return embedding + ([0.0] * (dimension - len(embedding)))

    def _extract_expected_dimension_from_error(self, error: Exception) -> Optional[int]:
        message = str(error)
        match = re.search(r"expected\s+(\d+)\s+dimensions", message)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None
