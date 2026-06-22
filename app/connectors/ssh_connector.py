"""
SSH Connector

SSH connection handler using Paramiko.
"""
import asyncio
import paramiko
from typing import Optional
from app.utils.logging import logger
from app.config import settings


class SSHConnector:
    """SSH connection handler"""
    
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str = "",
        timeout: int = 30
    ):
        """Initialize SSH connector"""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None
        self.is_connected = False
        
    async def connect(self) -> bool:
        """Establish SSH connection"""
        try:
            # Use run_in_executor for Python 3.8 compatibility (asyncio.to_thread is 3.9+)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._connect_sync)
            self.is_connected = True
            logger.info(f"SSH connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"SSH connection failed to {self.host}:{self.port} - {str(e)}")
            logger.exception("Full traceback:")  # Log full exception details
            self.is_connected = False
            return False
    
    def _connect_sync(self):
        """Synchronous connection method"""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect to the SSH server
        # This will work with legacy algorithms if Paramiko is properly configured
        self.client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False
        )
        
        # Invoke shell for interactive commands
        self.channel = self.client.invoke_shell()
        self.channel.settimeout(self.timeout)
    
    async def disconnect(self) -> bool:
        """Close SSH connection"""
        try:
            if self.channel:
                self.channel.close()
            if self.client:
                self.client.close()
            self.is_connected = False
            logger.info(f"SSH disconnected from {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting SSH: {str(e)}")
            return False
    
    async def execute(self, command: str) -> str:
        """
        Execute command over SSH
        
        Args:
            command: Command to execute
            
        Returns:
            str: Command output
        """
        if not self.is_connected or not self.channel:
            raise ConnectionError("Not connected to SSH server")
        
        try:
            # Send command (use run_in_executor for Python 3.8 compatibility)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.channel.send, command + "\n")
            
            # Read output
            output = await self._read_until_prompt()
            return output
        except Exception as e:
            logger.error(f"Error executing SSH command: {str(e)}")
            raise
    
    async def _read_until_prompt(self, timeout: int = 10) -> str:
        """Read output until prompt is detected"""
        output = ""
        loop = asyncio.get_event_loop()
        start_time = loop.time()
        
        while True:
            if loop.time() - start_time > timeout:
                break
                
            if self.channel and self.channel.recv_ready():
                # Use run_in_executor for Python 3.8 compatibility
                chunk = await loop.run_in_executor(None, self.channel.recv, 4096)
                output += chunk.decode('utf-8', errors='ignore')
                
                # Check for common prompts
                if any(p in output for p in ['>', '#', '$']):
                    await asyncio.sleep(0.1)  # Small delay to catch remaining output
                    if self.channel.recv_ready():
                        chunk = await loop.run_in_executor(None, self.channel.recv, 4096)
                        output += chunk.decode('utf-8', errors='ignore')
                    break
            else:
                await asyncio.sleep(0.1)
        
        return output
