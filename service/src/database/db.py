from peewee import SqliteDatabase, Model

from settings import settings

db = SqliteDatabase(settings.DATABASE_URL)


class BaseModel(Model):
    class Meta:
        database = db
