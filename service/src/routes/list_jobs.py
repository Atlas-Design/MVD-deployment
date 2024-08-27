from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query
from google.cloud import storage
from starlette.responses import JSONResponse

from database import Job, JobStatus

client_storage = storage.Client()

router = APIRouter()


@dataclass
class ListJobsConfig:
    all: bool = Query(default=False)


@router.get("/list_jobs")
def list_jobs(
    config: ListJobsConfig = Depends(),
):
    query_builder = Job.select().order_by(Job.created_at.desc())

    if not config.all:
        query_builder = query_builder.where(
            Job.status.not_in([
                JobStatus.FAILED,
                JobStatus.SUCCEEDED,
                JobStatus.CANCELLED
            ])
        )

    return JSONResponse(
        content=[
            {
                "job_id": job.id,
                "status": job.status,
                "created_at": job.created_at.isoformat(),
                "progress": [job.progress, job.total],
            }
            for job in query_builder
        ]
    )
