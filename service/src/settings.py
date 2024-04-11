import enum
import logging
import os

from pydantic_settings import BaseSettings


class Environment(str, enum.Enum):
    MAIN = 'main'
    DEV = 'dev'


class Settings(BaseSettings):
    ENV: Environment = Environment.DEV

    TMP_DIR: str = '/tmp'

    SD_DATA_STORAGE_BUCKET_NAME: str = 'sd-experiments'

    RABBITMQ_URL: str = 'amqp://admin:admin@localhost:5672'
    REDIS_URL: str = 'redis://localhost:6379'

    @property
    def DATABASE_URL(self):
        if self.ENV == Environment.DEV:
            return "database.db"
        elif self.ENV == Environment.MAIN:
            return "/data/database.db"
        else:
            raise Exception("Invalid env")


settings = Settings()

logging.basicConfig(
    level=logging.INFO if settings.ENV == Environment.MAIN else logging.DEBUG
)
