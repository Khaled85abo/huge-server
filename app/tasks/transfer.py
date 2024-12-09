import logging
from celery import shared_task
import subprocess
from pathlib import Path
import asyncio
import json
import re
import time
from app.logging.logger import logger
from app.websocket.connection_manager import manager
from asgiref.sync import async_to_sync

# Define server configurations
SERVER_CONFIGS = {
    'pimaster': {
        'host': '192.168.1.242', # This will be replace by MAX IV IP address
        'user': 'khaled',  # Assuming default Raspberry Pi username
    },
    'pisms': {
        'host': '192.168.1.66', # This will be replace by ICE IP address
        'user': 'khaled',
    }
}

IDENTITY_FILE = Path(__file__).parent.parent / 'identityFile' / 'id_rsa'


@shared_task(name="transfer")
def transfer(transfer_data: dict) -> dict:
    logger.info(f"Starting repository transfer: {transfer_data}")
    
    source = transfer_data['source_storage']
    dest = transfer_data['dest_storage']
    user_id = transfer_data['user_id']
    
    try:
        # First, get total size for estimation
        size_cmd = [
            'ssh', 
            '-i', str(IDENTITY_FILE),
            f"{SERVER_CONFIGS['pisms']['user']}@{SERVER_CONFIGS['pisms']['host']}", 
            f"du -sb {source}"
        ]
        size_output = subprocess.check_output(size_cmd, text=True)
        total_bytes = int(size_output.split()[0])
        print(f"Total bytes: {total_bytes}")
        # Construct rsync command with itemize changes
        rsync_cmd = [
            'rsync',
            '-avz',
            '--progress',
            '--stats',
            '--itemize-changes',
            '-e', f'ssh -i {IDENTITY_FILE}',
            f"{SERVER_CONFIGS['pisms']['user']}@{SERVER_CONFIGS['pisms']['host']}:{source}",
            f"{SERVER_CONFIGS['pimaster']['user']}@{SERVER_CONFIGS['pimaster']['host']}:{dest}"
        ]
        print(f"Rsync command: {rsync_cmd}")
        
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
                # Parse different types of rsync output
                if 'to-check=' in output:
                    # Progress line
                    progress_info = parse_rsync_progress(output)
                    if progress_info:
                        bytes_transferred = progress_info['bytes_transferred']
                        
                        # Calculate progress percentage
                        progress = int((bytes_transferred / total_bytes) * 100)
                        
                        # Calculate estimated time remaining
                        elapsed_time = time.time() - start_time
                        if bytes_transferred > 0:
                            transfer_rate = bytes_transferred / elapsed_time
                            remaining_bytes = total_bytes - bytes_transferred
                            estimated_seconds = remaining_bytes / transfer_rate if transfer_rate > 0 else 0
                        else:
                            estimated_seconds = 0

                        # Send progress update
                        async_to_sync(send_progress_update)(
                            user_id=user_id,
                            progress=progress,
                            current_file=current_file,
                            bytes_transferred=bytes_transferred,
                            total_bytes=total_bytes,
                            estimated_time=int(estimated_seconds)
                        )
                
                elif output.startswith('>f'):
                    # New file being transferred
                    current_file = output.split()[-1]
                    logger.info(f"Transferring file: {current_file}")

        if process.returncode == 0:
            logger.info("Transfer completed successfully")
            # Send final progress update
            async_to_sync(send_progress_update)(
                user_id=user_id,
                progress=100,
                current_file="Complete",
                bytes_transferred=total_bytes,
                total_bytes=total_bytes,
                estimated_time=0
            )
            return {
                "status": "completed",
                "message": "Repository transfer successful",
                "source": source,
                "destination": dest
            }
        else:
            raise subprocess.CalledProcessError(process.returncode, rsync_cmd)
            
    except Exception as e:
        error_msg = f"Transfer failed: {str(e)}"
        logger.error(error_msg)
        async_to_sync(send_progress_update)(
            user_id=user_id,
            progress=-1,
            error=str(e)
        )
        return {
            "status": "failed",
            "message": error_msg,
            "source": source,
            "destination": dest
        }

def parse_rsync_progress(output: str) -> dict:
    """Parse rsync progress output and return detailed information."""
    try:
        # Example output: "    1,234,567  50%    1.23MB/s    0:00:59"
        matches = re.search(r'(\d+(?:,\d+)*)\s+(\d+)%\s+([\d.]+\w+/s)', output)
        if matches:
            bytes_str = matches.group(1).replace(',', '')
            return {
                'bytes_transferred': int(bytes_str),
                'speed': matches.group(3)
            }
    except Exception as e:
        logger.error(f"Error parsing rsync progress: {e}")
    return None

async def send_progress_update(
    user_id: int,
    progress: int,
    current_file: str = None,
    bytes_transferred: int = None,
    total_bytes: int = None,
    estimated_time: int = None,
    error: str = None
):
    """Send detailed progress update through WebSocket."""
    message = {
        "type": "transfer_progress",
        "progress": progress,
        "current_file": current_file,
        "bytes_transferred": bytes_transferred,
        "total_bytes": total_bytes,
        "estimated_time_remaining": estimated_time,
        "error": error
    }
    await manager.broadcast_to_user(user_id, message)