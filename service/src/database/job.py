import enum
import datetime

from peewee import CharField, IntegerField, TextField, DateTimeField

from .db import BaseModel


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Job(BaseModel):
    id = CharField(primary_key=True, unique=True)

    created_at = DateTimeField(default=datetime.datetime.utcnow, index=True)

    status = CharField(default=JobStatus.QUEUED, index=True)

    celery_job_ids = TextField(default="[]", null=False)

    progress = IntegerField(default=0)
    total = IntegerField()

    current_step = TextField(default=None, null=True)

    steps = TextField()
    payload = TextField()

