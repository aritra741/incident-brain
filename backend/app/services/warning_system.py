from typing import Optional, List, Dict, Set
from uuid import UUID
import logging
from difflib import SequenceMatcher

from ..config import settings
from ..models.event import Event, EventType, EventSource
from .incident_memory import IncidentMemory
from .gemini_service import GeminiService

logger = logging.getLogger(__name__)

CO_RESPONDER_THRESHOLD = 2


class WarningSystem:
    def __init__(self, memory: IncidentMemory, gemini: GeminiService):
        self.memory = memory
        self.gemini = gemini
        self._matched_incident_ids: Dict[str, List[UUID]] = {}
        self._warning_history: Dict[str, List[Dict]] = {}
        self._co_responder_fired: Set[str] = set()

    async def check_for_warnings(
        self, new_event: Event, all_events: List[Event]
    ) -> Optional[Dict]:
        if new_event.type != EventType.ACTION:
            return None

        if not new_event.embedding:
            logger.warning("Skipping warning check: action has no embedding")
            return None

        similar_actions = await self.memory.search_similar_events(
            embedding=new_event.embedding,
            event_type=EventType.ACTION,
            threshold=settings.WARNING_SIMILARITY_THRESHOLD,
            limit=5,
        )

        if not similar_actions:
            similar_actions = await self._text_fallback_similar_actions(new_event)

        for match in similar_actions:
            match_incident_id = UUID(match["incident_id"])
            if match_incident_id == new_event.incident_id:
                continue

            match_event_id = UUID(match["event_id"])
            past_action = await self.memory.get_event_by_id(match_event_id)
            if not past_action:
                continue

            outcome = await self._find_outcome_in_db(past_action.id, past_action.incident_id)
            if outcome and self._is_negative_outcome(outcome):
                similarity = float(match.get("similarity", 0.0))

                warning_message = await self.gemini.generate_warning(
                    current_action=new_event.content,
                    past_action=past_action.content,
                    past_outcome=outcome,
                    similarity=similarity,
                )

                incident_id_str = str(new_event.incident_id)
                if incident_id_str not in self._matched_incident_ids:
                    self._matched_incident_ids[incident_id_str] = []
                if incident_id_str not in self._warning_history:
                    self._warning_history[incident_id_str] = []
                if past_action.incident_id not in self._matched_incident_ids[incident_id_str]:
                    self._matched_incident_ids[incident_id_str].append(past_action.incident_id)

                matched_incident = await self.memory.get_incident(past_action.incident_id)
                warning_entry = {
                    "action": new_event.content,
                    "actor": new_event.actor,
                    "matched_action": past_action.content,
                    "matched_incident_id": str(past_action.incident_id),
                    "matched_incident_title": matched_incident.title if matched_incident else "unknown",
                    "historical_outcome": outcome,
                    "similarity_score": similarity,
                }
                self._warning_history[incident_id_str].append(warning_entry)

                new_warning_count = await self.memory.increment_warning_count(new_event.incident_id)

                warning_result = {
                    "event_id": str(new_event.id),
                    "action_content": new_event.content,
                    "similar_event_id": str(past_action.id),
                    "similar_action_content": past_action.content,
                    "past_outcome": outcome,
                    "similarity_score": similarity,
                    "warning_message": warning_message,
                    "timestamp": new_event.timestamp.isoformat(),
                    "warning_count": new_warning_count,
                    "co_responder_triggered": False,
                }

                if (
                    new_warning_count == CO_RESPONDER_THRESHOLD
                    and incident_id_str not in self._co_responder_fired
                ):
                    co_responder = await self._trigger_co_responder(
                        new_event.incident_id, all_events
                    )
                    if co_responder:
                        self._co_responder_fired.add(incident_id_str)
                        warning_result["co_responder_triggered"] = True
                        warning_result["co_responder"] = co_responder

                return warning_result

        return None

    async def _text_fallback_similar_actions(self, new_event: Event) -> List[Dict]:
        result = (
            self.memory.client.table("events")
            .select("id,incident_id,content,type,timestamp")
            .eq("type", EventType.ACTION.value)
            .neq("incident_id", str(new_event.incident_id))
            .order("timestamp", desc=True)
            .limit(120)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return []

        matches = []
        for row in rows:
            similarity = self._text_similarity(new_event.content, row.get("content", ""))
            if similarity < 0.55:
                continue
            matches.append(
                {
                    "event_id": row["id"],
                    "incident_id": row["incident_id"],
                    "similarity": similarity,
                }
            )

        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches[:5]

    async def _trigger_co_responder(
        self, incident_id: UUID, current_events: List[Event]
    ) -> Optional[Dict]:
        try:
            incident_id_str = str(incident_id)
            matched_ids = self._matched_incident_ids.get(incident_id_str, [])
            warning_history = self._warning_history.get(incident_id_str, [])

            if not matched_ids or not warning_history:
                logger.warning("No matched incident IDs for co-responder analysis")
                return None

            historical_context = await self.memory.get_historical_resolution_paths(matched_ids)
            historical_by_id = {h["incident_id"]: h for h in historical_context}

            failed_actions = []
            for item in warning_history:
                matched_incident = historical_by_id.get(item["matched_incident_id"], {})
                failed_actions.append({
                    "action": item["action"],
                    "actor": item["actor"],
                    "matched_action": item["matched_action"],
                    "outcome": item["historical_outcome"],
                    "incident_title": item["matched_incident_title"],
                    "similarity_score": item["similarity_score"],
                    "resolution_time_minutes": matched_incident.get("resolution_time_minutes"),
                })

            current_timeline = [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "type": e.type.value,
                    "actor": e.actor,
                    "content": e.content,
                }
                for e in current_events
            ]

            analysis = await self.gemini.generate_co_responder_analysis(
                current_timeline=current_timeline,
                failed_actions=failed_actions,
                historical_context=historical_context,
            )

            intervention_content = self._format_co_responder_content(analysis)

            intervention_event = await self.memory.create_event({
                "incident_id": incident_id,
                "source": EventSource.AGENT.value,
                "actor": "Incident Brain",
                "type": EventType.INTERVENTION.value,
                "content": intervention_content,
                "embedding": None,
                "confidence": analysis.get("confidence", 0.7),
            })

            return {
                "event_id": str(intervention_event.id),
                "event": intervention_event.model_dump(mode="json"),
                "analysis": analysis,
                "message": self._format_slack_message(analysis, len(historical_context)),
                "timestamp": intervention_event.timestamp.isoformat(),
                "similar_incident_count": len(historical_context),
            }

        except Exception as e:
            logger.error(f"Co-responder analysis failed: {e}", exc_info=True)
            return None

    def _format_co_responder_content(self, analysis: Dict) -> str:
        parts = [
            f"Pattern: {analysis.get('pattern_summary', 'N/A')}",
            f"Failed approaches: {', '.join(analysis.get('failed_approaches', []))}",
            f"Recommendations: {', '.join(analysis.get('recommended_next_steps', []))}",
            f"Precedent: {analysis.get('historical_precedent', 'N/A')}",
            f"Confidence: {analysis.get('confidence', 0.0)}",
        ]
        return " | ".join(parts)

    def _format_slack_message(self, analysis: Dict, similar_count: int) -> str:
        pattern = analysis.get("pattern_summary", "Unable to determine")
        failed = analysis.get("failed_approaches", [])
        recommendations = analysis.get("recommended_next_steps", [])
        precedent = analysis.get("historical_precedent", "No historical data available")
        confidence = analysis.get("confidence", 0.0)

        failed_lines = "\n".join(f"• {f}" for f in failed) if failed else "• None recorded"
        rec_lines = "\n".join(f"{i+1}. {r}" for i, r in enumerate(recommendations)) if recommendations else "1. Escalate to senior engineer"

        message = (
            f"*Incident Brain* — Pattern detected\n\n"
            f"I've been watching this incident. Here's what I'm seeing:\n\n"
            f"*Pattern:* {pattern}\n\n"
            f"*What's been tried (and hasn't worked):*\n{failed_lines}\n\n"
            f"*Suggested next steps based on {similar_count} similar past incidents:*\n{rec_lines}\n\n"
            f"*Precedent:* {precedent}\n\n"
            f"Confidence: {confidence:.0%}"
        )
        return message

    def _find_outcome_after_action(self, action: Event, events: List[Event]) -> Optional[str]:
        action_found = False
        for event in events:
            if event.id == action.id:
                action_found = True
                continue
            if action_found and event.type == EventType.OUTCOME:
                return event.content
        return None

    async def _find_outcome_in_db(self, action_id: UUID, incident_id: UUID) -> Optional[str]:
        try:
            events = await self.memory.get_events(incident_id)
            action = next((e for e in events if e.id == action_id), None)
            if not action:
                return None
            return self._find_outcome_after_action(action, events)
        except Exception:
            return None

    def _is_negative_outcome(self, outcome: str) -> bool:
        negative = [
            "failed", "failure", "error", "rolled back", "rollback",
            "no effect", "no change", "worsened", "degraded", "crashed",
            "timeout", "rejected", "unsuccessful", "broken", "didn't work",
            "still down", "still failing", "made it worse", "didn't fix",
            "no improvement", "same issue", "still broken", "not working",
            "unresponsive", "hung", "stuck", "leaking",
        ]
        outcome_lower = outcome.lower()
        return any(word in outcome_lower for word in negative)

    def _text_similarity(self, a: str, b: str) -> float:
        a_lower = (a or "").lower().strip()
        b_lower = (b or "").lower().strip()
        if not a_lower or not b_lower:
            return 0.0

        seq_ratio = SequenceMatcher(None, a_lower, b_lower).ratio()

        a_words = set(a_lower.split())
        b_words = set(b_lower.split())
        if not a_words or not b_words:
            return seq_ratio

        overlap = len(a_words & b_words) / len(a_words | b_words)
        return (0.5 * seq_ratio) + (0.5 * overlap)

    def reset_incident_state(self, incident_id: UUID) -> None:
        incident_id_str = str(incident_id)
        self._matched_incident_ids.pop(incident_id_str, None)
        self._warning_history.pop(incident_id_str, None)
        self._co_responder_fired.discard(incident_id_str)
