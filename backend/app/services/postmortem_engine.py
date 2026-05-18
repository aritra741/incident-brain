from typing import Dict, List
from uuid import UUID
from datetime import datetime
import logging

from ..models.event import Event, EventType
from ..models.incident import Incident, IncidentStatus
from ..models.prediction import PredictionOutcome
from .incident_memory import IncidentMemory
from .gemini_service import GeminiService
from .cascade_prediction import CascadePredictionService

logger = logging.getLogger(__name__)


class PostMortemEngine:
    def __init__(self, memory: IncidentMemory, gemini: GeminiService):
        self.memory = memory
        self.gemini = gemini
        self.prediction_service = CascadePredictionService(memory, gemini)

    async def generate_post_mortem(self, incident_id: UUID) -> Dict:
        incident = await self.memory.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        if incident.status != IncidentStatus.RESOLVED:
            raise ValueError("Can only generate post-mortems for resolved incidents")

        events = await self.memory.get_events(incident_id)
        predictions = await self.prediction_service.get_predictions(incident_id)

        duration_minutes = 0.0
        if incident.resolved_at and incident.started_at:
            delta = incident.resolved_at - incident.started_at
            duration_minutes = delta.total_seconds() / 60.0

        events_data = [
            {
                "timestamp": event.timestamp.isoformat(),
                "type": event.type.value,
                "actor": event.actor,
                "content": event.content,
                "source": event.source.value,
            }
            for event in events
        ]

        warnings_data = await self._collect_warnings(incident_id, events)

        predictions_data = [
            {
                "predicted_failure": p.predicted_failure,
                "confidence": p.confidence,
                "time_to_failure_minutes": p.time_to_failure_minutes,
                "outcome": p.outcome.value if p.outcome else "unresolved",
            }
            for p in predictions
        ]

        post_mortem_data = await self.gemini.generate_post_mortem(
            events=events_data,
            warnings=warnings_data,
            duration_minutes=duration_minutes,
            predictions=predictions_data if predictions_data else None,
        )

        post_mortem_data["incident_id"] = str(incident_id)

        if predictions:
            try:
                retrospective = await self.gemini.generate_prediction_retrospective(
                    predictions=predictions_data,
                    events=events_data,
                )
                post_mortem_data["prediction_retrospective"] = retrospective
            except Exception as e:
                logger.error(f"Prediction retrospective failed: {e}")
                post_mortem_data["prediction_retrospective"] = None

        saved = await self.memory.save_post_mortem(post_mortem_data)

        return saved

    async def _collect_warnings(
        self, incident_id: UUID, events: List[Event]
    ) -> List[Dict]:
        warnings = []
        for event in events:
            if event.type == EventType.ACTION and event.embedding:
                similar = await self.memory.search_similar_events(
                    embedding=event.embedding,
                    event_type=EventType.ACTION,
                    threshold=0.85,
                    limit=1,
                )
                if similar:
                    warnings.append(
                        {
                            "action_content": event.content,
                            "similarity_score": similar[0].get("similarity", 0),
                        }
                    )
        return warnings

    async def export_as_markdown(self, incident_id: UUID) -> str:
        incident = await self.memory.get_incident(incident_id)
        post_mortem = await self.memory.get_post_mortem(incident_id)

        if not post_mortem:
            raise ValueError("Post-mortem not found")

        md = f"# Post-Mortem: {incident.title}\n\n"
        md += f"**Status:** {incident.status.value}\n"
        md += f"**Started:** {incident.started_at.isoformat()}\n"
        if incident.resolved_at:
            md += f"**Resolved:** {incident.resolved_at.isoformat()}\n"
        md += "\n---\n\n"

        md += f"## Summary\n\n{post_mortem['summary']}\n\n"

        md += "## Timeline\n\n"
        md += "| Time | Event |\n|---|---|\n"
        for item in post_mortem.get("timeline", []):
            md += f"| {item.get('time', 'N/A')} | {item.get('event', 'N/A')} |\n"
        md += "\n"

        md += f"## Root Cause Hypothesis\n\n{post_mortem['root_cause_hypothesis']}\n\n"

        md += "## Actions & Outcomes\n\n"
        for item in post_mortem.get("actions_and_outcomes", []):
            md += f"- **Action:** {item.get('action', 'N/A')}\n"
            md += f"  **Outcome:** {item.get('outcome', 'N/A')}\n\n"

        md += "## Contributing Factors\n\n"
        for factor in post_mortem.get("contributing_factors", []):
            md += f"- {factor}\n"
        md += "\n"

        md += "## Follow-up Action Items\n\n"
        for item in post_mortem.get("follow_up_items", []):
            md += f"- [ ] {item}\n"
        md += "\n"

        retrospective = post_mortem.get("prediction_retrospective")
        if retrospective:
            md += "## Prediction Retrospective\n\n"

            if retrospective.get("most_predictive_signals"):
                md += "### Most Predictive Signals\n\n"
                for signal in retrospective["most_predictive_signals"]:
                    md += f"- {signal}\n"
                md += "\n"

            if retrospective.get("most_accurate_prediction"):
                md += f"### Most Accurate Prediction\n\n{retrospective['most_accurate_prediction']}\n\n"

            if retrospective.get("earlier_prediction_opportunity"):
                md += f"### Earlier Prediction Opportunity\n\n{retrospective['earlier_prediction_opportunity']}\n\n"

            if retrospective.get("missed_signals"):
                md += "### Missed Signals\n\n"
                for signal in retrospective["missed_signals"]:
                    md += f"- {signal}\n"
                md += "\n"

        return md
