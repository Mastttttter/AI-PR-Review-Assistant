from functools import lru_cache

from pydantic import Field, RedisDsn, SecretStr
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

    api_key: str | None = Field(default=None)
    llm_api_key: SecretStr | None = Field(default=None)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout: int = Field(default=60, ge=1)
    llm_mock_enabled: bool = False
    llm_provider: str = "openai"

    openai_base_uri: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_base_uri: str = "https://api.anthropic.com"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"


@lru_cache
def get_settings() -> Settings:
    return Settings()
