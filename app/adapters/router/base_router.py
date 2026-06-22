"""
Base Router Adapter

Abstract base class for router adapters.
"""
from abc import abstractmethod
from typing import Dict, Any, List, Optional
from app.adapters.base import BaseDeviceAdapter


class BaseRouterAdapter(BaseDeviceAdapter):
    """Base class for router adapters"""
    
    @abstractmethod
    async def create_queue(self, queue_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create bandwidth queue
        
        Args:
            queue_config: Queue configuration dictionary containing:
                - name: Queue name (required)
                - target_ip: Target IP or subnet (required)
                - upload_kbps: Upload speed in Kbps (required)
                - download_kbps: Download speed in Kbps (required)
                - min_upload_kbps: Guaranteed upload (optional)
                - min_download_kbps: Guaranteed download (optional)
                - parent_queue: Parent queue name for hierarchical QoS (optional)
                - priority: Queue priority 1-8 (optional)
                - comment: Description (optional)
        
        Returns:
            dict: Creation result containing:
                - status: 'success' or 'error'
                - queue_id: Queue identifier
                - message: Status message
        """
        pass
    
    @abstractmethod
    async def update_queue(self, queue_id: str, queue_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update existing queue
        
        Args:
            queue_id: Queue identifier
            queue_config: Updated queue configuration
        
        Returns:
            dict: Update result
        """
        pass
    
    @abstractmethod
    async def delete_queue(self, queue_id: str) -> Dict[str, Any]:
        """
        Delete queue
        
        Args:
            queue_id: Queue identifier
        
        Returns:
            dict: Deletion result
        """
        pass
    
    @abstractmethod
    async def get_queues(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get list of queues
        
        Args:
            filters: Optional filters (name, target, parent, etc.)
        
        Returns:
            list: List of queue dictionaries
        """
        pass
    
    @abstractmethod
    async def create_hotspot_user(self, user_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create hotspot user
        
        Args:
            user_config: User configuration dictionary
        
        Returns:
            dict: Creation result
        """
        pass
    
    @abstractmethod
    async def disconnect_user(self, username: str) -> Dict[str, Any]:
        """
        Disconnect active user
        
        Args:
            username: Username to disconnect
        
        Returns:
            dict: Disconnection result
        """
        pass
    
    async def get_active_connections(self) -> List[Dict[str, Any]]:
        """
        Get active connections/users
        
        Returns:
            list: List of active connections
        """
        # Override in subclass if supported
        return []
    
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Get router interfaces
        
        Returns:
            list: List of interface dictionaries
        """
        # Override in subclass if supported
        return []
