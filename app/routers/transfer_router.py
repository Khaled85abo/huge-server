from fastapi import APIRouter, HTTPException
from app.database.schemas.schemas import TransferRequest
from app.tasks.transfer import transfer
from app.database.models.models import Job
import subprocess
from pathlib import Path
import time
import re
from app.logging.logger import logger
import platform
from app.utils.windows_transfer import windows_tar_transfer, windows_files_transfer
from app.utils.linux_transfer import linux_transfer

router = APIRouter()

@router.post("")
# async def transfer_resources(request: TransferRequest, current_user_id: int):
async def transfer_repository(request: TransferRequest):
    # Create transfer data dictionary with required information
    if request.source_storage == request.dest_storage:
        raise HTTPException(status_code=400, detail="Source and destination storages cannot be the same")
    if request.source_storage == "":
        raise HTTPException(status_code=400, detail="Source storage is required")
    if request.dest_storage == "":
        raise HTTPException(status_code=400, detail="Destination storage is required")
    
    # TODO: add the job to the database

    # transfer_data = {
    #     "source_storage": request.source_storage,
    #     "dest_storage": request.dest_storage,
    #     "status": "pending",
    #     "user_id": current_user_id
    # }

    # Queue the transfer task
    # task = transfer.delay(transfer_data)
    task = "werwrwusf8u9823"
    
    return {
        "message": "Transfer request received",
        "task_id": str(task),
        "status": "pending"
    }

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

@router.post("/test")
async def test_transfer_direct(request: TransferRequest):
    """Test endpoint that performs transfer directly without Celery"""
    if request.source_storage == "":
        raise HTTPException(status_code=400, detail="Source storage is required")
    if request.dest_storage == "":
        raise HTTPException(status_code=400, detail="Destination storage is required")

    transfer_data = {
        "source_storage": request.source_storage,
        "dest_storage": request.dest_storage,
        "user_id": 1  # Hardcoded for testing
    }

    try:
        # Check operating system and use appropriate transfer method
        if platform.system() == 'Windows':
            result = await windows_tar_transfer(transfer_data, SERVER_CONFIGS, IDENTITY_FILE)
        else:
            result = await linux_transfer(transfer_data, SERVER_CONFIGS, IDENTITY_FILE)
            
        return result

    except Exception as e:
        error_msg = f"Transfer failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


