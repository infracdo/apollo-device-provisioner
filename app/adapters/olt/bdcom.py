"""
BDCOM OLT Adapter

BDCOM OLT device implementation using SSH/Telnet.
"""
from typing import Dict, Any, List, Optional
from app.adapters.olt.base_olt import BaseOLTAdapter
from app.connectors.ssh_connector import SSHConnector
from app.connectors.telnet_connector import TelnetConnector
from app.utils.logging import logger
import re


class BDCOMOLTAdapter(BaseOLTAdapter):
    """BDCOM OLT adapter implementation"""
    
    async def connect(self):
        """Establish connection to BDCOM OLT"""
        if self.config.get('protocol', 'ssh') == 'ssh':
            self.connection = SSHConnector(
                host=self.config['host'],
                port=self.config.get('port', 22),
                username=self.config['username'],
                password=self.config['password'],
                timeout=self.config.get('timeout', 30)
            )
        else:
            self.connection = TelnetConnector(
                host=self.config['host'],
                port=self.config.get('port', 23),
                username=self.config['username'],
                password=self.config['password'],
                timeout=self.config.get('timeout', 30)
            )
        
        await self.connection.connect()
        logger.info(f"Connected to BDCOM OLT {self.config['host']}")
        
        # Initial setup
        await self.connection.send_command("enable")
        if 'enable_password' in self.config:
            await self.connection.send_command(self.config['enable_password'])
        await self.connection.send_command("config")
    
    async def provision_onu(self, onu_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provision ONU on BDCOM OLT
        
        BDCOM provisioning sequence:
        1. Navigate to PON interface
        2. Add ONU with serial number
        3. Configure service profile
        4. Set VLAN
        """
        try:
            slot = onu_config.get('slot')
            port = onu_config.get('port')
            ont_id = onu_config.get('ont_id')
            serial_no = onu_config.get('serial_no')
            onu_type = onu_config.get('onu_type', 'ONU')
            vlan = onu_config.get('vlan')
            
            # Enter interface mode
            interface_cmd = f"interface EPON0/{slot}:{port}"
            await self.connection.send_command(interface_cmd)
            
            # Register ONU
            register_cmd = f"epon bind-onu mac {serial_no} {ont_id}"
            output = await self.connection.send_command(register_cmd)
            
            # Exit interface mode
            await self.connection.send_command("exit")
            
            # Configure ONU
            onu_interface = f"interface EPON0/{slot}:{port}.{ont_id}"
            await self.connection.send_command(onu_interface)
            
            # Set ONU type
            await self.connection.send_command(f"epon onu-type {onu_type}")
            
            # Set VLAN
            if vlan:
                await self.connection.send_command(f"vlan {vlan}")
            
            # Set description
            if 'description' in onu_config:
                await self.connection.send_command(f"description {onu_config['description']}")
            
            # Exit and save
            await self.connection.send_command("exit")
            await self.connection.send_command("exit")
            await self.connection.send_command("write")
            
            logger.info(f"Provisioned ONU {serial_no} on BDCOM OLT")
            return {
                'status': 'success',
                'ont_id': ont_id,
                'message': 'ONU provisioned successfully',
                'output': output
            }
            
        except Exception as e:
            logger.error(f"Failed to provision ONU on BDCOM: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def remove_onu(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Remove ONU from BDCOM OLT"""
        try:
            slot = onu_location.get('slot')
            port = onu_location.get('port')
            ont_id = onu_location.get('ont_id')
            
            # Enter interface mode
            interface_cmd = f"interface EPON0/{slot}:{port}"
            await self.connection.send_command(interface_cmd)
            
            # Remove ONU
            remove_cmd = f"no epon bind-onu {ont_id}"
            await self.connection.send_command(remove_cmd)
            
            # Exit and save
            await self.connection.send_command("exit")
            await self.connection.send_command("exit")
            await self.connection.send_command("write")
            
            logger.info(f"Removed ONU {ont_id} from BDCOM OLT")
            return {'status': 'success', 'message': 'ONU removed successfully'}
            
        except Exception as e:
            logger.error(f"Failed to remove ONU from BDCOM: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def get_onts(self, slot: int, port: int) -> List[Dict[str, Any]]:
        """Get list of ONTs on port"""
        try:
            cmd = f"show epon onu-information EPON0/{slot}:{port}"
            output = await self.connection.send_command(cmd)
            
            # Parse output
            onts = []
            for line in output.split('\n'):
                # Parse ONU information
                if 'EPON0' in line:
                    # Extract ONU details from output
                    pass
            
            return onts
        except Exception as e:
            logger.error(f"Failed to get ONTs from BDCOM: {e}")
            return []
    
    async def get_ont_status(self, onu_location: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get ONU status"""
        try:
            slot = onu_location.get('slot')
            port = onu_location.get('port')
            ont_id = onu_location.get('ont_id')
            
            cmd = f"show epon onu-information EPON0/{slot}:{port}.{ont_id}"
            output = await self.connection.send_command(cmd)
            
            # Parse status from output
            return {'status': 'online', 'output': output}
        except Exception as e:
            logger.error(f"Failed to get ONU status from BDCOM: {e}")
            return None
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get VLAN list"""
        try:
            output = await self.connection.send_command("show vlan")
            # Parse VLAN information
            return []
        except Exception as e:
            logger.error(f"Failed to get VLANs from BDCOM: {e}")
            return []
    
    async def get_boards(self) -> List[Dict[str, Any]]:
        """Get board information"""
        try:
            output = await self.connection.send_command("show card")
            # Parse board information
            return []
        except Exception as e:
            logger.error(f"Failed to get boards from BDCOM: {e}")
            return []
    
    async def reboot_ont(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Reboot ONU"""
        try:
            slot = onu_location.get('slot')
            port = onu_location.get('port')
            ont_id = onu_location.get('ont_id')
            
            # Enter interface mode
            interface_cmd = f"interface EPON0/{slot}:{port}"
            await self.connection.send_command(interface_cmd)
            
            # Reboot ONU
            reboot_cmd = f"epon onu reboot {ont_id}"
            await self.connection.send_command(reboot_cmd)
            
            await self.connection.send_command("exit")
            
            logger.info(f"Rebooted ONU {ont_id} on BDCOM OLT")
            return {'status': 'success', 'message': 'ONU rebooted successfully'}
            
        except Exception as e:
            logger.error(f"Failed to reboot ONU on BDCOM: {e}")
            return {'status': 'error', 'message': str(e)}
