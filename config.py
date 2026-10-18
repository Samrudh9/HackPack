"""Central environment-based configuration for HackPack."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "HackPack"
    APP_VERSION: str = APP_VERSION

    # --- AI provider -------------------------------------------------------
    # Local-first default. No hosted API key is required for basic use.
    # Run `ollama pull llama3.1:8b` (or a smaller model, see README) first.
    LLM_MODEL: str = "ollama/llama3.1"
    LLM_API_BASE: str = "http://localhost:11434"
    LLM_TEMPERATURE: float = 0.2
    LLM_TIMEOUT_SECONDS: int = 120
    # Total attempts = 1 initial + LLM_MAX_RETRIES (capped at 2 by the client).
    LLM_MAX_RETRIES: int = 2
    # When true (default) a deterministic template pitch is produced if the
    # model is unreachable or keeps returning invalid structured output.
    LLM_FALLBACK_ENABLED: bool = True

    # --- GitHub analysis ---------------------------------------------------
    GITHUB_TOKEN: str = ""
    MAX_FILE_SIZE_BYTES: int = 100_000
    MAX_FILES_TO_ANALYZE: int = 50
    MAX_README_LENGTH: int = 30_000
    MAX_SOURCE_EXCERPTS: int = 12
    MAX_TOTAL_EXCERPT_CHARS: int = 55_000
    MAX_TEST_EXCERPTS: int = 4
    # Wall-clock budget for one repository analysis pass.
    ANALYSIS_TIME_BUDGET_SECONDS: int = 60

    # --- API ---------------------------------------------------------------
    # Comma-separated exact origins, e.g. "http://localhost:5173,https://myapp.lovable.app"
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8501"
    REQUEST_TIMEOUT_SECONDS: int = 180
    MAX_REQUEST_BODY_BYTES: int = 2_000_000

    # --- Output ------------------------------------------------------------
    OUTPUT_DIR: str = "generated"
    # When true, generated ZIPs are also written under OUTPUT_DIR for debugging.
    SAVE_GENERATED_ZIPS: bool = False

    DEFAULT_PITCH_DURATION_MINUTES: int = 3
    DEFAULT_SLIDE_COUNT: int = 6

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOW_ORIGINS.split(",") if origin.strip()]

    @field_validator("CORS_ALLOW_ORIGINS")
    @classmethod
    def reject_wildcard_origins(cls, value: str) -> str:
        for origin in [part.strip() for part in value.split(",") if part.strip()]:
            if "*" in origin:
                raise ValueError(
                    "Wildcard CORS origins are not allowed. List exact deployed origins instead."
                )
        return value


settings = Settings()
