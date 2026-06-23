from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    app_name: str = "First-Order"
    debug: bool = False

    news_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "UTF-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore
