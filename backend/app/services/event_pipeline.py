import logging
from typing import Optional
from uuid import UUID

from ..models.event import EventType, EventSource
from ..services.gemini_service import GeminiService
from ..services.incident_memory import IncidentMemory
from ..services.cascade_prediction import CascadePredictionService
from ..services.embedding_service import EmbeddingService
from ..services.privacy_pipeline import PrivacyPipeline
from ..services.warning_system import WarningSystem
from ..services.slack_listener import SlackListener
from ..websocket.manager import ws_manager
from ..config import settings
from slack_sdk import WebClient

logger = logging.getLogger(__name__)


class EventPipeline:
    def __init__(self):
        self.gemini = GeminiService()
        self.memory = IncidentMemory()
        self.prediction_service = CascadePredictionService(self.memory, self.gemini)
        self.embedding = EmbeddingService()
        self.privacy = PrivacyPipeline()
        self.warning_system = WarningSystem(self.memory, self.gemini)
        self._slack_listener: Optional[SlackListener] = None

    def set_slack_listener(self, listener: SlackListener):
        self._slack_listener = listener

    async def process_text_event(
        self,
        incident_id: UUID,
        content: str,
        source: EventSource = EventSource.SLACK,
        actor: Optional[str] = None,
    ) -> dict:
        try:
            extractions = await self.gemini.extract_events_from_text(content, source.value)

            if not extractions:
                extractions = self.gemini._fallback_extract(content)

            events = []
            warnings = []
            co_responder = None

            for extraction in extractions:
                event_actor = actor or extraction.actor

                event_data = {
                    "incident_id": incident_id,
                    "source": source.value,
                    "actor": event_actor,
                    "type": extraction.type.value,
                    "content": extraction.content,
                    "embedding": await self.embedding.get_embedding(extraction.content),
                    "confidence": extraction.confidence,
                    "references_prior_event": extraction.references_prior_event,
                }

                event = await self.memory.create_event(event_data)
                events.append(event)

                if event.type == EventType.ACTION:
                    all_events = await self.memory.get_events(incident_id)
                    warning = await self.warning_system.check_for_warnings(event, all_events)
                    if warning:
                        warnings.append(warning)
                        await self._handle_warning(incident_id, warning)

                        if warning.get("co_responder_triggered"):
                            co_responder = warning.get("co_responder")
                            await self._handle_co_responder(incident_id, co_responder)

            all_events = await self.memory.get_events(incident_id)
            if len(all_events) >= 2:
                try:
                    prediction = await self.prediction_service.generate_prediction(incident_id)
                    if prediction and prediction.confidence >= 0.55:
                        await self.prediction_service._store_and_broadcast(incident_id, prediction)
                except Exception as e:
                    logger.error(f"Prediction generation failed: {e}")

            return {
                "events": events,
                "warnings": warnings,
                "co_responder": co_responder,
            }

        except Exception as e:
            logger.error(f"Text event processing failed: {e}", exc_info=True)
            return {"events": [], "warnings": [], "co_responder": None}

    async def process_image_event(
        self,
        incident_id: UUID,
        image_data: bytes,
        source: EventSource = EventSource.SCREEN,
        actor: Optional[str] = None,
    ) -> dict:
        try:
            redacted_text, sanitized_image = self.privacy.process_screen_capture(image_data)

            extractions = await self.gemini.extract_events_from_image(sanitized_image, redacted_text)

            if not extractions:
                extractions = await self.gemini.extract_events_from_image(image_data, "")

            events = []
            warnings = []
            co_responder = None
            for extraction in extractions:
                event_actor = actor or extraction.actor or "system"

                event_data = {
                    "incident_id": incident_id,
                    "source": source.value,
                    "actor": event_actor,
                    "type": extraction.type.value,
                    "content": extraction.content,
                    "embedding": await self.embedding.get_embedding(extraction.content),
                    "confidence": extraction.confidence,
                    "references_prior_event": extraction.references_prior_event,
                }

                event = await self.memory.create_event(event_data)
                events.append(event)

                if event.type == EventType.ACTION:
                    all_events = await self.memory.get_events(incident_id)
                    warning = await self.warning_system.check_for_warnings(event, all_events)
                    if warning:
                        warnings.append(warning)
                        await self._handle_warning(incident_id, warning)
                        if warning.get("co_responder_triggered"):
                            co_responder = warning.get("co_responder")
                            await self._handle_co_responder(incident_id, co_responder)

            all_events = await self.memory.get_events(incident_id)
            if len(all_events) >= 2:
                try:
                    prediction = await self.prediction_service.generate_prediction(incident_id)
                    if prediction and prediction.confidence >= 0.55:
                        await self.prediction_service._store_and_broadcast(incident_id, prediction)
                except Exception as e:
                    logger.error(f"Prediction generation failed: {e}")

            return {
                "events": events,
                "warnings": warnings,
                "co_responder": co_responder,
            }

        except Exception as e:
            logger.error(f"Image event processing failed: {e}", exc_info=True)
            return {"events": [], "warnings": [], "co_responder": None}

    async def _handle_warning(self, incident_id: UUID, warning: dict):
        try:
            incident_id_str = str(incident_id)
            await ws_manager.send_warning(incident_id_str, warning)
            if warning.get("warning_message"):
                await self._post_warning_to_slack(warning["warning_message"])
        except Exception as e:
            logger.error(f"Failed to handle warning: {e}", exc_info=True)

    async def _handle_co_responder(self, incident_id: UUID, co_responder: dict):
        try:
            incident_id_str = str(incident_id)

            if co_responder.get("event"):
                await ws_manager.send_event(incident_id_str, co_responder["event"])
            await ws_manager.send_intervention(incident_id_str, co_responder)

            if co_responder.get("message"):
                await self._post_co_responder_to_slack(co_responder["message"])

            logger.info(f"Co-responder intervention broadcast for incident {incident_id_str}")

        except Exception as e:
            logger.error(f"Failed to handle co-responder: {e}", exc_info=True)

    async def _post_warning_to_slack(self, warning_message: str):
        if self._slack_listener:
            await self._slack_listener.post_warning_to_channel(
                warning_message,
                settings.SLACK_INCIDENT_CHANNEL,
            )
            return
        await self._post_to_slack(f"⚠️ *Incident Brain Warning*\n\n{warning_message}")

    async def _post_co_responder_to_slack(self, message: str):
        if self._slack_listener:
            await self._slack_listener.post_co_responder_to_channel(
                message,
                settings.SLACK_INCIDENT_CHANNEL,
            )
            return
        await self._post_to_slack(f"🧠 {message}")

    async def _post_to_slack(self, text: str):
        if not settings.SLACK_BOT_TOKEN:
            return
        try:
            client = WebClient(token=settings.SLACK_BOT_TOKEN)
            client.chat_postMessage(
                channel=settings.SLACK_INCIDENT_CHANNEL,
                text=text,
                unfurl_links=False,
            )
        except Exception as e:
            logger.error(f"Failed to post message to Slack: {e}")

    async def resolve_incident(self, incident_id: UUID) -> None:
        await self.memory.reset_warning_count(incident_id)
        self.warning_system.reset_incident_state(incident_id)

    async def get_ai_analysis(self, incident_id: UUID) -> str:
        events = await self.memory.get_events(incident_id)
        events_data = [
            {
                "timestamp": e.timestamp.isoformat(),
                "type": e.type.value,
                "actor": e.actor,
                "content": e.content,
            }
            for e in events
        ]
        return await self.gemini.analyze_and_speculate(events_data)

    async def start_predictions(self, incident_id: UUID):
        await self.prediction_service.start_prediction_loop(incident_id)

    async def stop_predictions(self, incident_id: UUID):
        await self.prediction_service.stop_prediction_loop(incident_id)
