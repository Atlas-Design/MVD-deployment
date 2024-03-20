import enum
import os

from pydantic_settings import BaseSettings


class Environment(str, enum.Enum):
    MAIN = 'main'
    DEV = 'dev'


class Settings(BaseSettings):
    ENV: Environment = Environment.DEV

    TMP_DIR: str = '/tmp'

    SD_DATA_STORAGE_BUCKET_NAME: str = 'sd-experiments'

    @property
    def DATABASE_URL(self):
        if self.ENV == Environment.DEV:
            return "database.db"
        elif self.ENV == Environment.MAIN:
            return "/data/database.db"
        else:
            raise Exception("Invalid env")


settings = Settings()
