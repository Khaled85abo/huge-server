from celery.result import AsyncResult
from app.websocket.connection_manager import manager
from app.database.models.models import Job
from app.db_setup import Session, engine
import asyncio
from app.database.models.models import JobStatus
import json
from app.logging.logger import logger

async def monitor_jobs(user_id: int, job_ids: list):
    """Monitor Celery tasks for the given job IDs and send progress updates via WebSocket"""
    while True:
        try:
            with Session(engine) as db:
                jobs = db.query(Job).filter(Job.id.in_(job_ids)).all()
                
                updates = []
                active_jobs = False
                
                for job in jobs:
                    if job.task_id:
                        result = AsyncResult(job.task_id)
                        
                        status = result.status
                        info = {
                            "job_id": job.id,
                            "status": status,
                            "task_id": job.task_id,
                        }
                        
                        # Add progress info if available
                        if status == JobStatus.IN_PROGRESS and result.info:
                            info.update(result.info)
                        
                        updates.append(info)
                        
                        # Check if we have any active jobs
                        if status in [JobStatus.PENDING, JobStatus.IN_PROGRESS]:
                            active_jobs = True
                
                # Send updates via WebSocket
                if updates:
                    await manager.broadcast_to_user(
                        user_id,
                        {
                            "type": "job_updates",
                            "updates": updates
                        }
                    )
                
                # If no active jobs, stop monitoring
                if not active_jobs:
                    break
                
        except Exception as e:
            logger.error(f"Error monitoring jobs: {str(e)}")
            break
            
        # Wait before next update
        await asyncio.sleep(1)


async def monitor_celery_task(user_id: int, task_id: str):
    """Monitor a single Celery task and broadcast updates"""
    while True:
        try:
            # Get task status from Celery
            result = AsyncResult(task_id)
            
            if result.ready():  # Task is finished
                if result.successful():
                    await manager.broadcast_to_user(
                        user_id,
                        {
                            "type": "transfer_progress",
                            "task_id": task_id,
                            "status": "completed"
                        }
                    )
                else:
                    await manager.broadcast_to_user(
                        user_id,
                        {
                            "type": "transfer_progress",
                            "task_id": task_id,
                            "status": "failed",
                            "error": str(result.result)  # Get error message
                        }
                    )
                break
            
            elif result.state == 'PROGRESS':
                # Get progress info that we stored with update_state
                progress_data = result.info
                await manager.broadcast_to_user(
                    user_id,
                    {
                        "type": "transfer_progress",
                        "task_id": task_id,
                        "status": "in_progress",
                        **progress_data  # Include all progress data
                    }
                )
            
        except Exception as e:
            logger.error(f"Error monitoring task {task_id}: {str(e)}")
            break
            
        await asyncio.sleep(1)  # Wait before next check