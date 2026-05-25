from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # RabbitMQ
    RABBITMQ_URL: str
    RABBITMQ_EXCHANGE: str = "events"
    RABBITMQ_QUEUE: str = "bet-maker.events"
    RABBITMQ_DLX_EXCHANGE: str = "events.dlx"
    RABBITMQ_DLQ: str = "bet-maker.events.dlq"
    RABBITMQ_ROUTING_KEY: str = "event.status_changed"
    RABBITMQ_PREFETCH_COUNT: int = 50
    PUBLISH_RETRY_INTERVAL_SECONDS: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()