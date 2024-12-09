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
        logger.info("Starting windows transfer process...")
        source = transfer_data['source_storage']
        dest = transfer_data['dest_storage']
        user_id = transfer_data['user_id']
        
        # Initialize SSH client
        logger.info("Initializing SSH client...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Load private key and connect
        logger.info(f"Loading private key from: {identity_file}")
        private_key = paramiko.RSAKey(filename=str(identity_file))
        source_server = server_configs['pisms']
        ssh.connect(
            source_server['host'],
            username=source_server['user'],
            pkey=private_key
        )
        
        # Get total size
        logger.info(f"Checking size of: {source}")
        stdin, stdout, stderr = ssh.exec_command(f"du -sb {source}")
        total_bytes = int(stdout.read().decode().split()[0])
        logger.info(f"Total bytes to transfer: {total_bytes}")
        
        # Setup SFTP
        sftp = ssh.open_sftp()
        
        # Initialize transfer tracking
        start_time = time.time()
        bytes_transferred = 0
        current_file = ""
        
        # Get list of files to transfer
        stdin, stdout, stderr = ssh.exec_command(f"find {source} -type f")
        files_to_transfer = stdout.read().decode().split('\n')
        files_to_transfer = [f for f in files_to_transfer if f]  # Remove empty strings
        
        for source_file in files_to_transfer:
            # Calculate destination path
            rel_path = Path(source_file).relative_to(source)
            dest_file = str(Path(dest) / rel_path)
            current_file = source_file
            
            # Create destination directory if it doesn't exist
            dest_dir = str(Path(dest_file).parent)
            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {dest_dir}")
            
            # Get file size
            file_attr = sftp.stat(source_file)
            file_size = file_attr.st_size
            
            def progress_callback(bytes_so_far, total_bytes):
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
            
            # Transfer the file
            logger.info(f"Transferring file: {current_file}")
            sftp.get(source_file, dest_file, callback=progress_callback)
        
        # Send final progress update
        await manager.broadcast_to_user(
            user_id,
            {
                "type": "transfer_progress",
                "progress": 100,
                "current_file": "Complete",
                "bytes_transferred": total_bytes,
                "total_bytes": total_bytes,
                "estimated_time_remaining": 0,
                "error": None
            }
        )
        
        ssh.close()
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