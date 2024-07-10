FROM python:3.11

ENV PYTHONUNBUFFERED=1

WORKDIR /code/

RUN pip install pipenv

ADD Pipfile.lock Pipfile ./
RUN pipenv install --deploy && pipenv install --skip-lock gunicorn

ENV PATH="/code/.venv/bin:$PATH"
ENV PYTHONPATH="/code/src:$PYTHONPATH"

COPY src src/

#WORKDIR src

#CMD bash -c "pipenv run uvicorn 'app:app' --app-dir src --workers 4 --host 0.0.0.0 --port 3000"
