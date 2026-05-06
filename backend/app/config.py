from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql+asyncpg://ims:ims@localhost:5432/ims"
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "ims_signals"
    redis_url: str = "redis://localhost:6379/0"

    ingestion_rate_per_minute: int = 60_000
    signal_queue_max: int = 100_000
    debounce_window_sec: int = 10

    log_metrics_interval_sec: int = 5


settings = Settings()
