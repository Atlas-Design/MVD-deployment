from fastapi import FastAPI

from database import db, Job

app = FastAPI()

from routes.schedule_job import router as schedule_job_router
from routes.download_result import router as download_result_router
from routes.check_status import router as check_status_router

app.include_router(schedule_job_router)
app.include_router(download_result_router)
app.include_router(check_status_router)


@app.on_event("startup")
def startup():
    db.connect()
    db.create_tables([Job])

