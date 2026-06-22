"""
SmartOLT Adapter

SmartOLT device implementation using REST API.
"""
from typing import Dict, Any, List, Optional
from app.adapters.olt.base_olt import BaseOLTAdapter
from app.connectors.api_connector import APIConnector
from app.utils.logging import logger


class SmartOLTAdapter(BaseOLTAdapter):
    """SmartOLT adapter implementation"""
    
    async def connect(self):
        """Establish connection to SmartOLT API"""
        self.connection = APIConnector(
            base_url=f"https://{self.config['host']}",
            headers={
                'Content-Type': 'application/json',
                'X-Token': self.config.get('api_token', '')
            },
            verify_ssl=self.config.get('verify_ssl', False),
            timeout=self.config.get('timeout', 30)
        )
        logger.info(f"Connected to SmartOLT API {self.config['host']}")
    
    async def provision_onu(self, onu_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provision ONU on SmartOLT via REST API
        
        SmartOLT uses REST API for provisioning
        """
        try:
            payload = {
                'serial_number': onu_config.get('serial_no'),
                'olt_id': onu_config.get('olt_id'),
                'pon_type': onu_config.get('pon_type', 'GPON'),
                'slot_number': onu_config.get('slot'),
                'pon_port': onu_config.get('port'),
                'ont_id': onu_config.get('ont_id'),
                'line_profile_id': onu_config.get('line_profile_id'),
                'service_profile_id': onu_config.get('service_profile_id'),
                'vlan': onu_config.get('vlan'),
                'description': onu_config.get('description', ''),
                'wan_mode': onu_config.get('wan_mode', 'dhcp'),
            }
            
            response = await self.connection.post('/api/v1/ont/provision', json=payload)
            
            if response.get('success'):
                ont_id = response.get('data', {}).get('ont_id')
                logger.info(f"Provisioned ONU {onu_config.get('serial_no')} on SmartOLT")
                return {
                    'status': 'success',
                    'ont_id': ont_id,
                    'message': 'ONU provisioned successfully',
                    'output': response
                }
            else:
                return {
                    'status': 'error',
                    'message': response.get('message', 'Unknown error')
                }
            
        except Exception as e:
            logger.error(f"Failed to provision ONU on SmartOLT: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def remove_onu(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Remove ONU from SmartOLT"""
        try:
            payload = {
                'olt_id': onu_location.get('olt_id'),
                'slot_number': onu_location.get('slot'),
                'pon_port': onu_location.get('port'),
                'ont_id': onu_location.get('ont_id')
            }
            
            response = await self.connection.delete('/api/v1/ont/remove', json=payload)
            
            if response.get('success'):
                logger.info(f"Removed ONU from SmartOLT")
                return {'status': 'success', 'message': 'ONU removed successfully'}
            else:
                return {'status': 'error', 'message': response.get('message', 'Unknown error')}
            
        except Exception as e:
            logger.error(f"Failed to remove ONU from SmartOLT: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def get_onts(self, slot: int, port: int) -> List[Dict[str, Any]]:
        """Get list of ONTs on port"""
        try:
            response = await self.connection.get(f'/api/v1/ont/list', params={
                'slot': slot,
                'port': port
            })
            
            if response.get('success'):
                return response.get('data', [])
            return []
        except Exception as e:
            logger.error(f"Failed to get ONTs from SmartOLT: {e}")
            return []
    
    async def get_ont_status(self, onu_location: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get ONU status"""
        try:
            response = await self.connection.get(f'/api/v1/ont/status', params={
                'slot': onu_location.get('slot'),
                'port': onu_location.get('port'),
                'ont_id': onu_location.get('ont_id')
            })
            
            if response.get('success'):
                return response.get('data')
            return None
        except Exception as e:
            logger.error(f"Failed to get ONU status from SmartOLT: {e}")
            return None
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get VLAN list"""
        try:
            response = await self.connection.get('/api/v1/vlan/list')
            if response.get('success'):
                return response.get('data', [])
            return []
        except Exception as e:
            logger.error(f"Failed to get VLANs from SmartOLT: {e}")
            return []
    
    async def get_boards(self) -> List[Dict[str, Any]]:
        """Get board information"""
        try:
            response = await self.connection.get('/api/v1/board/list')
            if response.get('success'):
                return response.get('data', [])
            return []
        except Exception as e:
            logger.error(f"Failed to get boards from SmartOLT: {e}")
            return []
    
    async def reboot_ont(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Reboot ONU"""
        try:
            payload = {
                'slot': onu_location.get('slot'),
                'port': onu_location.get('port'),
                'ont_id': onu_location.get('ont_id')
            }
            
            response = await self.connection.post('/api/v1/ont/reboot', json=payload)
            
            if response.get('success'):
                logger.info(f"Rebooted ONU on SmartOLT")
                return {'status': 'success', 'message': 'ONU rebooted successfully'}
            else:
                return {'status': 'error', 'message': response.get('message', 'Unknown error')}
            
        except Exception as e:
            logger.error(f"Failed to reboot ONU on SmartOLT: {e}")
            return {'status': 'error', 'message': str(e)}
