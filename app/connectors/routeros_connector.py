"""
RouterOS Connector

Mikrotik RouterOS API connection handler using librouteros.
"""
import asyncio
from typing import Optional, List, Dict, Any
import librouteros
from app.utils.logging import logger


class RouterOSConnector:
    """RouterOS API connection handler"""
    
    def __init__(
        self,
        host: str,
        port: int = 8728,
        username: str = "",
        password: str = "",
        timeout: int = 30
    ):
        """Initialize RouterOS connector"""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.api: Optional[Any] = None
        self.is_connected = False
        
    async def connect(self) -> bool:
        """Establish RouterOS API connection"""
        try:
            # librouteros is synchronous, so we run it in a thread
            self.api = await asyncio.to_thread(
                self._connect_sync
            )
            self.is_connected = True
            logger.info(f"RouterOS API connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"RouterOS connection failed to {self.host}:{self.port} - {str(e)}")
            self.is_connected = False
            return False
    
    def _connect_sync(self):
        """Synchronous connection method"""
        api = librouteros.connect(
            host=self.host,
            username=self.username,
            password=self.password,
            port=self.port,
            timeout=self.timeout
        )
        return api
    
    async def disconnect(self) -> bool:
        """Close RouterOS connection"""
        try:
            if self.api:
                await asyncio.to_thread(self.api.close)
            self.is_connected = False
            logger.info(f"RouterOS disconnected from {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting RouterOS: {str(e)}")
            return False
    
    async def execute(self, path: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute RouterOS API command
        
        Args:
            path: API path (e.g., '/queue/simple/print')
            **kwargs: Command arguments
            
        Returns:
            list: Command results
        """
        if not self.is_connected or not self.api:
            raise ConnectionError("Not connected to RouterOS API")
        
        try:
            result = await asyncio.to_thread(
                self._execute_sync,
                path,
                **kwargs
            )
            return result
        except Exception as e:
            logger.error(f"Error executing RouterOS command: {str(e)}")
            raise
    
    def _execute_sync(self, path: str, **kwargs):
        """Synchronous command execution"""
        return list(self.api(cmd=path, **kwargs))
    
    async def add(self, path: str, **params) -> Optional[str]:
        """Add item using RouterOS API"""
        result = await self.execute(f"{path}/add", **params)
        return result[0].get('ret') if result else None
    
    async def set(self, path: str, id: str, **params) -> bool:
        """Update item using RouterOS API"""
        try:
            await self.execute(f"{path}/set", **{'.id': id, **params})
            return True
        except:
            return False
    
    async def remove(self, path: str, id: str) -> bool:
        """Remove item using RouterOS API"""
        try:
            await self.execute(f"{path}/remove", **{'.id': id})
            return True
        except:
            return False
    
    async def get_all(self, path: str) -> List[Dict[str, Any]]:
        """Get all items from path"""
        return await self.execute(f"{path}/print")
