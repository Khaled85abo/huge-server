from fastapi import APIRouter, HTTPException
from app.database.schemas.schemas import TransferRequest
from app.tasks.transfer import transfer
from app.database.models.models import Job
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
    if request.source_storage == request.dest_storage:
        raise HTTPException(status_code=400, detail="Source and destination storages cannot be the same")
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
    
    return {
        "message": "Transfer completed",
        "result": result,
        "status": result.get("status", "unknown")
    }


