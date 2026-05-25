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
    # Postgres
    POSTGRES_DB: str = "store_db"
    POSTGRES_USER: str = "store_user"
    POSTGRES_PASSWORD: str = "7209dac7318d32776ed2ca2630d5f188"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: str = "5432"

    LINE_PROVIDER_URL: str = "http://line-provider:8001"
    LINE_PROVIDER_TIMEOUT_SECONDS: float = 5.0
    RECONCILE_INTERVAL_SECONDS: float = 60.0

    # TEST DB
    TEST_POSTGRES_DB: str
    TEST_POSTGRES_USER: str
    TEST_POSTGRES_PASSWORD: str
    TEST_POSTGRES_PORT: int
    TEST_POSTGRES_HOST: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def TEST_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.TEST_POSTGRES_USER}:{self.TEST_POSTGRES_PASSWORD}@"
            f"{self.TEST_POSTGRES_HOST}:{self.TEST_POSTGRES_PORT}/{self.TEST_POSTGRES_DB}"
        )


settings = Settings()
