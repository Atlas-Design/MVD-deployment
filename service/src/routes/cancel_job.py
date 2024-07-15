from dataclasses import dataclass

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Query
from google.cloud import storage
from starlette.responses import JSONResponse

import queues.cpu
import queues.gpu
from database import Job

client_storage = storage.Client()

router = APIRouter()


@dataclass
class CancelJobConfig:
    job_id: str = Query()


@router.get("/cancel_job")
def cancel_job(
        config: CancelJobConfig = Depends(),
):
    job_id = config.job_id

    job = Job.select().where(
        Job.id == job_id
    ).first()

    job.status = "CANCELLED"
    job.save()

    if job.current_step.startswith("gpu"):
        queue = queues.gpu.queue
    else:
        queue = queues.cpu.queue

    AsyncResult(id=job.celery_job_ids[-1], app=queue).revoke(terminate=True)

    return JSONResponse(
        content={
            "status": job.status,
            "progress": [job.progress, job.total],
        }
    )
