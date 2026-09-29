from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql://ccvie:ccvie@localhost:5432/ccvie"
    database_read_url: str | None = None
    db_pool_min: int = 1
    db_pool_max: int = 10
    migrations_dir: Path = REPO_ROOT / "db" / "migrations"

    # --- Cache / queue ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Security ---
    # Dev mode verifies HS256 tokens signed with auth_dev_secret. Production verifies
    # asymmetric tokens against auth_jwks_url.
    auth_dev_mode: bool = False
    auth_dev_secret: SecretStr = SecretStr("")
    auth_issuer: str = "ccvie-dev"
    auth_audience: str = "ccvie-api"
    auth_jwks_url: str | None = None
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    # --- Embeddings (Layer 1) ---
    # embedding_dimension must equal the vector() width in db/migrations; /readyz checks it.
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # --- LLM (Layer 3) ---
    llm_provider: str = "anthropic"
    llm_model_name: str = ""

    # --- Router thresholds (Layer 2) ---
    router_entity_count_threshold: int = 3
    router_word_count_low: int = 50
    router_word_count_high: int = 150
    router_taxonomy_coverage_high: float = 0.80
    router_taxonomy_coverage_low: float = 0.40

    # --- Ingestion ---
    ingestion_cadence_minutes: int = 60

    # --- Observability ---
    log_level: str = "INFO"
    otel_service_name: str = "ccvie-api"
    otel_exporter_otlp_endpoint: str | None = None

    # --- Eval / CI gate thresholds (Layer 5) ---
    eval_lead_time_regression_max_days_drop: int = 1
    eval_citation_accuracy_min: float = 0.95
    eval_router_accuracy_min: float = 0.85


settings = Settings()
