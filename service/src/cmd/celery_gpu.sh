#!/usr/bin/env bash

celery -A queues.gpu worker -c 1 --loglevel=INFO