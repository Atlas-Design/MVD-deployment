import json
import datetime
import traceback

import celery.result

import queues.cpu
import queues.gpu
import queues.base

from database import db, Job, JobStatus

from apscheduler.schedulers.blocking import BlockingScheduler

db.connect()

scheduler = BlockingScheduler()


def _start_next_step(job: Job):
    steps = json.loads(job.steps)
    step_to_run = steps[job.progress]

    job.current_step = step_to_run
    payload = json.loads(job.payload)

    print(step_to_run)

    match step_to_run:
        case 'cpu.prestage_0':
            job_result: celery.result.AsyncResult = queues.cpu.prestage_0.delay(payload)
        case 'cpu.stage_0':
            job_result: celery.result.AsyncResult = queues.cpu.stage_0.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_1':
            job_result: celery.result.AsyncResult = queues.cpu.stage_1.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_7':
            job_result: celery.result.AsyncResult = queues.cpu.stage_7.delay({"job_id": payload["job_id"]})
        case 'cpu.stage_8':
            job_result: celery.result.AsyncResult = queues.cpu.stage_8.delay({"job_id": payload["job_id"]})
        case 'gpu.stage_2':
            job_result: celery.result.AsyncResult = queues.gpu.stage_2.delay({"job_id": payload["job_id"]})
        case _:
            raise Exception(f"Unknown step")

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
                print(job_result.traceback)
            elif job_state == "SUCCESS":
                job_result.forget()

                job.progress += 1
                job.status = JobStatus.SCHEDULED

                if job.progress >= job.total:
                    job.status = JobStatus.SUCCEEDED
                else:
                    _start_next_step(job)

        except Exception as e:
            print(e)
            print(traceback.format_exc())

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
            print(e)
            print(traceback.format_exc())

            job.status = JobStatus.FAILED
        finally:
            job.save()


scheduler.add_job(check_status_of_running_jobs, 'interval', seconds=2)
scheduler.add_job(check_for_new_jobs, 'interval', seconds=2)

if __name__ == "__main__":
    scheduler.start()
