import asyncio
import base64
import google.generativeai as genai
from typing import List, Dict, Optional, Any
from PIL import Image
from io import BytesIO
import json
import logging
import re

import httpx

from ..config import settings
from ..models.event import GeminiExtraction, EventType

logger = logging.getLogger(__name__)

LT_AGENT_ID = "incident-brain"


class LobsterTrapDenied(Exception):
    """Raised when Lobster Trap blocks a request (policy DENY, quarantine, human review, etc.)."""

    def __init__(self, message: str = "", metadata: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.denied_message = message
        self.metadata = metadata or {}


class GeminiService:
    def __init__(self):
        raw_lt = (settings.LOBSTER_TRAP_BASE_URL or "").strip()
        self._lt_base = raw_lt.rstrip("/")
        self._use_lt = bool(self._lt_base)
        self._quota_warning_logged = False

        if self._use_lt:
            self.text_model = None
            self.vision_model = None
            logger.info("LLM traffic routed through Lobster Trap (%s)", self._lt_base)
        else:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.text_model = self._init_model(settings.GEMINI_MODEL)
            self.vision_model = self._init_model(settings.GEMINI_VISION_MODEL)

    def _init_model(self, model_name: str):
        try:
            return genai.GenerativeModel(model_name)
        except Exception:
            return genai.GenerativeModel("gemini-2.5-flash")

    def _log_lobstertrap_metadata(self, lt: Optional[Dict[str, Any]]) -> None:
        if not lt:
            return
        ingress = lt.get("ingress") or {}
        detected = ingress.get("detected") or {}
        logger.info(
            "lobstertrap verdict=%s risk=%s intent=%s mismatches=%s",
            lt.get("verdict"),
            detected.get("risk_score"),
            detected.get("intent_category"),
            ingress.get("mismatches"),
        )

    async def _lt_chat(self, messages: list, model: str, declared_intent: str) -> str:
        url = f"{self._lt_base}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "_lobstertrap": {
                "declared_intent": declared_intent,
                "agent_id": LT_AGENT_ID,
            },
        }
        headers = {
            "Authorization": f"Bearer {settings.GEMINI_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error(
                "Lobster Trap / LLM HTTP %s: %s",
                resp.status_code,
                (resp.text or "")[:800],
            )
            raise RuntimeError(f"Lobster Trap upstream HTTP {resp.status_code}")

        data = resp.json()
        self._log_lobstertrap_metadata(data.get("_lobstertrap"))
        lt = data.get("_lobstertrap") or {}
        verdict = lt.get("verdict")
        if verdict and verdict != "ALLOW":
            msg = ""
            try:
                ch0 = data["choices"][0]
                msg = (ch0.get("message") or {}).get("content") or ""
            except (KeyError, IndexError, TypeError):
                pass
            raise LobsterTrapDenied(msg or "[LOBSTER TRAP] Request blocked by policy.", lt)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error("Invalid chat completion payload: %r", data)
            raise RuntimeError("Invalid chat completion response") from e
        return (content or "").strip()

    async def _complete_text(self, prompt: str, declared_intent: str) -> str:
        if self._use_lt:
            return await self._lt_chat(
                [{"role": "user", "content": prompt}],
                settings.GEMINI_MODEL,
                declared_intent,
            )
        response = await asyncio.to_thread(self.text_model.generate_content, prompt)
        return (response.text or "").strip()

    async def _complete_vision(self, prompt: str, image_bytes: bytes, declared_intent: str) -> str:
        if self._use_lt:
            b64 = base64.standard_b64encode(image_bytes).decode("ascii")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ]
            return await self._lt_chat(messages, settings.GEMINI_VISION_MODEL, declared_intent)

        def _run():
            image = Image.open(BytesIO(image_bytes))
            return self.vision_model.generate_content([prompt, image]).text

        return (await asyncio.to_thread(_run) or "").strip()

    async def extract_events_from_text(self, text: str, source: str = "slack") -> List[GeminiExtraction]:
        prompt = (
            'You are an incident response analysis AI. Analyze this message from an incident response Slack channel and extract structured events.\n\n'
            f'Message: "{text}"\n\n'
            'Classify the message into one or more events. Each event must be one of:\n'
            '- action: Someone took a concrete step (restarted, deployed, rolled back, checked, modified)\n'
            '- hypothesis: Someone proposed a theory about what might be wrong\n'
            '- observation: Someone reported what they see (errors, metrics, logs, status)\n'
            '- outcome: The result of a previous action (success, failure, partial, no effect)\n\n'
            'Return a JSON array. Be specific and extract the technical details.\n'
            'Example: [{"type":"observation","actor":"sarah","content":"Payment API returning 500 errors at 12% rate","confidence":0.95}]\n\n'
            'If the message contains multiple distinct pieces of information, extract multiple events.\n'
            'If it is ambiguous, still extract your best guess with lower confidence.\n\n'
            'Return ONLY the JSON array, no markdown fences.'
        )

        try:
            response_text = await self._complete_text(prompt, "communication")
            return self._parse_extractions(response_text)
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked Slack text extraction: %s", e.metadata)
            return []
        except Exception as e:
            if self._is_quota_or_billing_error(e):
                self._log_quota_warning_once(e)
            else:
                logger.error(f"Gemini text extraction failed: {e}")
            return self._fallback_extract(text)

    async def extract_events_from_image(self, image_bytes: bytes, context: str = "") -> List[GeminiExtraction]:
        prompt = f"""You are an incident response analysis AI. Analyze this terminal screenshot or monitoring dashboard image and extract observable events.

{f"Context: {context}" if context else ""}

Extract everything you can see:
- Error messages, stack traces, exception types
- System commands that were run and their output
- Metrics, percentages, thresholds being breached
- Status indicators (healthy/unhealthy/degraded)
- Resource utilization (CPU, memory, connections, disk)
- Any alerts or warnings visible

For each observation, return:
- type: "observation" for what you see, "action" if a command was clearly run
- actor: "system" or infer from context
- content: detailed technical description of what you observe
- confidence: 0.0-1.0

Return a JSON array. Be thorough - extract every piece of useful information visible.
Return ONLY the JSON array, no markdown fences."""

        try:
            response_text = await self._complete_vision(prompt, image_bytes, "data_access")
            return self._parse_extractions(response_text)
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked image extraction: %s", e.metadata)
            return []
        except Exception as e:
            if self._is_quota_or_billing_error(e):
                self._log_quota_warning_once(e)
            else:
                logger.error(f"Gemini image extraction failed: {e}")
            return []

    async def generate_warning(
        self,
        current_action: str,
        past_action: str,
        past_outcome: str,
        similarity: float,
    ) -> str:
        prompt = f"""You are an incident response AI warning system. An engineer is about to take an action that is very similar to a past action that had a NEGATIVE outcome.

CURRENT ACTION: "{current_action}"
PAST ACTION: "{past_action}"
PAST OUTCOME: "{past_outcome}"
SIMILARITY: {similarity:.0%}

Write a brief, urgent warning (2-3 sentences max) that:
1. States clearly that this was tried before and failed
2. Summarizes what happened last time
3. Suggests an alternative or asks them to reconsider

Be direct and helpful, not alarmist. Use technical language."""

        try:
            return await self._complete_text(prompt, "general")
        except LobsterTrapDenied:
            return f"WARNING: Similar action '{past_action}' was attempted before and resulted in: {past_outcome}"
        except Exception as e:
            logger.error(f"Warning generation failed: {e}")
            return f"WARNING: Similar action '{past_action}' was attempted before and resulted in: {past_outcome}"

    async def predict_cascade(
        self,
        events: List[Dict],
        slack_messages: List[str],
        screenshot_descriptions: List[str],
    ) -> Dict:
        events_text = "\n".join(
            f"[{e.get('timestamp', 'N/A')}] ({e['type']}) {e['actor']}: {e['content']}"
            for e in events
        )
        slack_text = "\n".join(f"- {msg}" for msg in slack_messages) if slack_messages else "No Slack messages yet."
        screenshots_text = "\n".join(f"- {desc}" for desc in screenshot_descriptions) if screenshot_descriptions else "No screenshots yet."

        prompt = (
            'You are an incident response agent watching a live incident.\n\n'
            f'Events so far:\n{events_text}\n\n'
            'Reason forward: what fails next? Be concise — one short sentence.\n'
            '2-3 causal signals max.\n'
            'Suggested action must be concrete and stack-aware with exact checks/commands (SQL/CLI/API), not generic wording.\n'
            'Bad example: "Verify server status". Good example: "Check RDS connection pool: SHOW STATUS LIKE ''Threads_connected''; if >85% max_connections, restart leaking workers and cap pool_size=20."\n\n'
            'Return ONLY JSON:\n'
            '{\n'
            '  "prediction": "One sentence",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "time_to_failure_minutes": int,\n'
            '  "causal_chain": [\n'
            '    {"signal": "short signal", "source": "slack|screenshot|log", "timestamp": "HH:MM:SS"}\n'
            '  ],\n'
            '  "suggested_action": "1-2 lines with exact command/check and threshold"\n'
            '}\n'
            'NO markdown fences.'
        )

        try:
            response_text = await self._complete_text(prompt, "general")
            parsed = self._parse_json(response_text)
            parsed["suggested_action"] = self._harden_suggested_action(
                parsed.get("suggested_action", ""),
                events,
            )
            return parsed
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked cascade prediction: %s", e.metadata)
            return {
                "prediction": "Prediction blocked by security policy",
                "confidence": 0.0,
                "time_to_failure_minutes": None,
                "causal_chain": [],
                "suggested_action": self._harden_suggested_action("", events),
            }
        except Exception as e:
            logger.error(f"Cascade prediction failed: {e}")
            return {
                "prediction": "Unable to generate prediction",
                "confidence": 0.0,
                "time_to_failure_minutes": None,
                "causal_chain": [],
                "suggested_action": self._harden_suggested_action("", events),
            }

    async def generate_prediction_retrospective(
        self,
        predictions: List[Dict],
        events: List[Dict],
    ) -> Dict:
        predictions_text = "\n".join(
            f"- Predicted: {p['predicted_failure']} (confidence: {p['confidence']}, "
            f"time estimate: {p.get('time_to_failure_minutes', 'N/A')}min, "
            f"outcome: {p.get('outcome', 'unresolved')})"
            for p in predictions
        ) if predictions else "No predictions were made."

        events_text = "\n".join(
            f"[{e.get('timestamp', 'N/A')}] ({e['type']}) {e['actor']}: {e['content']}"
            for e in events
        )

        prompt = (
            'You are analyzing prediction accuracy after an incident.\n\n'
            f'PREDICTIONS MADE:\n{predictions_text}\n\n'
            f'ACTUAL EVENTS:\n{events_text}\n\n'
            'Analyze the predictions and return a JSON object:\n'
            '{\n'
            '  "most_predictive_signals": ["signal 1", "signal 2"],\n'
            '  "most_accurate_prediction": "description and why",\n'
            '  "earlier_prediction_opportunity": "what could have been predicted sooner",\n'
            '  "missed_signals": ["signal 1", "signal 2"]\n'
            '}\n\n'
            'Return ONLY the JSON object, no markdown fences.'
        )

        try:
            response_text = await self._complete_text(prompt, "general")
            return self._parse_json(response_text)
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked prediction retrospective: %s", e.metadata)
            return {
                "most_predictive_signals": [],
                "most_accurate_prediction": "Blocked by security policy",
                "earlier_prediction_opportunity": "Unable to determine",
                "missed_signals": [],
            }
        except Exception as e:
            logger.error(f"Prediction retrospective failed: {e}")
            return {
                "most_predictive_signals": [],
                "most_accurate_prediction": "Unable to analyze",
                "earlier_prediction_opportunity": "Unable to determine",
                "missed_signals": [],
            }

    async def generate_post_mortem(self, events: List[Dict], warnings: List[Dict], duration_minutes: float, predictions: Optional[List[Dict]] = None) -> Dict:
        events_text = "\n".join(
            f"[{e['timestamp']}] ({e['type']}) {e['actor']}: {e['content']}"
            for e in events
        )
        warnings_text = "\n".join(
            f"- WARNING: '{w['action']}' was flagged as similar to a past failed action (similarity: {w.get('similarity', 'high')})"
            for w in warnings
        ) if warnings else "No warnings were triggered during this incident."

        predictions_text = ""
        if predictions:
            predictions_text = "\n\nPREDICTIONS MADE DURING INCIDENT:\n" + "\n".join(
                f"- {p['predicted_failure']} (confidence: {p['confidence']}, "
                f"outcome: {p.get('outcome', 'unresolved')})"
                for p in predictions
            )

        prompt = (
            'You are a senior site reliability engineer writing a post-mortem report. Analyze this incident data and produce a thorough, insightful post-mortem.\n\n'
            f'INCIDENT EVENT LOG:\n{events_text}\n\n'
            f'WARNINGS TRIGGERED:\n{warnings_text}\n'
            f'{predictions_text}\n\n'
            f'DURATION: {duration_minutes:.0f} minutes\n\n'
            'Write a comprehensive post-mortem. Be analytical and insightful. Speculate intelligently about root causes based on the evidence. '
            'Do not just repeat what happened; analyze WHY it happened and what patterns you see.\n\n'
            'Return a JSON object with these exact fields:\n'
            '{\n'
            '  "summary": "2-3 sentence executive summary that captures the essence of the incident and its impact",\n'
            '  "timeline": [\n'
            '    {"time": "HH:MM", "event": "concise description"}\n'
            '  ],\n'
            '  "root_cause_hypothesis": "Your best technical analysis of the root cause. Reference specific evidence from the event log.",\n'
            '  "actions_and_outcomes": [\n'
            '    {"action": "what was tried", "outcome": "what happened and why"}\n'
            '  ],\n'
            '  "contributing_factors": [\n'
            '    "Systemic or process factors that enabled or worsened the incident"\n'
            '  ],\n'
            '  "follow_up_items": [\n'
            '    "Specific, actionable items to prevent recurrence. Be concrete, not generic."\n'
            '  ]\n'
            '}\n\n'
            'Return ONLY the JSON object, no markdown fences.'
        )

        try:
            response_text = await self._complete_text(prompt, "general")
            return self._parse_json(response_text)
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked post-mortem generation: %s", e.metadata)
            return {
                "summary": "Post-mortem generation blocked by security policy. Manual review required.",
                "timeline": [],
                "root_cause_hypothesis": "Unable to determine automatically.",
                "actions_and_outcomes": [],
                "contributing_factors": [],
                "follow_up_items": ["Review incident manually"],
            }
        except Exception as e:
            logger.error(f"Post-mortem generation failed: {e}")
            return {
                "summary": "Post-mortem generation failed. Manual review required.",
                "timeline": [],
                "root_cause_hypothesis": "Unable to determine automatically.",
                "actions_and_outcomes": [],
                "contributing_factors": [],
                "follow_up_items": ["Review incident manually"],
            }

    async def analyze_and_speculate(self, events: List[Dict]) -> str:
        events_text = "\n".join(
            f"[{e.get('timestamp', 'N/A')}] ({e['type']}) {e['actor']}: {e['content']}"
            for e in events
        )

        prompt = f"""You are an incident response AI copilot. Based on the current incident events, provide real-time analysis and speculation.

EVENTS SO FAR:
{events_text}

Provide a brief analysis (3-5 sentences) that:
1. Summarizes the current state of the incident
2. Speculates on the most likely root cause based on available evidence
3. Suggests the next diagnostic step or action to take

Be specific and reference the actual events. Be helpful and actionable."""

        try:
            return await self._complete_text(prompt, "general")
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked live analysis: %s", e.metadata)
            return "Analysis blocked by security policy for this request."
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return "Unable to generate analysis at this time."

    async def generate_co_responder_analysis(
        self,
        current_timeline: List[Dict],
        failed_actions: List[Dict],
        historical_context: List[Dict],
    ) -> Dict:
        timeline_text = "\n".join(
            f"[{e.get('timestamp', 'N/A')}] ({e['type']}) {e['actor']}: {e['content']}"
            for e in current_timeline
        )

        failed_text = "\n".join(
            f"- Action: {a['action']}\n  Matched from incident: {a.get('incident_title', 'unknown')}\n  Historical outcome: {a['outcome']}"
            for a in failed_actions
        )

        historical_text = ""
        for h in historical_context:
            historical_text += f"\n--- Incident: {h['title']} ---\n"
            historical_text += f"Resolution time: {h.get('resolution_time_minutes', 'N/A')} minutes\n"
            if h.get("resolution_events"):
                historical_text += "Resolution path (what eventually worked):\n"
                for evt in h["resolution_events"]:
                    historical_text += f"  [{evt['timestamp']}] ({evt['type']}) {evt['actor']}: {evt['content']}\n"
            historical_text += f"Full timeline:\n"
            for evt in h.get("events", []):
                historical_text += f"  [{evt['timestamp']}] ({evt['type']}) {evt['actor']}: {evt['content']}\n"

        prompt = f"""You are an incident response assistant with access to historical incident data.

CURRENT INCIDENT TIMELINE:
{timeline_text}

FAILED ACTIONS THIS INCIDENT:
{failed_text}

HISTORICAL CONTEXT:
{historical_text}

Based on this, the team appears to be stuck. Identify:
1. What pattern you're observing (specific, not generic)
2. What approaches have already failed and why
3. What 2-3 concrete alternative approaches are most likely to work, based on historical resolutions of similar incidents
4. Which engineer or team resolved similar incidents in the past (if available from actor fields)

Be direct and specific. No hedging. Write as if you are a senior engineer who has seen this before.

Return ONLY JSON:
{{
  "pattern_summary": "string",
  "failed_approaches": ["string"],
  "recommended_next_steps": ["string"],
  "historical_precedent": "string",
  "confidence": 0.0-1.0
}}"""

        try:
            response_text = await self._complete_text(prompt, "general")
            return self._parse_json(response_text)
        except LobsterTrapDenied as e:
            logger.warning("Lobster Trap blocked co-responder analysis: %s", e.metadata)
            return {
                "pattern_summary": "Analysis blocked by security policy",
                "failed_approaches": [a["action"] for a in failed_actions[:3]],
                "recommended_next_steps": ["Review incident history manually", "Escalate to senior engineer"],
                "historical_precedent": "Unable to retrieve historical context",
                "confidence": 0.3,
            }
        except Exception as e:
            logger.error(f"Co-responder analysis failed: {e}")
            return {
                "pattern_summary": "Unable to determine pattern automatically",
                "failed_approaches": [a["action"] for a in failed_actions[:3]],
                "recommended_next_steps": ["Review incident history manually", "Escalate to senior engineer"],
                "historical_precedent": "Unable to retrieve historical context",
                "confidence": 0.3,
            }

    def _parse_extractions(self, text: str) -> List[GeminiExtraction]:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning(f"Could not parse Gemini response: {text[:200]}")
                return []

        if not isinstance(data, list):
            data = [data]

        extracted = []
        for item in data:
            try:
                item.setdefault("type", "observation")
                item.setdefault("actor", "unknown")
                item.setdefault("confidence", 0.85)
                item.setdefault("references_prior_event", None)
                extracted.append(GeminiExtraction(**item))
            except Exception as e:
                logger.warning(f"Failed to parse extraction: {item}, error: {e}")

        return extracted

    def _parse_json(self, text: str) -> Dict:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise

    def _fallback_extract(self, text: str) -> List[GeminiExtraction]:
        text_lower = text.lower()

        if any(w in text_lower for w in ["restart", "deploy", "rollback", "kill", "scale", "pushed", "merged", "reverted"]):
            event_type = EventType.ACTION
        elif any(w in text_lower for w in ["maybe", "could be", "might be", "probably", "suspect", "think", "hypothesis"]):
            event_type = EventType.HYPOTHESIS
        elif any(w in text_lower for w in ["seeing", "looks like", "appears", "shows", "monitoring", "alert"]):
            event_type = EventType.OBSERVATION
        elif any(w in text_lower for w in ["fixed", "resolved", "recovered", "worked", "failed", "didn't work", "no change"]):
            event_type = EventType.OUTCOME
        else:
            event_type = EventType.OBSERVATION

        return [GeminiExtraction(
            type=event_type,
            actor="unknown",
            content=text,
            confidence=0.6,
            references_prior_event=None,
        )]

    def _is_quota_or_billing_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return any(token in message for token in ["429", "quota", "depleted", "billing", "prepayment"])

    def _log_quota_warning_once(self, error: Exception) -> None:
        if self._quota_warning_logged:
            return
        self._quota_warning_logged = True
        logger.warning(
            "Gemini API quota/billing unavailable (%s). Falling back to heuristic extraction.",
            str(error),
        )

    def _harden_suggested_action(self, suggestion: str, events: List[Dict]) -> str:
        suggestion = (suggestion or "").strip()
        merged = " ".join((e.get("content") or "").lower() for e in events[-30:])

        generic_markers = [
            "verify", "assess impact", "investigate further", "monitor closely",
            "check system health", "immediately verify", "ensure stability",
        ]
        is_generic = (not suggestion) or any(marker in suggestion.lower() for marker in generic_markers)

        if ("connection pool" in merged or "threads_connected" in merged or "db connection" in merged or "pool exhausted" in merged):
            concrete = "Check DB pool now: SHOW STATUS LIKE 'Threads_connected'; if >85% of max_connections, identify leaking workers and restart payment pods after lowering pool_size (e.g. 20)."
            return concrete if is_generic else suggestion

        if "payment" in merged and ("500" in merged or "latency" in merged):
            concrete = "Validate payment dependency health and rollback gate: run a canary transaction, check error-rate by endpoint, and rollback if 5xx stays >2% for 5 min."
            return concrete if is_generic else suggestion

        if "webhook" in merged or "stripe" in merged:
            concrete = "Inspect webhook handler DB session cleanup path; run a burst test and confirm active DB sessions return to baseline within 60s."
            return concrete if is_generic else suggestion

        if is_generic:
            return "Run a focused dependency check on the failing path (DB/cache/upstream), capture one concrete metric+threshold, and execute rollback if the threshold is breached for 5 minutes."
        return suggestion
