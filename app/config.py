from pydantic_settings import BaseSettings, SettingsConfigDict # Added SettingsConfigDict
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    database_url: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    app_name: str = "First-Order"
    debug: bool = False

    news_api_key: str = ""

    # MODERN FIXED BLOCK (Replaces class Config)
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="UTF-8",
        extra="ignore"
        )

@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore
