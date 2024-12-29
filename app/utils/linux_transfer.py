import subprocess
import re
import time
from fastapi import HTTPException
from app.logging.logger import logger
from celery import shared_task
from app.database.models.models import JobStatus
from app.utils.update_job_status import update_job_status

@shared_task(name="transfer.linux", bind=True)
async def linux_transfer(self, transfer_data, server_configs, identity_file):
    """Linux-specific implementation using subprocess"""
    try:
        update_job_status(transfer_data['job_id'], JobStatus.IN_PROGRESS)
        logger.info(f"Starting linux transfer process with data: {transfer_data}")

        # Validate transfer data
        if not transfer_data['source_storage']:
            raise HTTPException(status_code=400, detail="Source storage is required")
        if not transfer_data['dest_storage']:
            raise HTTPException(status_code=400, detail="Destination storage is required")

        source = transfer_data['source_storage']
        dest = transfer_data['dest_storage']
        user_id = transfer_data['user_id']

        # Create tarball of the source directory
        source_archive = f"{source}.tar.gz"
        tar_cmd = [
            'ssh',
            '-i', str(identity_file),
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f"{server_configs['pisms']['user']}@{server_configs['pisms']['host']}",
            f"tar -czf {source_archive} -C {source} ."
        ]
        
        logger.info(f"Running tar command: {' '.join(tar_cmd)}")
        subprocess.check_call(tar_cmd)

        # Get total size for estimation
        size_cmd = [
            'ssh',
            '-i', str(identity_file),
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f"{server_configs['pisms']['user']}@{server_configs['pisms']['host']}",
            f"du -sb {source_archive}"
        ]
        
        logger.info(f"Running size command: {' '.join(size_cmd)}")
        size_output = subprocess.check_output(size_cmd, text=True)
        total_bytes = int(size_output.split()[0])
        logger.info(f"Total bytes: {total_bytes}")

        # Transfer the tarball using rsync
        rsync_cmd = [
            'rsync',
            '-avz',
            '--progress',
            '--stats',
            '--itemize-changes',
            '-e', f'ssh -i {identity_file} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null',
            f"{server_configs['pisms']['user']}@{server_configs['pisms']['host']}:{source_archive}",
            f"{server_configs['pimaster']['user']}@{server_configs['pimaster']['host']}:{dest}"
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
                        
                        # Update job status
                        update_job_status(transfer_data['job_id'], JobStatus.IN_PROGRESS)
                        
                        # Update task state
                        self.update_state(
                            state=JobStatus.IN_PROGRESS,
                            meta={
                                'job_id': transfer_data['job_id'],
                                'task_id': self.request.id,
                                'user_id': user_id,
                                'current': bytes_transferred,
                                'total': total_bytes,
                                'status': JobStatus.IN_PROGRESS,
                                'percent': progress
                            }
                        )
                        time.sleep(0.3)

        if process.returncode == 0:
            # Extract the tarball at the destination
            untar_cmd = [
                'ssh',
                '-i', str(identity_file),
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                f"{server_configs['pimaster']['user']}@{server_configs['pimaster']['host']}",
                f"tar -xzf {dest}/{source_archive} -C {dest}"
            ]
            logger.info(f"Running untar command: {' '.join(untar_cmd)}")
            subprocess.check_call(untar_cmd)

            # Clean up the tarball
            cleanup_cmd = [
                'ssh',
                '-i', str(identity_file),
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                f"{server_configs['pimaster']['user']}@{server_configs['pimaster']['host']}",
                f"rm {dest}/{source_archive}"
            ]
            logger.info(f"Running cleanup command: {' '.join(cleanup_cmd)}")
            subprocess.check_call(cleanup_cmd)

            logger.info("Transfer completed successfully")
            update_job_status(transfer_data['job_id'], JobStatus.COMPLETED)
            return {
                "status": "completed",
                "message": "Repository transfer successful",
                "source": source,
                "destination": dest
            }
        else:
            error = process.stderr.read()
            update_job_status(transfer_data['job_id'], JobStatus.FAILED)
            raise HTTPException(status_code=500, detail=f"Transfer failed: {error}")
            
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.output}"
        logger.error(error_msg)
        update_job_status(transfer_data['job_id'], JobStatus.FAILED)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        error_msg = f"Transfer failed: {str(e)}"
        logger.error(error_msg)
        update_job_status(transfer_data['job_id'], JobStatus.FAILED)
        raise HTTPException(status_code=500, detail=error_msg)

