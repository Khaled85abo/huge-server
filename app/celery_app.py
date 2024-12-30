from celery import Celery
from kombu.utils.url import maybe_sanitize_url
import os

# Use separate Redis databases for broker and backend
redis_broker_url = os.getenv('REDIS_BROKER_URL')
redis_backend_url = os.getenv('REDIS_BACKEND_URL')

celery_app = Celery(
    'jobs',
    broker=redis_broker_url,
    backend=redis_backend_url
)

# Add this to explicitly include task modules
celery_app.autodiscover_tasks([
    'app.utils.windows_transfer',
    'app.utils.linux_paramiko_transfer'
])

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    
    # Add ML worker configuration
    task_routes={
        'transfer.*': {'queue': 'default'},       # Resource processing tasks
        '*': {'queue': 'default'}   
    },
    # task_time_limit=14400,  # 4 hours max
    # task_soft_time_limit=14100,  # Soft limit 15 mins before hard limit
    worker_prefetch_multiplier=1,  # Process one task at a time
    # worker_max_memory_per_child=4000000,  # Restart worker after using 4GB RAM
       # Add beat schedule
    # beat_schedule={
    #     'run-ml-training-at-midnight': {
    #         'task': 'train_yolo_model',
    #         'schedule': crontab(hour=0, minute=0),  # Run at midnight
    #         # Optional: if you want to pass default args
    #         # 'args': (default_data_dict,)
    #     },
    # }
    #    beat_schedule={
    #     # Run at midnight every day
    #     'daily-midnight-training': {
    #         'task': 'train_yolo_model',
    #         'schedule': crontab(hour=0, minute=0),
    #     },
        
    #     # Run every Sunday at 2 AM
    #     'weekly-training': {
    #         'task': 'train_yolo_model',
    #         'schedule': crontab(hour=2, minute=0, day_of_week=0),
    #     },
        
    #     # Run at 1 AM on the first day of every month
    #     'monthly-training': {
    #         'task': 'train_yolo_model',
    #         'schedule': crontab(hour=1, minute=0, day_of_month=1),
    #     }
    # }
)

print(f"Celery is configured with broker: {maybe_sanitize_url(celery_app.conf.broker_url)}")
print(f"Celery is configured with backend: {maybe_sanitize_url(celery_app.conf.result_backend)}")

# For your regular tasks:
# celery -A app.celery_app worker -Q default --loglevel=info

# For your ML tasks:
# celery -A app.celery_app worker -Q ml_training -c 1 --loglevel=info

# the command to start celery manually
# celery -A app.celery_app worker --pool=solo --loglevel=info

# hight bebugging
# celery -A app.celery_app worker --pool=solo -Q default --loglevel=debug

# low bebugging
#celery -A app.celery_app worker --pool=solo -Q default --loglevel=info