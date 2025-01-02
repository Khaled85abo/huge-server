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
        self._last_known_status = {}
        self.job_id : int | None = None

    async def _broadcast_job_completion(self, job_id: int):
        await manager.broadcast_to_user(
            job_id,
            {
                "type": "job_completion",
                "job_id": job_id,
                "status": "SUCCESS"
            }
        )

    async def start_monitoring(self):
        """Single monitoring loop that tracks the current active job"""
        self._is_running = True
        
        while self._is_running:
            try:
                with Session(engine) as db:
                    # Get all jobs that are in progress
                    active_jobs = db.query(Job).filter(Job.status == JobStatus.IN_PROGRESS).all()

                    if len(active_jobs) == 0 and self.job_id is not None:
                        # broadcast a job completion notification
                        await self._broadcast_job_completion(self.job_id)
                        self.job_id = None
                    
                    for active_job in active_jobs:
                        if active_job.task_id:
                            if self.job_id is None:
                                self.job_id = active_job.id
                            elif self.job_id != active_job.id:
                                # broadcast a job completion notification
                                await self._broadcast_job_completion(self.job_id)
                                self.job_id = None

                            
                            result = AsyncResult(active_job.task_id)
                            status = result.status
                            
                            
                            # Initialize or update the last known status and progress
                            last_status = self._last_known_status.get(active_job.id, {}).get('status')
                            last_progress = self._last_known_status.get(active_job.id, {}).get('progress', {})
                            
                            # Check if the status or progress has changed
                            progress_info = result.info if result.info else {}
                            current_progress = {
                                "current": progress_info.get('current', 0),
                                "total": progress_info.get('total', 0),
                                "percent": progress_info.get('percent', 0)
                            }
                            
                            if last_status != status or last_progress != current_progress:
                                self._last_known_status[active_job.id] = {
                                    'status': status,
                                    'progress': current_progress
                                }
                                
                                update = {
                                    "job_id": active_job.id,
                                    "status": status,
                                    "task_id": active_job.task_id,
                                    **current_progress
                                }
                                
                                # Check if job is complete (SUCCESS or FAILURE)
                                # if status in ['SUCCESS', 'FAILURE']:
                                #     logger.info(f"Job {active_job.id} completed with status: {status}")
                                #     # Send a job completion notification
                                #     await manager.broadcast_to_user(
                                #         active_job.user_id,
                                #         {
                                #             "type": "job_completion",
                                #             "job_id": active_job.id,
                                #             "status": status
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