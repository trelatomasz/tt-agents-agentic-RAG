from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    project_id: str = "local"
    location: str = "global"
    model_id: str = "gemini-2.5-flash"
    catalog_path: str = "data/catalog.json"
    catalog_gcs_uri: str | None = None
    catalog_max_age_seconds: int = 86400
    request_timeout_seconds: float = 8.0
    max_context_parts: int = 4
    retrieval_min_score: float = 2.0
    use_vertex: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
