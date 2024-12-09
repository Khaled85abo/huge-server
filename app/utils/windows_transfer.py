import subprocess
import asyncio
from pathlib import Path
import paramiko
from app.logging.logger import logger
import time
from app.websocket.connection_manager import manager

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
        
        # Get total size
        size_command = f"du -sb {source}"
        logger.info(f"Getting total size with command: {size_command}")
        stdin, stdout, stderr = source_ssh.exec_command(size_command)
        total_bytes = int(stdout.read().decode().split()[0])
        logger.info(f"Total bytes to transfer: {total_bytes}")
        
        # Get list of files
        find_command = f"find {source} -type f"
        logger.info(f"Getting file list with command: {find_command}")
        stdin, stdout, stderr = source_ssh.exec_command(find_command)
        files_to_transfer = stdout.read().decode().split('\n')
        files_to_transfer = [f for f in files_to_transfer if f]
        logger.info(f"Found {len(files_to_transfer)} files to transfer")
        
        # Initialize transfer tracking
        start_time = time.time()
        bytes_transferred = 0
        
        for source_file in files_to_transfer:
            # Calculate paths
            rel_path = Path(source_file).relative_to(source)
            dest_file = str(Path(dest) / rel_path).replace('\\', '/')
            current_file = source_file
            
            logger.info(f"Processing file: {source_file} -> {dest_file}")
            
            # Create destination directory on dest server
            dest_dir = str(Path(dest_file).parent).replace('\\', '/')
            mkdir_command = f"mkdir -p {dest_dir}"
            logger.info(f"Creating directory on destination: {mkdir_command}")
            stdin, stdout, stderr = dest_ssh.exec_command(mkdir_command)
            
            # Get file size
            file_attr = source_sftp.stat(source_file)
            file_size = file_attr.st_size
            logger.info(f"File size: {file_size} bytes")
            
            # Create progress callback
            callback = create_progress_callback(
                user_id=user_id,
                total_bytes=total_bytes,
                current_file=current_file,
                start_time=start_time,
                bytes_transferred=bytes_transferred
            )
            
            # Transfer file from source to destination
            logger.info(f"Starting transfer of: {source_file}")
            try:
                # Create a temporary file for transfer
                with source_sftp.file(source_file, 'rb') as source_fh:
                    with dest_sftp.file(dest_file, 'wb') as dest_fh:
                        while True:
                            data = source_fh.read(32768)  # Read in 32KB chunks
                            if not data:
                                break
                            dest_fh.write(data)
                            callback(len(data), file_size)
                logger.info(f"Successfully transferred: {source_file}")
            except Exception as e:
                logger.error(f"Error transferring {source_file}: {str(e)}")
                raise
        
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