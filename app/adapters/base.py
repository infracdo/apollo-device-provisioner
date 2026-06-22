"""
Base Device Adapter

Abstract base class for all device adapters.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.utils.logging import logger


class BaseDeviceAdapter(ABC):
    """Base class for all device adapters"""
    
    def __init__(self, device_config: Dict[str, Any]):
        """
        Initialize device adapter
        
        Args:
            device_config: Device configuration dictionary containing:
                - id: Device ID
                - ip_address: Device IP address
                - port: Connection port
                - username: Authentication username
                - password: Authentication password
                - manufacturer: Device manufacturer
                - model: Device model (optional)
        """
        self.device_config = device_config
        self.connector = None
        self.is_connected = False
        
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to device
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close connection to device
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def execute_command(self, command: str) -> str:
        """
        Execute a command on the device
        
        Args:
            command: Command string to execute
            
        Returns:
            str: Command output
        """
        pass
    
    @abstractmethod
    async def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information
        
        Returns:
            dict: Device information including model, version, uptime, etc.
        """
        pass
    
    def log_command(self, command: str, output: str, level: str = "DEBUG"):
        """Log command execution"""
        device_name = self.device_config.get('name', self.device_config.get('ip_address'))
        log_msg = f"Device: {device_name} | Command: {command} | Output: {output[:200]}..."
        
        if level == "INFO":
            logger.info(log_msg)
        elif level == "WARNING":
            logger.warning(log_msg)
        elif level == "ERROR":
            logger.error(log_msg)
        else:
            logger.debug(log_msg)
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
