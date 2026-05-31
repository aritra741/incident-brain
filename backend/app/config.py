from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "Incident Brain"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"

    # Optional: Veea Lobster Trap DPI proxy. Use the OpenAI-compat prefix on the proxy,
    # e.g. http://127.0.0.1:8080/v1beta/openai  (see README). Embeddings still use google-generativeai.
    LOBSTER_TRAP_BASE_URL: Optional[str] = None

    SLACK_BOT_TOKEN: str = ""
    SLACK_APP_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    SLACK_INCIDENT_CHANNEL: str = "incidents"

    WARNING_SIMILARITY_THRESHOLD: float = 0.85
    EMBEDDING_DIMENSION: int = 768

    SCREEN_CAPTURE_INTERVAL: int = 30
    SCREEN_CAPTURE_ENABLED: bool = False

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://incident-brain.vercel.app",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
