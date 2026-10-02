from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://reaper:local-only@localhost:5432/reaper"
    checkpoint_url: str = (
        "postgresql://reaper:local-only@localhost:5432/reaper?options=-csearch_path%3Dcheckpoints"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    runner_url: str = "http://localhost:8090"
    runner_token: str = Field(min_length=32)
    session_secret: str = Field(min_length=32)
    app_origin: str = "http://localhost:8080"
    artifact_root: str = "/data/artifacts"
    sandbox_global_slots: int = Field(default=1, ge=1, le=8)
    queued_runs_per_workspace: int = Field(default=10, ge=1, le=100)
    publication_enabled: bool = False
    python_image: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    node_image: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    def model_post_init(self, context: object) -> None:
        if self.publication_enabled:
            raise ValueError("Publication is not available in M0; keep PUBLICATION_ENABLED=false")
