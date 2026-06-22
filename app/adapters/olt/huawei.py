"""
Huawei OLT Adapter

Implementation for Huawei OLT devices.
"""
import re
from typing import Dict, Any, List, Optional
from app.adapters.olt.base_olt import BaseOLTAdapter
from app.connectors.ssh_connector import SSHConnector
from app.connectors.telnet_connector import TelnetConnector
from app.utils.logging import logger


class HuaweiOLTAdapter(BaseOLTAdapter):
    """Huawei OLT implementation"""
    
    def __init__(self, device_config: Dict[str, Any]):
        super().__init__(device_config)
        self.command_mode = 0  # 0=normal, 1=enable, 2=config
        
    async def connect(self) -> bool:
        """Establish connection to Huawei OLT"""
        port = self.device_config.get('port', 22)
        
        if port == 23:
            self.connector = TelnetConnector(
                host=self.device_config['ip_address'],
                port=port,
                username=self.device_config['username'],
                password=self.device_config['password']
            )
        else:
            self.connector = SSHConnector(
                host=self.device_config['ip_address'],
                port=port,
                username=self.device_config['username'],
                password=self.device_config['password']
            )
        
        connected = await self.connector.connect()
        self.is_connected = connected
        return connected
    
    async def disconnect(self) -> bool:
        """Close connection"""
        if self.connector:
            return await self.connector.disconnect()
        return True
    
    async def execute_command(self, command: str) -> str:
        """Execute command on Huawei OLT"""
        if not self.is_connected or not self.connector:
            raise ConnectionError("Not connected to device")
        
        # Handle command mode changes
        if command == 'enable':
            self.command_mode = max(1, self.command_mode)
        elif command == 'config':
            self.command_mode = max(2, self.command_mode)
        elif command in ['quit', 'exit']:
            self.command_mode = max(0, self.command_mode - 1)
        
        output = await self.connector.execute(command)
        
        # Clean up page breaks
        output = output.replace("---- More ( Press 'Q' to break ) ----", "")
        output = re.sub(r'\x1b\[\d+D', '', output)  # Remove ANSI escape sequences
        
        self.log_command(command, output)
        return output
    
    async def provision_onu(self, onu_config: Dict[str, Any]) -> Dict[str, Any]:
        """Provision ONU on Huawei OLT"""
        try:
            # Extract parameters
            serial_no = onu_config['serial_no']
            frame = onu_config.get('frame', 0)
            slot = onu_config['slot']
            port = onu_config['port']
            line_profile = onu_config['line_profile_id']
            service_profile = onu_config['service_profile_id']
            vlan = onu_config['vlan']
            description = onu_config.get('description', '')
            wan_mode = onu_config.get('wan_mode', 'dhcp')
            
            # Enter configuration mode
            await self.execute_command("enable")
            await self.execute_command("config")
            await self.execute_command(f"interface gpon {frame}/{slot}")
            
            # Add ONU
            add_cmd = f'ont add {port} sn-auth {serial_no} omci ont-lineprofile-id {line_profile} ont-srvprofile-id {service_profile}'
            if description:
                add_cmd += f' desc "{description}"'
            
            output = await self.execute_command(add_cmd)
            
            # Extract ONT ID from output
            ont_id_match = re.search(r'ONT\s*ID\s*:\s*(\d+)', output)
            if not ont_id_match:
                return {
                    'status': 'error',
                    'message': 'Failed to add ONU - could not extract ONT ID',
                    'output': output
                }
            
            ont_id = int(ont_id_match.group(1))
            
            # Configure IP
            ip_cmd = f'ont ipconfig {port} {ont_id} ip-index 1 {wan_mode} vlan {vlan} priority 0'
            await self.execute_command(ip_cmd)
            
            # Configure WAN
            await self.execute_command(f'ont internet-config {port} {ont_id} ip-index 1')
            await self.execute_command(f'ont wan-config {port} {ont_id} ip-index 1 profile-id 0')
            await self.execute_command(f'ont policy-route-config {port} {ont_id} profile-id 0')
            
            # Enable ethernet ports
            for eth_port in range(1, 5):
                await self.execute_command(f'ont port route {port} {ont_id} eth {eth_port} enable')
            
            # Exit interface mode
            await self.execute_command('quit')
            
            logger.info(f"ONU {serial_no} provisioned successfully with ONT ID {ont_id}")
            
            return {
                'status': 'success',
                'ont_id': ont_id,
                'message': f'ONU provisioned successfully with ID {ont_id}'
            }
            
        except Exception as e:
            logger.error(f"Error provisioning ONU: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'ont_id': None
            }
    
    async def remove_onu(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Remove ONU from Huawei OLT"""
        try:
            frame = onu_location.get('frame', 0)
            slot = onu_location['slot']
            port = onu_location['port']
            ont_id = onu_location['ont_id']
            
            await self.execute_command("enable")
            await self.execute_command("config")
            await self.execute_command(f"interface gpon {frame}/{slot}")
            await self.execute_command(f"no ont {port} {ont_id}")
            await self.execute_command("quit")
            
            return {
                'status': 'success',
                'message': f'ONU at F/S/P/ID {frame}/{slot}/{port}/{ont_id} removed successfully'
            }
        except Exception as e:
            logger.error(f"Error removing ONU: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def get_onts(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get list of ONTs"""
        # Implementation would parse 'display ont info' output
        return []
    
    async def get_ont_status(self, ont_location: Dict[str, Any]) -> Dict[str, Any]:
        """Get ONT status"""
        # Implementation would parse 'display ont info' for specific ONT
        return {}
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get VLANs"""
        output = await self.execute_command("enable")
        output = await self.execute_command("display vlan all")
        # Parse VLAN output
        return []
    
    async def get_boards(self) -> List[Dict[str, Any]]:
        """Get board information"""
        output = await self.execute_command("display board 0")
        # Parse board output
        return []
    
    async def reboot_ont(self, ont_location: Dict[str, Any]) -> Dict[str, Any]:
        """Reboot ONT"""
        try:
            frame = ont_location.get('frame', 0)
            slot = ont_location['slot']
            port = ont_location['port']
            ont_id = ont_location['ont_id']
            
            await self.execute_command("enable")
            await self.execute_command("config")
            await self.execute_command(f"interface gpon {frame}/{slot}")
            await self.execute_command(f"ont reset {port} {ont_id}")
            await self.execute_command("quit")
            
            return {
                'status': 'success',
                'message': f'ONT {ont_id} reboot initiated'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def get_device_info(self) -> Dict[str, Any]:
        """Get device information"""
        output = await self.execute_command("display version")
        return {
            'manufacturer': 'Huawei',
            'raw_output': output
        }
