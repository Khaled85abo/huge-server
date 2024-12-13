from celery.result import AsyncResult
from app.websocket.connection_manager import manager
from app.database.models.models import Job, JobStatus
from app.db_setup import Session, engine
import asyncio
from app.logging.logger import logger

class JobMonitor:
    def __init__(self):
        self._current_job = None
        self._is_running = False

    async def start_monitoring(self):
        """Single monitoring loop that tracks the current active job"""
        self._is_running = True
        
        while self._is_running:
            try:
                with Session(engine) as db:
                    # Get the currently processing job
                    active_job = db.query(Job).filter(Job.status == JobStatus.IN_PROGRESS).first()
                    
                    if active_job and active_job.task_id:
                        result = AsyncResult(active_job.task_id)
                        status = result.status
                        
                        update = {
                            "job_id": active_job.id,
                            "status": status,
                            "task_id": active_job.task_id,
                        }
                        
                        # Add progress info if available
                        if status == JobStatus.IN_PROGRESS and result.info:
                            # result.info contains the meta data from self.update_state
                            progress_info = result.info
                            update.update({
                                "current": progress_info.get('current', 0),
                                "total": progress_info.get('total', 0),
                                "percent": progress_info.get('percent', 0),
                                "status": progress_info.get('status', JobStatus.IN_PROGRESS)
                            })
                            
                        # Check if job is complete (SUCCESS or FAILURE)
                        # elif status in ['SUCCESS', JobStatus.COMPLETED]:
                        #     logger.info(f"Job {active_job.id} completed with status: {status}")
                        #     # Send a job completion notification
                        #     await manager.broadcast_to_user(
                        #         active_job.user_id,
                        #         {
                        #             "type": "job_completion",
                        #             "job_id": active_job.id,
                        #             "status": JobStatus.COMPLETED
                        #         }
                        #     )
                        
                        # Broadcast to the job's owner
                        await manager.broadcast_to_user(
                            active_job.user_id,
                            {
                                "type": "job_updates",
                                "updates": [update]
                            }
                        )
                        
            except Exception as e:
                logger.error(f"Error in job monitor: {str(e)}")
                
            await asyncio.sleep(1)
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self._is_running = False

# Create a single instance
job_monitor = JobMonitor()