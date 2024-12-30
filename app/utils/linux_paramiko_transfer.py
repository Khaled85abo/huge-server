import asyncio
import time
import paramiko
from pathlib import Path
from fastapi import HTTPException
from celery import shared_task
from app.database.models.models import JobStatus
from app.utils.update_job_status import update_job_status
from app.logging.logger import logger

# Adjustable chunk sizes for reading/writing
CHUNK_SIZE = {
    'small': 32768,
    'medium': 65536,
    'large': 131072
}

@shared_task(name="transfer.linux_paramiko", bind=True)
def linux_transfer(self, transfer_data, server_configs, identity_file):
    """
    Linux-specific implementation using Paramiko (chunk-based transfer).
    This replaces the old subprocess/rsync approach.
    """
    try:
        update_job_status(transfer_data['job_id'], JobStatus.IN_PROGRESS)
        logger.info(f"Starting Linux transfer process (Paramiko) with data: {transfer_data}")

        # Validate transfer data
        if not transfer_data.get('source_storage'):
            raise HTTPException(status_code=400, detail="Source storage is required")
        if not transfer_data.get('dest_storage'):
            raise HTTPException(status_code=400, detail="Destination storage is required")

        source = transfer_data['source_storage']
        dest = transfer_data['dest_storage']
        user_id = transfer_data['user_id']

        # Prepare SSH clients
        source_ssh = paramiko.SSHClient()
        source_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        dest_ssh = paramiko.SSHClient()
        dest_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load private key
        logger.info(f"Loading private key from: {identity_file}")
        private_key = paramiko.RSAKey(filename=str(identity_file))

        # Connect to source server (e.g. pisms)
        source_server = server_configs['pisms']
        logger.info(f"Connecting to source server: {source_server['host']}")
        source_ssh.connect(
            source_server['host'],
            username=source_server['user'],
            pkey=private_key
        )
        logger.info("Successfully connected to source server")

        # Connect to destination server (e.g. pimaster)
        dest_server = server_configs['pimaster']
        logger.info(f"Connecting to destination server: {dest_server['host']}")
        dest_ssh.connect(
            dest_server['host'],
            username=dest_server['user'],
            pkey=private_key
        )
        logger.info("Successfully connected to destination server")

        # Create tar archive on source
        source_archive = f"{source}.tar.gz"
        tar_command = f"tar -czf '{source_archive}' -C '{source}' ."
        logger.info(f"Creating tar archive on source with command: {tar_command}")
        stdin, stdout, stderr = source_ssh.exec_command(tar_command)
        tar_output = stdout.read().decode()
        tar_error = stderr.read().decode()
        if tar_error:
            logger.error(f"Tar command error: {tar_error}")
            raise Exception(f"Failed to create tar archive: {tar_error}")
        logger.info(f"Tar command output: {tar_output}")

        # Determine size of the newly created tarball
        size_command = f"stat -c%s '{source_archive}'"
        logger.info(f"Getting archive size with command: {size_command}")
        stdin, stdout, stderr = source_ssh.exec_command(size_command)
        size_output = stdout.read().decode().strip()
        size_error = stderr.read().decode()
        if size_error:
            logger.error(f"Error getting file size: {size_error}")
            raise Exception(f"Failed to get archive size: {size_error}")
        if not size_output:
            logger.error("File size command returned empty output")
            raise Exception("Failed to get archive size: empty output")

        total_bytes = int(size_output)
        logger.info(f"Archive file size: {total_bytes} bytes")

        # Open SFTP connections
        logger.info("Opening SFTP connections on both servers...")
        source_sftp = source_ssh.open_sftp()
        dest_sftp = dest_ssh.open_sftp()

        # Transfer the tar file in chunks
        bytes_transferred = 0
        dest_archive = f"{dest}/{Path(source_archive).name}"
        logger.info(f"Transferring tarball to destination: {dest_archive}")

        with source_sftp.file(source_archive, 'rb') as sfh:
            with dest_sftp.file(dest_archive, 'wb') as dfh:
                while True:
                    data = sfh.read(CHUNK_SIZE['small'])
                    if not data:
                        break
                    dfh.write(data)
                    bytes_transferred += len(data)

                    # Calculate progress
                    progress = int((bytes_transferred / total_bytes) * 100)

                    # Update Celery task state
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
                    time.sleep(0.2)  # Throttle updates slightly

        # Close SFTP after the transfer
        source_sftp.close()
        dest_sftp.close()
        logger.info("Tarball transfer completed; SFTP connections closed")

        # Untar on destination server
        untar_command = f"tar -xzf '{dest_archive}' -C '{dest}'"
        logger.info(f"Untarring archive on destination with command: {untar_command}")
        stdin, stdout, stderr = dest_ssh.exec_command(untar_command)
        untar_output = stdout.read().decode()
        untar_error = stderr.read().decode()
        if untar_error:
            logger.error(f"Untar command error: {untar_error}")
            raise Exception(f"Failed to untar file: {untar_error}")
        logger.info(f"Untar command output: {untar_output}")

        # Remove tarball on destination
        rm_dest_cmd = f"rm '{dest_archive}'"
        logger.info(f"Removing tarball on destination: {rm_dest_cmd}")
        dest_ssh.exec_command(rm_dest_cmd)

        # Remove tarball on source
        rm_source_cmd = f"rm '{source_archive}'"
        logger.info(f"Cleaning up tar file on source: {rm_source_cmd}")
        source_ssh.exec_command(rm_source_cmd)

        # Close SSH connections
        source_ssh.close()
        dest_ssh.close()
        logger.info("All SSH connections closed.")

        # Update job status to COMPLETED
        update_job_status(transfer_data['job_id'], JobStatus.COMPLETED)
        logger.info("Linux transfer (Paramiko) completed successfully.")

        return {
            "status": "completed",
            "message": "Linux transfer (Paramiko) successful",
            "source": source,
            "destination": dest
        }

    except Exception as e:
        logger.error(f"Linux transfer (Paramiko) failed with error: {e}")
        update_job_status(transfer_data['job_id'], JobStatus.FAILED)
        raise HTTPException(status_code=500, detail=str(e))
