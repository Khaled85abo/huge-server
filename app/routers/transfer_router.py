from fastapi import APIRouter, HTTPException
from app.database.schemas.schemas import TransferRequest
from app.tasks.transfer import transfer
from app.database.models.models import Job
import subprocess
from pathlib import Path
import time
import re
from app.logging.logger import logger

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

@router.post("/sync")
async def transfer_repository_sync(request: TransferRequest):
    if request.source_storage == "":
        raise HTTPException(status_code=400, detail="Source storage is required")
    if request.dest_storage == "":
        raise HTTPException(status_code=400, detail="Destination storage is required")
    
    # Create transfer data dictionary
    transfer_data = {
        "source_storage": request.source_storage,
        "dest_storage": request.dest_storage,
        "user_id": 1  # You can modify this or add it to the request model if needed
    }

    # Call transfer function directly instead of using delay()
    result = transfer(transfer_data)
    
    # return {
    #     "message": "Transfer completed",
    #     "result": result,
    #     "status": result.get("status", "unknown")
    # }

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
    if request.source_storage == request.dest_storage:
        raise HTTPException(status_code=400, detail="Source and destination storages cannot be the same")
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
        # First, get total size for estimation
        size_cmd = [
            'ssh',
            '-i', str(IDENTITY_FILE),
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f"{SERVER_CONFIGS['pisms']['user']}@{SERVER_CONFIGS['pisms']['host']}",
            f"du -sb {transfer_data['source_storage']}"
        ]
        
        logger.info(f"Running size command: {' '.join(size_cmd)}")
        size_output = subprocess.check_output(size_cmd, text=True)
        total_bytes = int(size_output.split()[0])
        logger.info(f"Total bytes: {total_bytes}")

        # Construct rsync command
        rsync_cmd = [
            'rsync',
            '-avz',
            '--progress',
            '--stats',
            '--itemize-changes',
            '-e', f'ssh -i {IDENTITY_FILE} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null',
            f"{SERVER_CONFIGS['pisms']['user']}@{SERVER_CONFIGS['pisms']['host']}:{transfer_data['source_storage']}",
            f"{SERVER_CONFIGS['pimaster']['user']}@{SERVER_CONFIGS['pimaster']['host']}:{transfer_data['dest_storage']}"
        ]
        
        logger.info(f"Running rsync command: {' '.join(rsync_cmd)}")
        process = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        start_time = time.time()
        bytes_transferred = 0
        current_file = ""
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
                
            if output:
                logger.info(f"Rsync output: {output.strip()}")
                # Log different types of rsync output
                if 'to-check=' in output:
                    # Progress line
                    matches = re.search(r'(\d+(?:,\d+)*)\s+(\d+)%\s+([\d.]+\w+/s)', output)
                    if matches:
                        bytes_str = matches.group(1).replace(',', '')
                        bytes_transferred = int(bytes_str)
                        progress = int((bytes_transferred / total_bytes) * 100)
                        logger.info(f"Progress: {progress}%")
                
                elif output.startswith('>f'):
                    # New file being transferred
                    current_file = output.split()[-1]
                    logger.info(f"Transferring file: {current_file}")

        if process.returncode == 0:
            logger.info("Transfer completed successfully")
            return {
                "status": "completed",
                "message": "Repository transfer successful",
                "source": transfer_data['source_storage'],
                "destination": transfer_data['dest_storage']
            }
        else:
            error = process.stderr.read()
            raise HTTPException(status_code=500, detail=f"Transfer failed: {error}")
            
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.output}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        error_msg = f"Transfer failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


