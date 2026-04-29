from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    ENVIRONMENT: str = "development"
    # Empty default so we can require it in non-dev at boot time.
    SECRET_KEY: str = ""
    LOG_LEVEL: str = "INFO"

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "openspeakers"
    POSTGRES_USER: str = "openspeakers"
    POSTGRES_PASSWORD: str = "openspeakers"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis / Celery
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    # If explicitly set, use as-is. Otherwise, constructed from REDIS_HOST/PORT below.
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    @model_validator(mode="after")
    def _build_celery_urls(self) -> Settings:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        base = f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}"
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = f"{base}/0"
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = f"{base}/1"
        return self

    # GPU
    GPU_DEVICE_ID: int = 0
    GPU_DEVICE: str = "cuda"

    # File paths
    AUDIO_OUTPUT_DIR: str = "./audio_output"
    MODEL_CACHE_DIR: str = "./model_cache"

    # Models
    ENABLED_MODELS: str = ""  # comma-separated; empty = all registered models
    VIBEVOICE_MODEL_PATH: str = "microsoft/VibeVoice-Realtime-0.5B"
    VIBEVOICE_1P5B_MODEL_PATH: str = "microsoft/VibeVoice-1.5B"
    FISH_SPEECH_MODEL_PATH: str = "fishaudio/s2-pro"
    QWEN3_TTS_MODEL_PATH: str = "Qwen/Qwen3-TTS"
    KOKORO_MODEL_PATH: str = "hexgrad/Kokoro-82M"

    # Reference-audio transcription (faster-whisper, runs in worker-asr).
    # Default model is the 140 MB ``base`` checkpoint — fast on CPU and
    # accurate enough for a transcript the user can edit. ``small`` /
    # ``medium`` / ``large-v3-turbo`` are valid drop-ins for higher accuracy.
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    # Master kill switch for the ASR pipeline. When ``False``, voice profile
    # uploads no longer dispatch the auto-transcribe task and rely on manual
    # entry only.
    AUTO_TRANSCRIBE_REFERENCES: bool = True
    # F5-TTS-specific opt-out: when ``False`` the F5 model will refuse to
    # invoke its built-in Whisper fallback for missing transcripts (avoids a
    # surprise 600 MB download in the worker container).
    F5_TTS_AUTO_TRANSCRIBE: bool = True

    # CORS — comma-separated origins. The defaults cover the standard dev setup
    # (Vite on 5173, docker-compose mapping to 5200, and the docker network).
    CORS_ALLOW_ORIGINS: str = (
        "http://localhost:5173,http://localhost:5200,http://localhost:3000,http://frontend:5173"
    )

    @property
    def enabled_model_list(self) -> list[str]:
        if not self.ENABLED_MODELS:
            return []
        return [m.strip() for m in self.ENABLED_MODELS.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _secret_key_required_in_non_dev(self) -> Settings:
        """Production / staging must supply SECRET_KEY via env. Dev gets an
        ephemeral random key so local runs never leak a default secret."""
        if not self.SECRET_KEY:
            if self.ENVIRONMENT.lower() == "development":
                self.SECRET_KEY = secrets.token_urlsafe(32)
            else:
                raise ValueError(
                    "SECRET_KEY must be set via environment variable when "
                    f"ENVIRONMENT={self.ENVIRONMENT!r} (only 'development' auto-generates)"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
