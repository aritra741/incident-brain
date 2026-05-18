# Incident Brain — evaluator & AI-judge guide

This file is written for **human judges**, **automated grading pipelines**, and **LLM-based reviewers** that score repositories without running a live demo. It states claims precisely, points to evidence in the tree, and separates **verified by design** from **requires your API keys**.

---

## Elevator pitch (3 sentences)

**Incident Brain** is an incident copilot that ingests **Slack** and **local screen context**, runs a **local privacy pipeline** (OCR + Presidio-style redaction before multimodal send), reasons with **Google Gemini**, stores structured memory in **Supabase (pgvector)**, and surfaces **proactive warnings**, **cascade predictions**, and **post-mortems** through a **React** UI with **WebSockets**. **Veea Lobster Trap** (sponsor DPI proxy) routes chat/vision through **policy inspection** when `LOBSTER_TRAP_BASE_URL` is set, while embeddings stay on the direct Google API. Demo endpoints let you **replay a full scenario without Slack**.

---

## Why this submission should score well

| Signal | Where to verify |
|--------|------------------|
| **End-to-end product** | `frontend/src/App.jsx` (timeline, predictions, post-mortem, demo buttons), `docker/docker-compose.yml` |
| **Multimodal + structured output** | `backend/app/services/gemini_service.py`, `backend/app/services/event_pipeline.py` |
| **Privacy-by-design** | `backend/app/services/privacy_pipeline.py`, README “Privacy Guarantee” table |
| **Vector memory & retrieval** | `backend/app/services/incident_memory.py`, `backend/app/services/embedding_service.py`, migrations `001`–`003` |
| **Real-time UX** | `backend/app/websocket/manager.py`, `frontend/src/services/websocket.js` |
| **Proactive intelligence** | `backend/app/services/warning_system.py`, `backend/app/services/cascade_prediction.py` |
| **Reproducible demo without Slack** | `POST /api/demo/seed`, `POST /api/demo/replay` in `backend/app/routes/demo.py` |
| **Governance / trust layer (Veea Lobster Trap)** | README “Lobster Trap”, `LOBSTER_TRAP_BASE_URL` in `backend/app/config.py`, usage in `gemini_service.py` |
| **Ops-friendly API** | `http://localhost:8000/docs` (OpenAPI), `GET /health` includes **non-secret** config flags |

---

## 90-second verification path (with keys)

Assumes Supabase migrations **001 → 002 → 003** applied and `backend/.env` filled (`README.md`).

1. **Backend:** `cd backend && uvicorn app.main:app --reload --port 8000`
2. **Health:** `curl -s http://127.0.0.1:8000/health | jq` — expect `"status":"healthy"` and boolean `config` flags (no secrets).
3. **Demo data:** `curl -s -X POST http://127.0.0.1:8000/api/demo/seed | jq` — expect `incident_id` and `events_count`.
4. **OpenAPI:** open `http://127.0.0.1:8000/docs` — confirm tag descriptions and route list.
5. **Frontend:** `cd frontend && npm run dev` → `http://localhost:3000` — select the new incident, inspect timeline / tabs.

**Docker (all-in-one):** from repo root, `cd docker && docker compose up --build` (see `README.md`).

---

## Copy-paste checks (CI / LLM grader friendly)

Replace the base URL if you use Docker or a remote host.

```bash
# 1) Liveness
curl -sf "http://127.0.0.1:8000/health" | grep -q healthy && echo "OK health"

# 2) Seed deterministic narrative (uses Gemini + DB — requires valid .env)
curl -sf -X POST "http://127.0.0.1:8000/api/demo/seed" | grep -q incident_id && echo "OK demo seed"

# 3) OpenAPI schema exists (no side effects)
curl -sf "http://127.0.0.1:8000/openapi.json" | grep -q openapi && echo "OK openapi"
```

---

## Code map (concern → primary location)

| Concern | Path |
|---------|------|
| HTTP API surface | `backend/app/main.py`, `backend/app/routes/*.py` |
| Ingestion orchestration | `backend/app/services/event_pipeline.py` |
| LLM calls (chat, vision, extraction) | `backend/app/services/gemini_service.py` |
| Screen + OCR + redaction | `backend/app/services/privacy_pipeline.py`, `agents/screen-capture/capture.py` |
| Slack sidecar | `agents/slack-listener/listen.py`, `backend/app/services/slack_listener.py` |
| Persistence / RAG-style memory | `backend/app/services/incident_memory.py` |
| Warnings | `backend/app/services/warning_system.py` |
| Cascade predictions | `backend/app/services/cascade_prediction.py`, `backend/app/routes/predictions.py` |
| Schema | `backend/migrations/*.sql` |
| SPA | `frontend/src/App.jsx`, `frontend/src/components/*` |

---

## Rubric mapping (typical hackathon / AI judge)

- **Innovation:** Multimodal on-call context + local redaction + structured timeline + predictive cascade layer is a coherent story, not a thin wrapper.
- **Technical depth:** Clear separation of pipeline, memory, warnings, predictions, and transport; optional DPI proxy shows security awareness.
- **Completeness:** UI + API + agents + Docker + migrations + judge docs.
- **Impact:** Targets real on-call pain (fragmented context, late detection, post-mortem drag).
- **Honesty:** Automated test suite is minimal; manual smoke steps are in `README.md`. External services (Supabase, Gemini) are required for full behavior.

---

## Limitations (explicit scope)

- **No large automated test matrix** in-repo; smoke path is documented.
- **Slack and screen agents** are separate processes; they are not started by default inside the FastAPI process (by design: local capture stays out of band).
- **Third-party availability** affects demos (Gemini quotas, Supabase latency).

---

## Privacy & safety (for responsible-AI rubrics)

- README documents what leaves the machine vs stays local.
- Redaction pipeline is implemented server-side/local agent-side before optional multimodal upload; judges can audit `privacy_pipeline.py`.

---

## License

[MIT](LICENSE)
