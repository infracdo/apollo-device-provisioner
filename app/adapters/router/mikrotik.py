"""
Mikrotik Router Adapter

Mikrotik RouterOS implementation using RouterOS API.
"""
from typing import Dict, Any, List, Optional
from app.adapters.router.base_router import BaseRouterAdapter
from app.connectors.routeros_connector import RouterOSConnector
from app.utils.logging import logger


class MikrotikAdapter(BaseRouterAdapter):
    """Mikrotik router adapter implementation"""
    
    async def connect(self):
        """Establish connection to Mikrotik RouterOS API"""
        self.connection = RouterOSConnector(
            host=self.config['host'],
            port=self.config.get('port', 8728),
            username=self.config['username'],
            password=self.config['password'],
            timeout=self.config.get('timeout', 30),
            use_ssl=self.config.get('use_ssl', False)
        )
        
        await self.connection.connect()
        logger.info(f"Connected to Mikrotik {self.config['host']}")
    
    async def create_queue(self, queue_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create queue on Mikrotik
        
        Creates both upload and download queues in queue simple
        """
        try:
            name = queue_config.get('name')
            target_ip = queue_config.get('target_ip')
            upload_kbps = queue_config.get('upload_kbps')
            download_kbps = queue_config.get('download_kbps')
            
            # Create queue simple entry
            params = {
                'name': name,
                'target': target_ip,
                'max-limit': f"{upload_kbps}k/{download_kbps}k",
            }
            
            # Optional parameters
            if queue_config.get('min_upload_kbps') and queue_config.get('min_download_kbps'):
                params['limit-at'] = f"{queue_config['min_upload_kbps']}k/{queue_config['min_download_kbps']}k"
            
            if queue_config.get('priority'):
                params['priority'] = f"{queue_config['priority']}/{queue_config['priority']}"
            
            if queue_config.get('parent_queue'):
                params['parent'] = queue_config['parent_queue']
            
            if queue_config.get('comment'):
                params['comment'] = queue_config['comment']
            
            # Execute command
            result = await self.connection.add('/queue/simple', params)
            
            logger.info(f"Created queue {name} on Mikrotik")
            return {
                'status': 'success',
                'queue_id': result,
                'message': 'Queue created successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to create queue on Mikrotik: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def update_queue(self, queue_id: str, queue_config: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing queue"""
        try:
            params = {}
            
            # Build update parameters
            if 'upload_kbps' in queue_config and 'download_kbps' in queue_config:
                params['max-limit'] = f"{queue_config['upload_kbps']}k/{queue_config['download_kbps']}k"
            
            if 'min_upload_kbps' in queue_config and 'min_download_kbps' in queue_config:
                params['limit-at'] = f"{queue_config['min_upload_kbps']}k/{queue_config['min_download_kbps']}k"
            
            if 'priority' in queue_config:
                params['priority'] = f"{queue_config['priority']}/{queue_config['priority']}"
            
            if 'disabled' in queue_config:
                params['disabled'] = 'yes' if queue_config['disabled'] else 'no'
            
            # Execute update
            await self.connection.set('/queue/simple', queue_id, params)
            
            logger.info(f"Updated queue {queue_id} on Mikrotik")
            return {
                'status': 'success',
                'message': 'Queue updated successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to update queue on Mikrotik: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def delete_queue(self, queue_id: str) -> Dict[str, Any]:
        """Delete queue"""
        try:
            await self.connection.remove('/queue/simple', queue_id)
            
            logger.info(f"Deleted queue {queue_id} from Mikrotik")
            return {
                'status': 'success',
                'message': 'Queue deleted successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to delete queue from Mikrotik: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def get_queues(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get queue list"""
        try:
            queues = await self.connection.get_all('/queue/simple')
            
            # Apply filters if provided
            if filters:
                # Add filtering logic here
                pass
            
            return queues
        except Exception as e:
            logger.error(f"Failed to get queues from Mikrotik: {e}")
            return []
    
    async def create_hotspot_user(self, user_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create hotspot user"""
        try:
            params = {
                'name': user_config.get('username'),
                'password': user_config.get('password'),
            }
            
            # Optional parameters
            if user_config.get('profile'):
                params['profile'] = user_config['profile']
            
            if user_config.get('mac_address'):
                params['mac-address'] = user_config['mac_address']
            
            if user_config.get('upload_kbps'):
                params['limit-bytes-in'] = user_config['upload_kbps'] * 1024
            
            if user_config.get('download_kbps'):
                params['limit-bytes-out'] = user_config['download_kbps'] * 1024
            
            if user_config.get('comment'):
                params['comment'] = user_config['comment']
            
            # Execute command
            result = await self.connection.add('/ip/hotspot/user', params)
            
            logger.info(f"Created hotspot user {user_config.get('username')} on Mikrotik")
            return {
                'status': 'success',
                'user_id': result,
                'message': 'Hotspot user created successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to create hotspot user on Mikrotik: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def disconnect_user(self, username: str) -> Dict[str, Any]:
        """Disconnect hotspot user"""
        try:
            # Find active session
            sessions = await self.connection.get_all('/ip/hotspot/active')
            
            for session in sessions:
                if session.get('user') == username:
                    await self.connection.remove('/ip/hotspot/active', session.get('.id'))
                    logger.info(f"Disconnected user {username} from Mikrotik")
                    return {
                        'status': 'success',
                        'message': f'User {username} disconnected successfully'
                    }
            
            return {
                'status': 'error',
                'message': f'User {username} not found in active sessions'
            }
            
        except Exception as e:
            logger.error(f"Failed to disconnect user from Mikrotik: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
