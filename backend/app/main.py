from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .config import settings
from .routes import incidents, events, postmortems, websocket, demo, predictions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DESCRIPTION = """
**Incident Brain** ingests on-call context from **Slack** and **screen capture**, runs a **local privacy pipeline** before multimodal reasoning, and stores a structured **incident timeline** in **Supabase (pgvector)**.

It powers **proactive warnings**, **cascade failure predictions**, **post-mortems**, and a **real-time React UI** (WebSockets).

- **Evaluator quick path:** see repository `JUDGING.md`.
- **Demo without Slack:** `POST /api/demo/seed`, `POST /api/demo/replay`.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "incidents",
        "description": "Create, list, update, resolve, and delete incidents (containers for timeline data).",
    },
    {
        "name": "events",
        "description": "Ingest text and redacted image events; retrieve timeline and aggregated analysis.",
    },
    {
        "name": "postmortems",
        "description": "Generate and export AI-assisted post-mortems for a resolved or active incident.",
    },
    {
        "name": "predictions",
        "description": "Cascade-style failure predictions with optional outcome tracking for calibration.",
    },
    {
        "name": "demo",
        "description": "Deterministic demo seeding and replay for judges and local testing without Slack.",
    },
    {
        "name": "websocket",
        "description": "Subscribe to incident-scoped real-time updates (not shown as REST in this schema).",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Incident Brain...")
    yield
    logger.info("Shutting down Incident Brain...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents.router)
app.include_router(events.router)
app.include_router(postmortems.router)
app.include_router(predictions.router)
app.include_router(websocket.router)
app.include_router(demo.router)


@app.get("/health", summary="Liveness and integration readiness (no secrets)")
async def health_check():
    """Returns process health plus boolean flags only—safe for monitors and automated graders."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "config": {
            "supabase": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY),
            "gemini": bool(settings.GEMINI_API_KEY),
            "slack_tokens": bool(settings.SLACK_BOT_TOKEN and settings.SLACK_APP_TOKEN),
            "lobster_trap_proxy": bool(settings.LOBSTER_TRAP_BASE_URL),
        },
    }
