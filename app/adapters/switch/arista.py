"""
Arista EOS Switch Adapter Implementation
"""
import re
import logging
from typing import Dict, List, Any, Optional
from app.adapters.switch.base_switch import BaseSwitchAdapter
from app.connectors.ssh_connector import SSHConnector

logger = logging.getLogger(__name__)


class AristaAdapter(BaseSwitchAdapter):
    """Adapter for Arista EOS switches"""
    
    def __init__(self, device):
        super().__init__(device)
        self.connector = None
    
    async def connect(self) -> bool:
        """Connect to Arista switch"""
        try:
            if self.device.protocol == 'ssh':
                self.connector = SSHConnector(
                    host=self.device.host,
                    port=self.device.port or 22,
                    username=self.device.username,
                    password=self.device.password,
                    timeout=self.device.timeout or 30
                )
            else:
                logger.error(f"Unsupported protocol: {self.device.protocol}")
                return False
            
            connected = await self.connector.connect()
            
            if connected:
                # Disable pagination for full command output
                try:
                    await self.execute_command("terminal length 0")
                except Exception as e:
                    logger.debug(f"Could not set terminal length: {str(e)}")
                
                # Enter privileged mode
                await self._enter_enable_mode()
                logger.info(f"Connected to Arista switch {self.device.host}")
            
            return connected
            
        except Exception as e:
            logger.error(f"Error connecting to Arista switch: {str(e)}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Arista switch"""
        if self.connector:
            return await self.connector.disconnect()
        return True
    
    async def execute_command(self, command: str) -> str:
        """Execute command on Arista switch"""
        if not self.connector:
            raise ConnectionError("Not connected to switch")
        return await self.connector.execute(command)
    
    async def _enter_enable_mode(self):
        """Enter privileged EXEC mode"""
        try:
            # Send enable command
            output = await self.execute_command("enable")
            
            # Check if password prompt
            if "password" in output.lower():
                enable_password = self.device.config.get('enable_password') or self.device.password
                await self.connector.channel.send(enable_password + '\n')
        except Exception as e:
            logger.warning(f"Could not enter enable mode: {str(e)}")
    
    # Interface Management
    
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """Get list of all interfaces
        
        Try multiple commands:
        1. show interfaces status (preferred for Arista)
        2. show interfaces description (fallback)
        """
        try:
            # Try show interfaces status first (Arista's standard command)
            output = await self.execute_command("show interfaces status")
            interfaces = self._parse_interfaces_status(output)
            if interfaces:
                return interfaces
        except Exception as e:
            logger.debug(f"show interfaces status failed: {str(e)}")
        
        try:
            # Fallback to show interfaces description
            output = await self.execute_command("show interfaces description")
            return self._parse_interfaces_description(output)
        except Exception as e:
            logger.error(f"Error getting interfaces: {str(e)}")
            return []
    
    def _parse_interfaces_status(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show interfaces status' output
        
        Example format:
        Port       Name   Status       Vlan     Duplex Speed  Type
        Et1               connected    1        full   10G    10GBASE-SR
        Ma1               connected    routed   a-full a-1G   10/100/1000
        """
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers, separators, empty lines
            if not line or '----' in line or line.startswith('Port'):
                continue
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Skip command echoes
            parts = line.split()
            if len(parts) < 2:
                continue
            
            if parts[0].lower() in ['show', 'interface', 'interfaces']:
                continue
            
            # Parse interface line
            # Arista format: Et1  description  connected  1  full  10G  10GBASE-SR
            if len(parts) >= 3:
                interface_name = parts[0]
                
                # Find status (connected/disabled/notconnect/etc)
                status = 'unknown'
                vlan = '1'
                duplex = 'auto'
                speed = 'auto'
                description = ''
                
                # Parse fields - Arista format varies
                for i, part in enumerate(parts[1:], 1):
                    if part.lower() in ['connected', 'notconnect', 'disabled', 'err-disabled', 'inactive']:
                        status = 'up' if part.lower() == 'connected' else 'down'
                        # VLAN is typically next
                        if i+1 < len(parts):
                            vlan_candidate = parts[i+1]
                            if vlan_candidate.isdigit() or vlan_candidate.lower() == 'routed':
                                vlan = vlan_candidate
                        # Duplex is typically after VLAN
                        if i+2 < len(parts):
                            duplex = parts[i+2]
                        # Speed is typically after duplex
                        if i+3 < len(parts):
                            speed = parts[i+3]
                        break
                    elif not part.lower() in ['connected', 'notconnect', 'disabled']:
                        # This might be description
                        if i == 1 and not part.isdigit():
                            description = part
                
                interfaces.append({
                    'name': interface_name,
                    'status': status,
                    'description': description,
                    'speed': speed,
                    'duplex': duplex,
                    'vlan': vlan
                })
        
        return interfaces
    
    def _parse_interfaces_description(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show interfaces description' output"""
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line or '----' in line or line.startswith('Interface'):
                continue
            if line.endswith('#') or line.endswith('>'):
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                interface_name = parts[0]
                status = parts[1] if len(parts) > 1 else 'unknown'
                description = ' '.join(parts[2:]) if len(parts) > 2 else ''
                
                interfaces.append({
                    'name': interface_name,
                    'status': status,
                    'description': description,
                    'speed': 'auto',
                    'duplex': 'auto',
                    'vlan': '1'
                })
        
        return interfaces
    
    async def get_interface_status(self, interface: str) -> Dict[str, Any]:
        """Get detailed status of specific interface"""
        try:
            output = await self.execute_command(f"show interfaces {interface}")
            return self._parse_interface_detail(output, interface)
        except Exception as e:
            logger.error(f"Error getting interface status: {str(e)}")
            return {}
    
    def _parse_interface_detail(self, output: str, interface: str) -> Dict[str, Any]:
        """Parse detailed interface output"""
        info = {'name': interface}
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            
            if 'line protocol is' in line.lower():
                if 'up' in line.lower():
                    info['status'] = 'up'
                    info['protocol'] = 'up'
                else:
                    info['status'] = 'down'
                    info['protocol'] = 'down'
            
            elif 'Hardware is' in line or 'hardware' in line.lower():
                match = re.search(r'address is ([0-9a-f:.]+)', line, re.I)
                if match:
                    info['mac_address'] = match.group(1)
            
            elif 'MTU' in line:
                match = re.search(r'MTU (\d+)', line)
                if match:
                    info['mtu'] = int(match.group(1))
            
            elif 'BW' in line or 'bandwidth' in line.lower():
                match = re.search(r'BW (\d+)', line)
                if match:
                    info['bandwidth'] = int(match.group(1))
        
        return info
    
    # VLAN Management
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get all VLANs"""
        try:
            output = await self.execute_command("show vlan")
            return self._parse_vlans(output)
        except Exception as e:
            logger.error(f"Error getting VLANs: {str(e)}")
            return []
    
    def _parse_vlans(self, output: str) -> List[Dict[str, Any]]:
        """Parse VLAN output
        
        Example format:
        VLAN  Name                             Status    Ports
        ----- -------------------------------- --------- -------------------------------
        1     default                          active    Et1, Et2, Et3
        """
        vlans = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers and separators
            if not line or '----' in line or line.startswith('VLAN'):
                continue
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Parse VLAN line
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                vlan_id = parts[0]
                name = parts[1]
                status = parts[2]
                
                vlans.append({
                    'id': vlan_id,
                    'name': name,
                    'status': status
                })
        
        return vlans
    
    # Discovery Methods
    
    async def discover_commands(self) -> Dict[str, Any]:
        """Discover which commands are supported"""
        commands = [
            ("show version", "System version and hardware info"),
            ("show inventory", "Hardware inventory"),
            ("show interfaces", "All interfaces detailed"),
            ("show interfaces status", "Interface status summary"),
            ("show interfaces description", "Interface descriptions"),
            ("show vlan", "VLAN database"),
            ("show vlan brief", "VLAN brief summary"),
            ("show mac address-table", "MAC address table"),
            ("show arp", "ARP table"),
            ("show ip route", "Routing table"),
            ("show spanning-tree", "Spanning tree status"),
            ("show running-config", "Running configuration"),
            ("show startup-config", "Startup configuration"),
        ]
        
        results = {
            'successful_commands': [],
            'failed_commands': [],
            'total_tested': len(commands),
            'success_rate': 0
        }
        
        for command, description in commands:
            try:
                output = await self.execute_command(command)
                
                # Check if command failed
                if any(err in output.lower() for err in ['invalid', 'unknown command', 'error', '% incomplete']):
                    results['failed_commands'].append({
                        'command': command,
                        'description': description,
                        'error': output[:200]
                    })
                else:
                    results['successful_commands'].append({
                        'command': command,
                        'description': description,
                        'output_size': len(output)
                    })
            except Exception as e:
                results['failed_commands'].append({
                    'command': command,
                    'description': description,
                    'error': str(e)
                })
        
        results['success_rate'] = len(results['successful_commands']) / len(commands) * 100
        return results
    
    async def discover_vlan_port_mapping(self) -> Dict[str, Any]:
        """Discover VLAN to port mappings"""
        try:
            vlans = await self.get_vlans()
            interfaces = await self.get_interfaces()
            
            # Get detailed VLAN info
            vlan_output = await self.execute_command("show vlan")
            port_mappings = self._parse_vlan_port_mapping(vlan_output)
            
            return {
                'vlans': vlans,
                'total_vlans': len(vlans),
                'interfaces': interfaces,
                'total_interfaces': len(interfaces),
                'port_vlan_mappings': port_mappings
            }
        except Exception as e:
            logger.error(f"Error discovering VLAN mappings: {str(e)}")
            return {}
    
    def _parse_vlan_port_mapping(self, output: str) -> List[Dict[str, Any]]:
        """Parse VLAN to port mappings from show vlan output"""
        mappings = []
        current_vlan = None
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line or '----' in line:
                continue
            
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                # New VLAN entry
                current_vlan = parts[0]
                vlan_name = parts[1]
                status = parts[2]
                
                # Ports might be on same line
                if len(parts) > 3:
                    ports = ' '.join(parts[3:])
                    for port in ports.split(','):
                        port = port.strip()
                        if port:
                            mappings.append({
                                'interface': port,
                                'vlan': current_vlan,
                                'vlan_name': vlan_name,
                                'mode': 'access',
                                'status': status
                            })
            elif current_vlan and parts:
                # Continuation of ports for current VLAN
                ports = ' '.join(parts)
                for port in ports.split(','):
                    port = port.strip()
                    if port and not port.startswith('VLAN'):
                        mappings.append({
                            'interface': port,
                            'vlan': current_vlan,
                            'mode': 'access',
                            'status': 'active'
                        })
        
        return mappings
    
    async def discover_capabilities(self) -> Dict[str, Any]:
        """Discover switch capabilities"""
        try:
            # Get version info
            version_output = await self.execute_command("show version")
            version_info = self._parse_version(version_output)
            
            # Get interface count
            interfaces = await self.get_interfaces()
            
            # Get VLAN info
            vlans = await self.get_vlans()
            
            capabilities = {
                'manufacturer': 'Arista',
                'model': version_info.get('model', 'Unknown'),
                'os_version': version_info.get('version', 'Unknown'),
                'serial': version_info.get('serial', 'Unknown'),
                'hostname': version_info.get('hostname', 'Unknown'),
                'uptime': version_info.get('uptime', 'Unknown'),
                'supported_features': [
                    'vlan_management',
                    'interface_configuration',
                    'mac_address_table',
                    'arp_table',
                    'routing',
                    'spanning_tree',
                    'trunk_ports',
                    'access_ports',
                    'port_statistics',
                    'configuration_save',
                    'layer3_routing'
                ],
                'port_count': len(interfaces),
                'vlan_range': {
                    'min': 1,
                    'max': 4094,
                    'configured_vlans': len(vlans),
                    'min_configured': min([int(v['id']) for v in vlans]) if vlans else None,
                    'max_configured': max([int(v['id']) for v in vlans]) if vlans else None
                },
                'interface_types': list(set([i['name'].split('0')[0] if '0' in i['name'] else i['name'][:2] for i in interfaces])),
                'protocol': self.device.protocol,
                'management_ip': self.device.host
            }
            
            return capabilities
        except Exception as e:
            logger.error(f"Error discovering capabilities: {str(e)}")
            return {}
    
    def _parse_version(self, output: str) -> Dict[str, Any]:
        """Parse show version output
        
        Example:
        Arista DCS-7060CX-32S-R
        Hardware version: 22.00
        Serial number: JPE17490333
        Software image version: 4.26.6M
        Uptime: 5 hours and 4 minutes
        """
        info = {}
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Model - first line typically
            if line.startswith('Arista '):
                info['model'] = line.replace('Arista ', '').strip()
            
            # Serial number
            if 'Serial number' in line or 'serial number' in line.lower():
                match = re.search(r':\s*(\S+)', line)
                if match:
                    info['serial'] = match.group(1)
            
            # Software version
            if 'Software image version' in line or 'image version' in line.lower():
                match = re.search(r':\s*(\S+)', line)
                if match:
                    info['version'] = match.group(1)
            
            # Uptime
            if 'Uptime' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    info['uptime'] = match.group(1).strip()
            
            # Hostname
            if 'hostname' in line.lower():
                match = re.search(r':\s*(\S+)', line)
                if match:
                    info['hostname'] = match.group(1)
        
        return info
    
    # Configuration Management
    
    async def set_interface_status(self, interface: str, enabled: bool) -> bool:
        """Enable or disable an interface"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            
            if enabled:
                await self.execute_command("no shutdown")
            else:
                await self.execute_command("shutdown")
            
            await self.execute_command("end")
            return True
        except Exception as e:
            logger.error(f"Error setting interface status: {str(e)}")
            return False
    
    async def save_config(self) -> bool:
        """Save running configuration"""
        try:
            output = await self.execute_command("write memory")
            return 'ok' in output.lower() or 'building configuration' in output.lower()
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
            return False
    
    # Additional required methods from BaseSwitchAdapter
    
    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        try:
            output = await self.execute_command("show version")
            return self._parse_version(output)
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            return {}
    
    async def get_vlan_info(self, vlan_id: int) -> Dict[str, Any]:
        """Get information about specific VLAN"""
        try:
            output = await self.execute_command(f"show vlan id {vlan_id}")
            vlans = self._parse_vlans(output)
            return vlans[0] if vlans else {}
        except Exception as e:
            logger.error(f"Error getting VLAN info: {str(e)}")
            return {}
    
    async def create_vlan(self, vlan_id: int, name: str) -> bool:
        """Create a new VLAN"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"vlan {vlan_id}")
            await self.execute_command(f"name {name}")
            await self.execute_command("end")
            return True
        except Exception as e:
            logger.error(f"Error creating VLAN: {str(e)}")
            return False
    
    async def delete_vlan(self, vlan_id: int) -> bool:
        """Delete a VLAN"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"no vlan {vlan_id}")
            await self.execute_command("end")
            return True
        except Exception as e:
            logger.error(f"Error deleting VLAN: {str(e)}")
            return False
    
    async def set_interface_vlan(self, interface: str, vlan_id: int) -> bool:
        """Set interface access VLAN"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            await self.execute_command("switchport mode access")
            await self.execute_command(f"switchport access vlan {vlan_id}")
            await self.execute_command("end")
            return True
        except Exception as e:
            logger.error(f"Error setting interface VLAN: {str(e)}")
            return False
    
    async def set_trunk_allowed_vlans(self, interface: str, vlans: List[int]) -> bool:
        """Set allowed VLANs on trunk interface"""
        try:
            vlan_list = ','.join(map(str, vlans))
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            await self.execute_command("switchport mode trunk")
            await self.execute_command(f"switchport trunk allowed vlan {vlan_list}")
            await self.execute_command("end")
            return True
        except Exception as e:
            logger.error(f"Error setting trunk VLANs: {str(e)}")
            return False
    
    async def set_interface_description(self, interface: str, description: str) -> bool:
        """Set interface description"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            await self.execute_command(f"description {description}")
            await self.execute_command("end")
            return True
        except Exception as e:
            logger.error(f"Error setting interface description: {str(e)}")
            return False
    
    async def get_mac_table(self) -> List[Dict[str, Any]]:
        """Get MAC address table"""
        try:
            output = await self.execute_command("show mac address-table")
            return self._parse_mac_table(output)
        except Exception as e:
            logger.error(f"Error getting MAC table: {str(e)}")
            return []
    
    def _parse_mac_table(self, output: str) -> List[Dict[str, Any]]:
        """Parse MAC address table"""
        entries = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or '----' in line or line.startswith('Mac') or line.startswith('Vlan'):
                continue
            
            parts = line.split()
            if len(parts) >= 4:
                entries.append({
                    'vlan': parts[0],
                    'mac_address': parts[1],
                    'type': parts[2],
                    'interface': parts[3] if len(parts) > 3 else ''
                })
        
        return entries
    
    async def get_arp_table(self) -> List[Dict[str, Any]]:
        """Get ARP table"""
        try:
            output = await self.execute_command("show arp")
            return self._parse_arp_table(output)
        except Exception as e:
            logger.error(f"Error getting ARP table: {str(e)}")
            return []
    
    def _parse_arp_table(self, output: str) -> List[Dict[str, Any]]:
        """Parse ARP table"""
        entries = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or '----' in line or line.startswith('Address') or line.startswith('Internet'):
                continue
            
            parts = line.split()
            if len(parts) >= 4:
                entries.append({
                    'ip_address': parts[0],
                    'age': parts[1],
                    'mac_address': parts[2],
                    'interface': parts[3] if len(parts) > 3 else ''
                })
        
        return entries
    
    async def get_interface_statistics(self, interface: str) -> Dict[str, Any]:
        """Get interface statistics"""
        try:
            output = await self.execute_command(f"show interfaces {interface}")
            return self._parse_interface_statistics(output)
        except Exception as e:
            logger.error(f"Error getting interface statistics: {str(e)}")
            return {}
    
    def _parse_interface_statistics(self, output: str) -> Dict[str, Any]:
        """Parse interface statistics"""
        stats = {}
        lines = output.split('\n')
        
        for line in lines:
            if 'packets input' in line.lower():
                match = re.search(r'(\d+) packets input', line)
                if match:
                    stats['input_packets'] = int(match.group(1))
            
            if 'packets output' in line.lower():
                match = re.search(r'(\d+) packets output', line)
                if match:
                    stats['output_packets'] = int(match.group(1))
            
            if 'input errors' in line.lower():
                match = re.search(r'(\d+) input errors', line)
                if match:
                    stats['input_errors'] = int(match.group(1))
            
            if 'output errors' in line.lower():
                match = re.search(r'(\d+) output errors', line)
                if match:
                    stats['output_errors'] = int(match.group(1))
        
        return stats
    
    async def get_port_statistics_summary(self) -> Dict[str, Any]:
        """Get summary of port statistics"""
        interfaces = await self.get_interfaces()
        return {
            'total_ports': len(interfaces),
            'ports_up': len([i for i in interfaces if i['status'] == 'up']),
            'ports_down': len([i for i in interfaces if i['status'] == 'down'])
        }
    
    async def get_running_config(self) -> str:
        """Get running configuration"""
        try:
            return await self.execute_command("show running-config")
        except Exception as e:
            logger.error(f"Error getting running config: {str(e)}")
            return ""
    
    async def get_startup_config(self) -> str:
        """Get startup configuration"""
        try:
            return await self.execute_command("show startup-config")
        except Exception as e:
            logger.error(f"Error getting startup config: {str(e)}")
            return ""
    
    async def get_switch_capabilities(self) -> Dict[str, Any]:
        """Get switch capabilities - alias for discover_capabilities"""
        return await self.discover_capabilities()
