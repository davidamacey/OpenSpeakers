from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change_this_in_production"
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
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # GPU
    GPU_DEVICE_ID: int = 0
    GPU_DEVICE: str = "cuda"

    # File paths
    AUDIO_OUTPUT_DIR: str = "./audio_output"
    MODEL_CACHE_DIR: str = "./models"

    # Models
    ENABLED_MODELS: str = ""  # comma-separated; empty = all registered models
    VIBEVOICE_MODEL_PATH: str = "microsoft/VibeVoice-Realtime-0.5B"
    VIBEVOICE_1P5B_MODEL_PATH: str = "microsoft/VibeVoice-1.5B"
    FISH_SPEECH_MODEL_PATH: str = "fishaudio/fish-speech-1.5"
    QWEN3_TTS_MODEL_PATH: str = "Qwen/Qwen3-TTS"
    KOKORO_MODEL_PATH: str = "hexgrad/Kokoro-82M"

    @property
    def enabled_model_list(self) -> list[str]:
        if not self.ENABLED_MODELS:
            return []
        return [m.strip() for m in self.ENABLED_MODELS.split(",") if m.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
