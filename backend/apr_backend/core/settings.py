from functools import lru_cache

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APR_", env_file=".env", extra="ignore")

    app_name: str = "AI PR Review Assistant"
    environment: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    database_url: str = "sqlite:///./apr_backend.db"
    review_queue_name: str = "review"


@lru_cache
def get_settings() -> Settings:
    return Settings()
