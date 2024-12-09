import subprocess
import asyncio
from pathlib import Path
import paramiko
from app.logging.logger import logger
import time
from app.websocket.connection_manager import manager



# Why read in chunks?
# - Windows is not as efficient with large file transfers
# - Reading in chunks allows us to update the progress bar more frequently
# - Reading in chunks allows us to handle errors more gracefully
CHUNK_SIZES = {
    'small': 32768,
    'medium': 65536,
    'large': 131072
}

async def windows_transfer(transfer_data, server_configs, identity_file):
    """Windows-specific implementation using paramiko"""
    try:
        logger.info(f"Starting windows transfer process with data: {transfer_data}")
        source = transfer_data['source_storage']
        dest = transfer_data['dest_storage']
        user_id = transfer_data['user_id']
        
        # Initialize SSH connections for both servers
        logger.info("Initializing SSH clients...")
        source_ssh = paramiko.SSHClient()
        dest_ssh = paramiko.SSHClient()
        source_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        dest_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Load private key
        logger.info(f"Loading private key from: {identity_file}")
        private_key = paramiko.RSAKey(filename=str(identity_file))
        
        # Connect to source server (pisms)
        source_server = server_configs['pisms']
        logger.info(f"Connecting to source server: {source_server['host']}")
        source_ssh.connect(
            source_server['host'],
            username=source_server['user'],
            pkey=private_key
        )
        logger.info("Successfully connected to source server")
        
        # Connect to destination server (pimaster)
        dest_server = server_configs['pimaster']
        logger.info(f"Connecting to destination server: {dest_server['host']}")
        dest_ssh.connect(
            dest_server['host'],
            username=dest_server['user'],
            pkey=private_key
        )
        logger.info("Successfully connected to destination server")
        
        # Setup SFTP connections
        source_sftp = source_ssh.open_sftp()
        dest_sftp = dest_ssh.open_sftp()
        logger.info("SFTP connections established")
        
        # Use tar instead of zip
        source_archive = f"{source}.tar.gz"
        dest_archive = f"{dest}.tar.gz"
        
        # Create tar archive
        logger.info(f"Creating tar archive: {source_archive}")
        source_parent = str(Path(source).parent).replace('\\', '/')  # Ensure forward slashes
        source_name = Path(source).name
        tar_command = f"cd '{source_parent}' && tar -czf '{source_archive}' '{source_name}'"
        
        logger.info(f"Executing command: {tar_command}")  # Add this for debugging
        stdin, stdout, stderr = source_ssh.exec_command(tar_command)
        
        tar_error = stderr.read().decode()
        tar_output = stdout.read().decode()
        logger.info(f"Tar command output: {tar_output}")
        if tar_error:
            logger.error(f"Tar command error: {tar_error}")
            raise Exception(f"Failed to create tar archive: {tar_error}")
        
        # Get file size (using Linux-compatible stat command)
        size_command = f"stat -c%s '{source_archive}'"
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

        # Initialize transfer tracking
        start_time = time.time()
        bytes_transferred = 0

        # Create destination directory
        # mkdir_command = f"mkdir -p {Path(dest).parent}"
        # dest_ssh.exec_command(mkdir_command)

        # Create progress callback for single file transfer
        callback = create_progress_callback(
            user_id=user_id,
            total_bytes=total_bytes,
            current_file=source_archive,
            start_time=start_time,
            bytes_transferred=bytes_transferred
        )

        # Transfer the zip file
        logger.info(f"Transferring zip file to destination")
        try:
            with source_sftp.file(source_archive, 'rb') as source_fh:
                with dest_sftp.file(dest_archive, 'wb') as dest_fh:
                    while True:
                        data = source_fh.read(CHUNK_SIZES['small'])
                        if not data:
                            break
                        dest_fh.write(data)
                        callback(len(data), total_bytes)
        except Exception as e:
            logger.error(f"Error transferring zip file: {str(e)}")
            raise

        # Unzip on destination server
        logger.info("Untarring file on destination server")
        # Untar on destination server
        # untar_command = f"cd {Path(dest).parent} && tar -xzf {dest_archive} && rm {dest_archive}"
        untar_command = f"cd / && tar -xzf {dest_archive} && rm {dest_archive}"
        stdin, stdout, stderr = dest_ssh.exec_command(untar_command)
        if stderr.read():
            raise Exception(f"Failed to untar file: {stderr.read().decode()}")

        # Clean up zip file on source server
        logger.info("Cleaning up source zip file")
        cleanup_command = f"rm {source_archive}"
        source_ssh.exec_command(cleanup_command)

        logger.info("All files transferred successfully")
        
        # Close connections
        source_sftp.close()
        dest_sftp.close()
        source_ssh.close()
        dest_ssh.close()
        logger.info("All connections closed")
        
        return {
            "status": "completed",
            "message": "Repository transfer successful",
            "source": source,
            "destination": dest
        }
        
    except Exception as e:
        logger.error(f"Windows transfer failed with error: {str(e)}")
        await manager.broadcast_to_user(
            user_id,
            {
                "type": "transfer_progress",
                "progress": -1,
                "error": str(e)
            }
        )
        raise Exception(f"Windows transfer failed: {str(e)}")
    


def create_progress_callback(user_id, total_bytes, current_file, start_time, bytes_transferred):
    """Creates a progress callback function for file transfers"""
    def progress_callback(bytes_so_far, total_bytes_for_file):
        nonlocal bytes_transferred
        bytes_transferred += bytes_so_far
        
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
        
        logger.info(f"Transfer progress: {progress}% ({bytes_transferred}/{total_bytes} bytes)")
        logger.info(f"Current file progress: {bytes_so_far}/{total_bytes_for_file} bytes")
        logger.info(f"Estimated time remaining: {int(estimated_seconds)} seconds")
        
        # Send progress update
        asyncio.create_task(
            manager.broadcast_to_user(
                user_id,
                {
                    "type": "transfer_progress",
                    "progress": progress,
                    "current_file": current_file,
                    "bytes_transferred": bytes_transferred,
                    "total_bytes": total_bytes,
                    "estimated_time_remaining": int(estimated_seconds),
                    "error": None
                }
            )
        )
    
    return progress_callback