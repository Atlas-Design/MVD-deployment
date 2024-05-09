import json
import logging
import datetime

import celery.result

import queues.cpu
import queues.gpu
import queues.base

from database import db, Job, JobStatus

from apscheduler.schedulers.blocking import BlockingScheduler

db.connect()

scheduler = BlockingScheduler()

logging.getLogger("apscheduler.scheduler").setLevel(logging.INFO)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

logger = logging.getLogger("sd_cloud.scheduler")


def _start_next_step(job: Job):
    steps = json.loads(job.steps)
    step_to_run = steps[job.progress]

    job.current_step = step_to_run
    payload = json.loads(job.payload)

    logger.debug(f"Running step {step_to_run}")

    match step_to_run:
        case 'cpu.prestage_0':
            job_result: celery.result.AsyncResult = queues.cpu.prestage_0.delay(payload)
        case 'cpu.stage_0':
            job_result: celery.result.AsyncResult = queues.cpu.stage_0.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_1':
            job_result: celery.result.AsyncResult = queues.cpu.stage_1.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_3':
            job_result: celery.result.AsyncResult = queues.cpu.stage_3.delay({"job_id": payload["job_id"]})
        # case 'cpu.stage_5':
        #     job_result: celery.result.AsyncResult = queues.cpu.stage_5.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_7':
            job_result: celery.result.AsyncResult = queues.cpu.stage_7.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_9':
            job_result: celery.result.AsyncResult = queues.cpu.stage_9.delay({"job_id": payload["job_id"]})
        case 'gpu.stage_2':
            job_result: celery.result.AsyncResult = queues.gpu.stage_2.delay({"job_id": payload["job_id"]})
        case 'gpu.stage_4':
            job_result: celery.result.AsyncResult = queues.gpu.stage_4.delay({"job_id": payload["job_id"]})
        case 'gpu.stage_8':
            job_result: celery.result.AsyncResult = queues.gpu.stage_8.delay({"job_id": payload["job_id"]})
        case _:
            raise Exception(f"Unknown step: {step_to_run}")

    job.celery_job_ids = json.dumps(json.loads(job.celery_job_ids) + [job_result.id])


def check_status_of_running_jobs():
    jobs = Job.select().where(
        Job.status.in_([JobStatus.SCHEDULED, JobStatus.RUNNING])
    )

    for job in jobs:
        try:
            id = json.loads(job.celery_job_ids)[-1]
            if job.current_step.startswith("gpu"):
                queue = queues.gpu.queue
            else:
                queue = queues.cpu.queue

            job_result = celery.result.AsyncResult(id, app=queue)

            job_state = job_result.state

            if job_state == "STARTED":
                job.status = JobStatus.RUNNING
            elif job_state == "FAILURE":
                job.status = JobStatus.FAILED
                logger.error(job_result.traceback)
            elif job_state == "SUCCESS":
                job_result.forget()

                job.progress += 1
                job.status = JobStatus.SCHEDULED

                if job.progress >= job.total:
                    job.status = JobStatus.SUCCEEDED
                else:
                    _start_next_step(job)

        except Exception as e:
            logger.exception(e)

            job.status = JobStatus.FAILED
        finally:
            job.save()


def check_for_new_jobs():
    jobs = Job.select().where(
        Job.status == JobStatus.QUEUED
    )

    for job in jobs:
        try:
            job.status = JobStatus.SCHEDULED

            _start_next_step(job)
        except Exception as e:
            logger.exception(e)

            job.status = JobStatus.FAILED
        finally:
            job.save()


def delete_old_jobs():
    jobs = Job.select().where(
        Job.status != JobStatus.SCHEDULED,
        Job.created_at < datetime.datetime.utcnow() - datetime.timedelta(days=3),
    )

    for job in jobs:
        try:
            job.delete()
        except Exception as e:
            logger.exception(e)


scheduler.add_job(check_status_of_running_jobs, 'interval', seconds=2, max_instances=1, coalesce=True)
scheduler.add_job(check_for_new_jobs, 'interval', seconds=2, max_instances=1, coalesce=True)
scheduler.add_job(delete_old_jobs, 'interval', hours=2, max_instances=1, coalesce=True,
                  next_run_time=datetime.datetime.now())

if __name__ == "__main__":
    scheduler.start()
