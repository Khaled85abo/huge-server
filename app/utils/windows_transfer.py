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
        
        # Initialize SSH client
        logger.info("Initializing SSH client...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Load private key
        logger.info(f"Loading private key from: {identity_file}")
        private_key = paramiko.RSAKey(filename=str(identity_file))
        logger.info("Private key loaded successfully")
        
        # Connect to source server
        source_server = server_configs['pisms']
        logger.info(f"Attempting to connect to source server: {source_server['host']}")
        ssh.connect(
            source_server['host'],
            username=source_server['user'],
            pkey=private_key
        )
        logger.info("Successfully connected to source server")
        
        # Get file size
        logger.info(f"Checking size of: {transfer_data['source_storage']}")
        stdin, stdout, stderr = ssh.exec_command(f"du -sb {transfer_data['source_storage']}")
        total_bytes = int(stdout.read().decode().split()[0])
        logger.info(f"Total bytes to transfer: {total_bytes}")
        
        # Setup SFTP
        logger.info("Setting up SFTP connection...")
        sftp = ssh.open_sftp()
        logger.info("SFTP connection established")
        
        # Initialize transfer tracking variables
        start_time = time.time()
        bytes_transferred = 0
        
        # Define progress callback
        def progress_callback(bytes_so_far, total_bytes):
            nonlocal bytes_transferred, start_time
            bytes_transferred = bytes_so_far
            
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
                    transfer_data['user_id'],
                    {
                        "type": "transfer_progress",
                        "progress": progress,
                        "current_file": transfer_data['source_storage'],
                        "bytes_transferred": bytes_transferred,
                        "total_bytes": total_bytes,
                        "estimated_time_remaining": int(estimated_seconds),
                        "error": None
                    }
                )
            )
        
        # Perform the transfer
        logger.info("Starting file transfer...")
        sftp.get(
            transfer_data['source_storage'],
            transfer_data['dest_storage'],
            callback=progress_callback
        )
        logger.info("File transfer completed")
        
        # Send final progress update
        await manager.broadcast_to_user(
            transfer_data['user_id'],
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
        logger.info("SSH connection closed")
        
        return {
            "status": "completed",
            "message": "Repository transfer successful",
            "source": transfer_data['source_storage'],
            "destination": transfer_data['dest_storage']
        }
        
    except Exception as e:
        logger.error(f"Windows transfer failed with error: {str(e)}")
        # Send error progress update
        await manager.broadcast_to_user(
            transfer_data['user_id'],
            {
                "type": "transfer_progress",
                "progress": -1,
                "error": str(e)
            }
        )
        raise Exception(f"Windows transfer failed: {str(e)}")