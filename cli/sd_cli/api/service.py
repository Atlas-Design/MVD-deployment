from typing import Literal, Optional, Union

import abc
import requests
import urllib.parse


class BaseCommand(abc.ABC):
    def __init__(
            self,
            base_url: str,
            path: str,
            method: Literal["GET", "POST"],

            data: Optional[dict] = None,
            files: Optional[Union[dict | list]] = None,
            params: Optional[dict] = None,
    ):
        self.base_url = base_url
        self.path = path
        self.method = method

        self.data = data
        self.files = files
        self.params = params

    def run(self):
        response = requests.request(
            method=self.method,
            url=urllib.parse.urljoin(self.base_url, self.path),
            data=self.data,
            files=self.files,
            params=self.params,
        )

        response.raise_for_status()

        return response.json()


class ServiceScheduleJobCommand(BaseCommand):
    def __init__(
            self,
            base_url: str,
            data: dict,  # todo: add type hint
            files: Union[dict | list],  # todo: add type hint
    ):
        super().__init__(
            base_url=base_url,
            path="/schedule_job",
            method="POST",
            data=data,
            files=files,
        )


class ServiceGetDownloadUrlCommand(BaseCommand):
    def __init__(
            self,
            base_url: str,

            job_id: str,
    ):
        super().__init__(
            base_url=base_url,
            path="/get_download_url",
            method="GET",
            params={"job_id": job_id},
        )


class ServiceCheckStatusCommand(BaseCommand):
    def __init__(
            self,
            base_url: str,

            job_id: str,
    ):
        super().__init__(
            base_url=base_url,
            path="/check_status",
            method="GET",
            params={"job_id": job_id},
        )
