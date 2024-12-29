from app.db_setup import engine
from sqlalchemy.orm import Session
from app.database.models.models import Job
from app.logging.logger import logger



def update_job_status(job_id: int, status: str):
    with Session(engine) as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = status
            db.commit()
        else:
            logger.error(f"Job with id {job_id} not found")