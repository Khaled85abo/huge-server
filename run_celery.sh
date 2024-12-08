#! /bin/bash

celery -A app.celery_app worker --pool=solo --loglevel=info