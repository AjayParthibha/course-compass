from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{REPO_ROOT / 'backend' / 'coursecompass.db'}"
    data_dir: Path = REPO_ROOT / "data"
    snapshot: str | None = None  # defaults to the newest folder in data/snapshots
    current_term: str = "FA26"

    openai_api_key: str | None = None
    advisor_model: str = "gpt-5.6-terra"
    advisor_effort: str = "medium"
    max_tool_calls: int = 8

    static_dir: Path = REPO_ROOT / "web" / "dist"
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
