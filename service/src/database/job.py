import enum

from .db import  BaseModel
from peewee import CharField, IntegerField, TextField


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Job(BaseModel):
    id = CharField(primary_key=True, unique=True)

    status = CharField(default=JobStatus.QUEUED)

    batch_job_name = CharField(default=None, null=True)

    progress = IntegerField(default=0)
    total = IntegerField()

    steps = TextField()
