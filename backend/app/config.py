"""Runtime configuration. Every secret comes from the environment."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'nigraan.db'}"
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 12 * 60
    demo_mode: bool = True
    allowed_origin: str = "http://localhost:3000"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_timeout_s: float = 20.0

    # The company's "today". The synthetic history ends the day before.
    as_of_date: date = date(2026, 10, 12)
    seed: int = 42
    auto_seed: bool = True

    models_dir: Path = REPO_DIR / "models"
    demo_week_dir: Path = REPO_DIR / "demo_week"
    data_out_dir: Path = BACKEND_DIR / "data_out"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origin.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Render/Heroku style URLs
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
