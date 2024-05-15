import os
import zipfile
import tempfile

from pathlib import Path
from urllib.request import urlretrieve

from sd_cli.api.service import ServiceGetDownloadUrlCommand


def download_result(
        backend_base: str,

        job_id: str,
        output: Path,
):

    get_url_command = ServiceGetDownloadUrlCommand(
        base_url=backend_base,
        job_id=job_id
    )

    get_url_result = get_url_command.run()

    if output.suffix == ".zip":
        urlretrieve(get_url_result["download_url"], output)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'data.zip')

            urlretrieve(get_url_result["download_url"], path)

            with zipfile.ZipFile(path, 'r') as zf:
                os.makedirs(output, exist_ok=True)
                zf.extractall(output)
