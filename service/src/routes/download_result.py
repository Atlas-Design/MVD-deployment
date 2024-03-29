from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query
from starlette.responses import JSONResponse

from google.cloud import storage

from settings import settings

client_storage = storage.Client()

router = APIRouter()


@dataclass
class DownloadConfig:
    job_id: str = Query()


@router.get("/get_download_url")
def get_download_url(
        config: DownloadConfig = Depends(),
):
    job_id = config.job_id

    data_bucket = client_storage.bucket(settings.SD_DATA_STORAGE_BUCKET_NAME)

    output_blob = data_bucket.blob(f"{job_id}/data.zip")

    output_blob.make_public()

    return JSONResponse(
        content={
            "download_url": output_blob.public_url
        }
    )
