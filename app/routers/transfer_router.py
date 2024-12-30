from fastapi import APIRouter, HTTPException, Depends
from app.database.schemas.schemas import TransferRequest
# from app.tasks.transfer import transfer
from app.database.models.models import Job, User
import subprocess
from pathlib import Path
import time
import re
from app.logging.logger import logger
import platform
from app.utils.windows_transfer import windows_tar_transfer
from app.utils.linux_paramiko_transfer import linux_paramiko_transfer
from app.db_setup import get_db
from sqlalchemy.orm import Session
from app.celery_app import celery_app
from app.auth import get_current_user
router = APIRouter()


# Define server configurations (copy from transfer.py)
SERVER_CONFIGS = {
    'pimaster': {
        'host': '192.168.1.242',
        'user': 'khaled',
    },
    'pisms': {
        'host': '192.168.1.66',
        'user': 'khaled',
    }
}

IDENTITY_FILE = Path(__file__).parent.parent / 'identityFile' / 'id_rsa'


@router.get("")
async def get_jobs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    jobs = db.query(Job).filter(Job.user_id == current_user.id).order_by(Job.created_date.desc()).all()
    return jobs

@router.post("")
# async def transfer_resources(request: TransferRequest, current_user_id: int):
async def transfer_repository(request: TransferRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Create transfer data dictionary with required information
    if request.source_storage == "":
        raise HTTPException(status_code=400, detail="Source storage is required")
    if request.dest_storage == "":
        raise HTTPException(status_code=400, detail="Destination storage is required")
    
    # TODO: add the job to the database
    job = Job(
        source_storage=request.source_storage,
        dest_storage=request.dest_storage,
        status="pending",
        user_id=current_user.id
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    transfer_data = {
        "job_id": job.id,
        "source_storage": request.source_storage,
        "dest_storage": request.dest_storage,
        "status": "pending",
        "user_id": current_user.id
    }

    try:
        print("platform",platform.system())
        # Check operating system and use appropriate transfer method
        task = None
        if platform.system() == 'Windows':
            print("windows")
            logger.debug("Attempting to queue Windows transfer task")
            task = celery_app.send_task(
                'transfer.windows',
                args=[transfer_data, SERVER_CONFIGS, str(IDENTITY_FILE)]
            )                
        else:
            print("linux")
            logger.debug("Attempting to queue Linux transfer task")
            task = celery_app.send_task(
                'transfer.linux_paramiko',
                args=[transfer_data, SERVER_CONFIGS, str(IDENTITY_FILE)]
            )    
        
        logger.info(f"Task queued successfully with id: {task.id}")
        job.task_id = str(task)
        db.commit()
        db.refresh(job)

        return job
    except Exception as e:
        error_msg = f"Transfer failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)







@router.post("/test")
async def test_transfer_direct(request: TransferRequest, current_user: User = Depends(get_current_user)):
    """Test endpoint that performs transfer directly without Celery"""
    if request.source_storage == "":
        raise HTTPException(status_code=400, detail="Source storage is required")
    if request.dest_storage == "":
        raise HTTPException(status_code=400, detail="Destination storage is required")

    transfer_data = {
        "source_storage": request.source_storage,
        "dest_storage": request.dest_storage,
        "user_id": current_user.id  # Hardcoded for testing
    }

    try:
        # Check operating system and use appropriate transfer method
        if platform.system() == 'Windows':
            result = await windows_tar_transfer(transfer_data, SERVER_CONFIGS, IDENTITY_FILE)
        else:
            result = await linux_paramiko_transfer(transfer_data, SERVER_CONFIGS, IDENTITY_FILE)
            
        return result

    except Exception as e:
        error_msg = f"Transfer failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


