# Incident Brain

An autonomous incident response agent that ingests data from Slack and the engineer's screen, processes them through a privacy filter, reasons over them using Gemini, and maintains a structured incident timeline that powers real-time warnings and an auto-generated post-mortem.

> **For hackathon judges, automated reviewers, and LLM graders:** start with **[`JUDGING.md`](JUDGING.md)** (scoring hooks, copy-paste checks, code map). For a structural walkthrough, see **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**. With the backend running, **`/docs`** (Swagger) and **`/redoc`** are the live API reference; **`GET /health`** returns non-secret integration flags for quick verification.

## Sponsors

**Google** provides the **Gemini** API used for multimodal reasoning. **Veea** provides **[Lobster Trap](https://github.com/veeainc/lobstertrap)**, the DPI policy proxy that inspects chat and vision traffic against YAML policy when you run it and set `LOBSTER_TRAP_BASE_URL` (see below).

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Slack API     │     │  Screen Capture │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │              ┌────────▼────────┐
         │              │ Privacy Pipeline │
         │              │ (OCR + Presidio) │
         │              └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────┐
│  Google Gemini + Veea Lobster Trap (DPI) │
│  DPI on chat; embeddings direct API   │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│        Incident Memory                  │
│        (Supabase pgvector)              │
└────────────────┬────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐  ┌──────────────┐
│   Warning    │  │  Post-Mortem │
│   System     │  │   Engine     │
└──────────────┘  └──────────────┘
        │                 │
        └────────┬────────┘
                 ▼
┌─────────────────────────────────────────┐
│          React Frontend                 │
│   (Timeline + Post-Mortem View)         │
└─────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Multimodal reasoning | **Google** Gemini API; **Veea** [Lobster Trap](https://github.com/veeainc/lobstertrap) DPI proxy for chat/vision when configured |
| PII redaction | Microsoft Presidio |
| OCR | Tesseract / pytesseract |
| Vector storage | Supabase pgvector |
| Backend | FastAPI (Python) |
| Frontend | React + Vite |
| Slack integration | Slack Bolt SDK |
| Real-time | WebSocket |
| Deployment | Docker / Vultr |

## Privacy Guarantee

| Data | Leaves the machine? |
|---|---|
| Raw terminal screenshot | No |
| OCR extracted text (pre-redaction) | No |
| Credentials, API keys | No |
| Customer PII | No |
| Redacted/sanitized image | Yes (Gemini only) |
| Slack messages | Yes (Gemini, per Slack agreements) |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Supabase account
- Google Gemini API key
- Tesseract OCR
- Slack App (optional)

### 1. Clone and Setup

```bash
git clone <repo-url>
cd incident-brain
```

### 2. Setup Supabase

1. Create a new Supabase project (enable **pgvector** if prompted or per Supabase docs).
2. In the Supabase SQL editor, run each migration **in order** (paste the full file contents and execute):

   | Order | File |
   |---|---|
   | 1 | `backend/migrations/001_initial_schema.sql` |
   | 2 | `backend/migrations/002_predictions_table.sql` |
   | 3 | `backend/migrations/003_co_responder.sql` |

   Skipping or reordering migrations will cause schema errors at runtime.

### Veea Lobster Trap (DPI trust layer)

[Veea Lobster Trap](https://github.com/veeainc/lobstertrap) (sponsor-provided) sits between Incident Brain and the Google Gemini **OpenAI-compatible** endpoint so every chat request and model reply can be inspected against YAML policy (prompt injection, exfiltration, credentials, and more). Incident Brain sends a declared agent id and intent for declared-vs-detected auditing via `_lobstertrap` metadata.

1. Install or build Lobster Trap from the upstream repo (see their README).
2. Run the proxy with Google as the backend (paths are forwarded as-is, including `/v1beta/openai/...`):

```bash
./lobstertrap serve --listen :8080 --backend https://generativelanguage.googleapis.com
```

3. Point the backend at the OpenAI-compat prefix on the proxy (no trailing slash required):

```bash
export LOBSTER_TRAP_BASE_URL=http://127.0.0.1:8080/v1beta/openai
```

Use the same `GEMINI_API_KEY` as for direct Gemini access. The dashboard is at `http://127.0.0.1:8080/_lobstertrap/` while the proxy runs.

**Note:** Text embeddings still use `google-generativeai` directly so the `gemini-embedding-exp-03-07` model is unchanged; all **chat** and **vision** completions go through Lobster Trap when `LOBSTER_TRAP_BASE_URL` is set.

### 3. Backend Setup

```bash
cd backend
cp .env.example .env
# Edit .env with your API keys

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements/base.txt

# Install Tesseract OCR
# macOS: brew install tesseract
# Ubuntu: sudo apt install tesseract-ocr

uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 5. Open the App

Visit `http://localhost:3000`

## Docker Deployment

Paths in `docker/docker-compose.yml` are relative to the `docker/` folder. From the repo root:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

cd docker
docker compose up --build
```

The UI is at `http://localhost:3000` (nginx on port 3000). The API is at `http://localhost:8000` (including interactive docs at `http://localhost:8000/docs`).

## Easiest split deploy: Railway (API) + Vercel (UI)

1. **Railway** — Create a service from this GitHub repo. Set **Root Directory** to `backend`. Use **Dockerfile** build (`backend/railway.toml` sets this). **Do not** set a custom start command to `start.sh` (that script is local-only). Networking domain port: **8080**. The Dockerfile listens on **`PORT`** so Railway routing works.
2. **Railway variables** — Copy values from `backend/.env.example` (Gemini, Supabase, Slack, etc.). Add **`CORS_ORIGINS`** as a JSON array including your Vercel URL, e.g. `["https://your-app.vercel.app"]` (add preview URLs if you use them).
3. **Vercel** — New project from the same repo. **Root Directory**: `frontend`. Build: `npm run build`, output: `dist`. Add **`VITE_API_BASE_URL`** = your Railway public API origin (e.g. `https://something.up.railway.app`, no trailing slash). See `frontend/.env.example`.
4. Smoke: open `https://…railway.app/health` and your Vercel URL; confirm the app loads and API calls succeed in the browser network tab.

## Running Agents

### Screen Capture Agent (Local)

```bash
pip install -r backend/requirements/screen-capture.txt
```

```bash
# Interval mode (captures every 30s)
CAPTURE_MODE=interval python agents/screen-capture/capture.py

# Keystroke mode (captures on terminal activity)
CAPTURE_MODE=keystroke python agents/screen-capture/capture.py
```

### Slack Listener

```bash
# Set DEFAULT_INCIDENT_ID in environment
DEFAULT_INCIDENT_ID=<your-incident-uuid> python agents/slack-listener/listen.py
```

## API Endpoints

Interactive OpenAPI docs: `http://localhost:8000/docs` (when the backend is running).

### Incidents
- `POST /api/incidents/` - Create incident
- `GET /api/incidents/` - List incidents
- `GET /api/incidents/{id}` - Get incident
- `PATCH /api/incidents/{id}` - Update incident
- `POST /api/incidents/{id}/resolve` - Resolve incident
- `DELETE /api/incidents/{id}` - Delete incident

### Events
- `POST /api/events/text` - Create text event
- `POST /api/events/image` - Create image event
- `GET /api/events/incident/{id}` - Get events for incident
- `GET /api/events/incident/{id}/analysis` - Analysis for incident events

### Predictions (cascade / risk)
- `GET /api/predictions/incident/{id}` - List predictions for an incident
- `GET /api/predictions/incident/{id}/accuracy` - Accuracy summary
- `POST /api/predictions/generate/{id}` - Generate predictions
- `POST /api/predictions/{prediction_id}/outcome` - Record outcome

### Post-Mortems
- `POST /api/postmortems/generate/{id}` - Generate post-mortem
- `GET /api/postmortems/incident/{id}` - Get post-mortem
- `GET /api/postmortems/incident/{id}/markdown` - Export as markdown

### Demo (local / hackathon demos without live Slack)
- `POST /api/demo/seed` - Seed demo data
- `POST /api/demo/seed-warnings` - Seed warning-related demo data
- `POST /api/demo/replay` - Replay demo scenario

### WebSocket
- `ws://localhost:8000/ws/{client_id}` - Real-time updates

## Manual smoke test (no automated suite yet)

With backend and frontend running, and Supabase migrations applied:

1. Open `http://localhost:3000` and confirm the app loads.
2. `GET http://localhost:8000/health` returns JSON with `"status": "healthy"`, `version`, and boolean `config` flags (Supabase, Gemini, Slack tokens, Lobster Trap)—**no secrets**.
3. Create an incident via `POST /api/incidents/` or the UI, then add a text event via `POST /api/events/text` or the UI; confirm it appears in the timeline.
4. Optional: call `POST /api/demo/seed` then explore the UI and WebSocket-driven updates.

## Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `LOBSTER_TRAP_BASE_URL` | **Veea** Lobster Trap OpenAI-compat base URL (e.g. `http://127.0.0.1:8080/v1beta/openai`); omit only if you are calling Gemini directly without the proxy |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (server-side operations) |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |
| `SLACK_APP_TOKEN` | Slack app-level token |
| `SLACK_SIGNING_SECRET` | Slack signing secret |
| `SLACK_INCIDENT_CHANNEL` | Slack channel ID to monitor |
| `SCREEN_CAPTURE_ENABLED` | Enable screen capture (true/false) |
| `SCREEN_CAPTURE_INTERVAL` | Capture interval in seconds |
| `WARNING_SIMILARITY_THRESHOLD` | Similarity threshold for warnings (0-1) |

## License

[MIT](LICENSE)
