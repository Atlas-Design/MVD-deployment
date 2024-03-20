from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query
from starlette.responses import JSONResponse

from google.cloud import storage

from database import Job

client_storage = storage.Client()

router = APIRouter()


@dataclass
class CheckStatusConfig:
    job_id: str = Query()


@router.get("/check_status")
def check_status(
        config: CheckStatusConfig = Depends(),
):
    job_id = config.job_id

    job = Job.select().where(
        Job.id == job_id
    ).first()

    return JSONResponse(
        content={
            "status": job.status,
            "progress": [job.progress, job.total]
        }
    )
