import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from database import db, Job
from settings import settings, Environment

from routes.schedule_job import router as schedule_job_router
from routes.download_result import router as download_result_router
from routes.check_status import router as check_status_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    db.create_tables([Job])
    yield
    db.close()


app = FastAPI(
    lifespan=lifespan,
    **({} if settings.ENV == Environment.DEV else {"docs_url": None, "redoc_url": None})
)

app.include_router(schedule_job_router)
app.include_router(download_result_router)
app.include_router(check_status_router)

logger = logging.getLogger("sd_cloud.server")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')

    logger.error(f"{request}: {exc_str}")

    if settings.ENV == Environment.DEV:
        return JSONResponse(content={'message': exc_str}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    else:
        return Response(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("cmd.server:app", host="0.0.0.0", port=3000, reload=True)
