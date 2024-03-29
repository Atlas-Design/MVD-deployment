#!/usr/bin/env bash

celery -A queues.cpu worker -c 2 --loglevel=INFO