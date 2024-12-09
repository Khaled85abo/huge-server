import subprocess
import re
import time
from fastapi import HTTPException
from app.logging.logger import logger

async def linux_transfer(transfer_data, server_configs, identity_file):
    """Linux-specific implementation using subprocess"""
    if transfer_data['source_storage'] == "":
        raise HTTPException(status_code=400, detail="Source storage is required")
    if transfer_data['dest_storage'] == "":
        raise HTTPException(status_code=400, detail="Destination storage is required")

    transfer_data = {
        "source_storage": transfer_data.source_storage,
        "dest_storage": transfer_data.dest_storage,
        "user_id": 1  # Hardcoded for testing
    }

    try:
        # First, get total size for estimation
        size_cmd = [
            'ssh',
            '-i', str(identity_file),
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f"{server_configs['pisms']['user']}@{server_configs['pisms']['host']}",
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
            '-e', f'ssh -i {identity_file} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null',
            f"{server_configs['pisms']['user']}@{server_configs['pisms']['host']}:{transfer_data['source_storage']}",
            f"{server_configs['pimaster']['user']}@{server_configs['pimaster']['host']}:{transfer_data['dest_storage']}"
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