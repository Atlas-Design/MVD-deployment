import json


from database import db, Job, JobStatus

from google.cloud import batch_v1
from apscheduler.schedulers.blocking import BlockingScheduler


db.connect()

client_batch = batch_v1.BatchServiceClient()

scheduler = BlockingScheduler()


def _run_batch_step(job: Job):
    steps = json.loads(job.steps)
    step_to_run = steps[job.progress]

    batch_job = client_batch.create_job(
        batch_v1.CreateJobRequest(step_to_run)
    )

    job.batch_job_name = batch_job.name


def check_status_of_running_jobs():
    jobs = Job.select().where(
        Job.status.in_([JobStatus.SCHEDULED, JobStatus.RUNNING])
    )

    for job in jobs:
        try:
            batch_job = client_batch.get_job(
                batch_v1.GetJobRequest({"name": job.batch_job_name})
            )
            batch_job_state = batch_job.status.state

            if batch_job_state == batch_v1.JobStatus.State.RUNNING:
                job.status = JobStatus.RUNNING
            elif batch_job_state == batch_v1.JobStatus.State.FAILED:
                job.status = JobStatus.FAILED
            elif batch_job_state == batch_v1.JobStatus.State.SUCCEEDED:
                job.progress += 1

                if job.progress >= job.total:
                    job.status = JobStatus.SUCCEEDED
                else:
                    _run_batch_step(job)

        except Exception as e:
            print(e)
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

            _run_batch_step(job)
        except Exception as e:
            print(e)

            job.status = JobStatus.FAILED
        finally:
            job.save()


scheduler.add_job(check_status_of_running_jobs, 'interval', seconds=10)
scheduler.add_job(check_for_new_jobs, 'interval', seconds=10)

if __name__ == "__main__":
    scheduler.start()
