"""
API Connector

HTTP/HTTPS REST API connection handler using httpx.
"""
import asyncio
import httpx
from typing import Dict, Any, Optional
from app.utils.logging import logger
from app.config import settings


class APIConnector:
    """REST API connection handler"""
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        verify_ssl: bool = False
    ):
        """Initialize API connector"""
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        
        self.default_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        if api_key:
            self.default_headers['X-Token'] = api_key
            
        if headers:
            self.default_headers.update(headers)
        
        self.client: Optional[httpx.AsyncClient] = None
        self.is_connected = False
        
    async def connect(self) -> bool:
        """Initialize HTTP client"""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            self.is_connected = True
            logger.info(f"API client initialized for {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize API client: {str(e)}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Close HTTP client"""
        try:
            if self.client:
                await self.client.aclose()
            self.is_connected = False
            logger.info(f"API client closed for {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"Error closing API client: {str(e)}")
            return False
    
    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send GET request
        
        Args:
            path: API endpoint path
            params: Query parameters
            
        Returns:
            dict: Response data
        """
        if not self.is_connected or not self.client:
            raise ConnectionError("API client not connected")
        
        try:
            response = await self.client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"GET request failed for {path}: {str(e)}")
            raise
    
    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send POST request
        
        Args:
            path: API endpoint path
            data: Form data
            json: JSON data
            
        Returns:
            dict: Response data
        """
        if not self.is_connected or not self.client:
            raise ConnectionError("API client not connected")
        
        try:
            response = await self.client.post(path, data=data, json=json)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"POST request failed for {path}: {str(e)}")
            raise
    
    async def put(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send PUT request"""
        if not self.is_connected or not self.client:
            raise ConnectionError("API client not connected")
        
        try:
            response = await self.client.put(path, data=data, json=json)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"PUT request failed for {path}: {str(e)}")
            raise
    
    async def delete(self, path: str) -> Dict[str, Any]:
        """Send DELETE request"""
        if not self.is_connected or not self.client:
            raise ConnectionError("API client not connected")
        
        try:
            response = await self.client.delete(path)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"DELETE request failed for {path}: {str(e)}")
            raise
