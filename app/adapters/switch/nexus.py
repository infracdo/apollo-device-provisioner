"""
Cisco Nexus Switch Adapter

Implementation for Cisco Nexus switches with NX-OS.
Supports NX-OS command syntax (similar to IOS but with some differences).
"""
import re
from typing import Dict, List, Any, Optional
from app.adapters.switch.base_switch import BaseSwitchAdapter
from app.connectors.telnet_connector import TelnetConnector
from app.connectors.ssh_connector import SSHConnector
from app.models import Device
from app.utils.logging import logger


class NexusSwitch(BaseSwitchAdapter):
    """Cisco Nexus switch adapter implementation"""
    
    def __init__(self, device: Device):
        """Initialize Nexus switch adapter"""
        super().__init__(device)
        self.connector = None
        
    async def connect(self) -> bool:
        """Establish connection to Nexus switch"""
        try:
            device_config = {
                'host': self.device.host,
                'port': self.device.port,
                'username': self.device.username,
                'password': self.device.password,
                'timeout': 30
            }
            
            if self.device.protocol == 'telnet':
                self.connector = TelnetConnector(**device_config)
            elif self.device.protocol == 'ssh':
                self.connector = SSHConnector(**device_config)
            else:
                logger.error(f"Unsupported protocol: {self.device.protocol}")
                return False
            
            connected = await self.connector.connect()
            
            if connected:
                # Enter privileged mode
                await self._enter_enable_mode()
                # Disable terminal paging
                await self.execute_command("terminal length 0")
                logger.info(f"Connected to Nexus switch {self.device.host}")
            
            return connected
            
        except Exception as e:
            logger.error(f"Error connecting to Nexus switch: {str(e)}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Nexus switch"""
        if self.connector:
            return await self.connector.disconnect()
        return True
    
    async def execute_command(self, command: str) -> str:
        """Execute command on Nexus switch"""
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
                await self.connector.writer.write(enable_password + '\n')
                await self.connector.writer.drain()
        except Exception as e:
            logger.warning(f"Could not enter enable mode: {str(e)}")
    
    # Interface Management
    
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """Get list of all interfaces
        
        Command: show interface status
        """
        try:
            output = await self.execute_command("show interface status")
            return self._parse_interface_status(output)
        except Exception as e:
            logger.error(f"Error getting interfaces: {str(e)}")
            return []
    
    def _parse_interface_status(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show interface status' output for Nexus"""
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers, separators, and empty lines
            if not line or '----' in line or 'Port' in line or 'Interface' in line:
                continue
            
            # Skip prompts
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Skip command echo
            if 'show interface' in line.lower():
                continue
            
            # Parse interface line (Nexus format)
            # Format: Eth1/1    --             connected    1    full    1000  --
            parts = line.split()
            if len(parts) >= 3:
                interface_name = parts[0]
                
                # Skip if not a physical interface
                if not any(x in interface_name.lower() for x in ['eth', 'ethernet', 'gi', 'te', 'fa']):
                    continue
                
                # Extract fields
                description = parts[1] if parts[1] != '--' else ''
                status = 'up' if 'connected' in line.lower() or 'up' in line.lower() else 'down'
                
                # Find VLAN
                vlan = '1'
                for i, part in enumerate(parts):
                    if part.isdigit() and 1 <= int(part) <= 4094:
                        vlan = part
                        break
                
                # Find duplex
                duplex = 'auto'
                if 'full' in line.lower():
                    duplex = 'full'
                elif 'half' in line.lower():
                    duplex = 'half'
                
                # Find speed
                speed = 'auto'
                for part in parts:
                    if part.isdigit() and int(part) in [10, 100, 1000, 10000, 40000, 100000]:
                        speed = part
                        break
                
                interfaces.append({
                    'name': interface_name,
                    'description': description,
                    'status': status,
                    'speed': speed,
                    'duplex': duplex,
                    'vlan': vlan
                })
        
        return interfaces
    
    async def get_interface_status(self, interface: str) -> Dict[str, Any]:
        """Get detailed status of specific interface"""
        try:
            output = await self.execute_command(f"show interface {interface}")
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
            
            elif 'Hardware' in line:
                match = re.search(r'Hardware:\s*(.+?)(?:,|$)', line)
                if match:
                    info['hardware'] = match.group(1).strip()
            
            elif 'Description:' in line:
                match = re.search(r'Description:\s*(.+)', line)
                if match:
                    info['description'] = match.group(1).strip()
            
            elif 'MTU' in line:
                match = re.search(r'MTU (\d+)', line)
                if match:
                    info['mtu'] = int(match.group(1))
            
            elif 'BW' in line or 'Bandwidth' in line:
                match = re.search(r'(?:BW|Bandwidth)\s+(\d+)', line, re.IGNORECASE)
                if match:
                    info['bandwidth'] = match.group(1)
            
            elif 'duplex' in line.lower():
                if 'full' in line.lower():
                    info['duplex'] = 'full'
                elif 'half' in line.lower():
                    info['duplex'] = 'half'
                else:
                    info['duplex'] = 'auto'
        
        return info
    
    async def get_interface_statistics(self, interface: str) -> Dict[str, Any]:
        """Get traffic statistics for interface"""
        try:
            output = await self.execute_command(f"show interface {interface}")
            return self._parse_interface_statistics(output)
        except Exception as e:
            logger.error(f"Error getting interface statistics: {str(e)}")
            return {}
    
    def _parse_interface_statistics(self, output: str) -> Dict[str, Any]:
        """Parse interface statistics from output"""
        stats = {}
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            
            # Input packets/bytes
            if 'input' in line.lower():
                # Input packets
                match = re.search(r'(\d+)\s+(?:input\s+)?packets', line)
                if match:
                    stats['input_packets'] = int(match.group(1))
                
                # Input bytes
                match = re.search(r'(\d+)\s+bytes', line)
                if match and 'input_bytes' not in stats:
                    stats['input_bytes'] = int(match.group(1))
            
            # Output packets/bytes
            if 'output' in line.lower():
                # Output packets
                match = re.search(r'(\d+)\s+(?:output\s+)?packets', line)
                if match:
                    stats['output_packets'] = int(match.group(1))
                
                # Output bytes
                match = re.search(r'(\d+)\s+bytes', line)
                if match and 'output_bytes' not in stats:
                    stats['output_bytes'] = int(match.group(1))
            
            # RX/TX counters (alternative format)
            if 'RX' in line:
                match = re.search(r'(\d+)\s+unicast packets', line)
                if match and 'input_packets' not in stats:
                    stats['input_packets'] = int(match.group(1))
            
            if 'TX' in line:
                match = re.search(r'(\d+)\s+unicast packets', line)
                if match and 'output_packets' not in stats:
                    stats['output_packets'] = int(match.group(1))
            
            # Errors
            if 'input error' in line.lower():
                match = re.search(r'(\d+)\s+input\s+error', line)
                if match:
                    stats['input_errors'] = int(match.group(1))
            
            if 'output error' in line.lower():
                match = re.search(r'(\d+)\s+output\s+error', line)
                if match:
                    stats['output_errors'] = int(match.group(1))
        
        return stats
    
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
            
            logger.info(f"Set interface {interface} to {'enabled' if enabled else 'disabled'}")
            return True
        except Exception as e:
            logger.error(f"Error setting interface status: {str(e)}")
            return False
    
    async def set_interface_description(self, interface: str, description: str) -> bool:
        """Set interface description"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            await self.execute_command(f"description {description}")
            await self.execute_command("end")
            
            logger.info(f"Set description for interface {interface}")
            return True
        except Exception as e:
            logger.error(f"Error setting interface description: {str(e)}")
            return False
    
    # VLAN Management
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get list of configured VLANs
        
        Command: show vlan
        """
        try:
            output = await self.execute_command("show vlan")
            return self._parse_vlans(output)
        except Exception as e:
            logger.error(f"Error getting VLANs: {str(e)}")
            return []
    
    def _parse_vlans(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show vlan' output for Nexus"""
        vlans = []
        lines = output.split('\n')
        
        in_vlan_section = False
        for line in lines:
            line = line.strip()
            
            # Detect VLAN section header
            if 'VLAN' in line and ('Name' in line or 'Status' in line):
                in_vlan_section = True
                continue
            
            # Skip separators and empty lines
            if not line or '----' in line:
                continue
            
            # Skip prompts
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Skip command echo
            if 'show vlan' in line.lower():
                continue
            
            if in_vlan_section:
                # Parse VLAN line
                # Format: 1    default                          active
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    vlan_id = int(parts[0])
                    
                    # Skip reserved VLANs if needed
                    if vlan_id > 4094:
                        continue
                    
                    vlan_entry = {
                        'vlan_id': vlan_id,
                        'name': parts[1] if len(parts) > 1 else f'VLAN{vlan_id}',
                        'status': parts[2] if len(parts) > 2 else 'active'
                    }
                    
                    # Ports may be on same line or next lines
                    if len(parts) > 3:
                        vlan_entry['ports'] = ' '.join(parts[3:])
                    else:
                        vlan_entry['ports'] = ''
                    
                    vlans.append(vlan_entry)
        
        return vlans
    
    async def get_vlan_info(self, vlan_id: int) -> Dict[str, Any]:
        """Get detailed information about specific VLAN"""
        try:
            output = await self.execute_command(f"show vlan id {vlan_id}")
            vlans = self._parse_vlans(output)
            
            for vlan in vlans:
                if vlan['vlan_id'] == vlan_id:
                    return vlan
            
            return {}
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
            
            logger.info(f"Created VLAN {vlan_id} with name {name}")
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
            
            logger.info(f"Deleted VLAN {vlan_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting VLAN: {str(e)}")
            return False
    
    async def set_interface_vlan(self, interface: str, vlan_id: int, mode: str = "access") -> bool:
        """Assign interface to VLAN"""
        try:
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            
            if mode == "access":
                await self.execute_command("switchport mode access")
                await self.execute_command(f"switchport access vlan {vlan_id}")
            elif mode == "trunk":
                await self.execute_command("switchport mode trunk")
            
            await self.execute_command("end")
            
            logger.info(f"Set interface {interface} to VLAN {vlan_id} in {mode} mode")
            return True
        except Exception as e:
            logger.error(f"Error setting interface VLAN: {str(e)}")
            return False
    
    async def set_trunk_allowed_vlans(self, interface: str, vlans: List[int]) -> bool:
        """Set allowed VLANs on trunk port"""
        try:
            vlan_list = ','.join(str(v) for v in vlans)
            
            await self.execute_command("configure terminal")
            await self.execute_command(f"interface {interface}")
            await self.execute_command("switchport mode trunk")
            await self.execute_command(f"switchport trunk allowed vlan {vlan_list}")
            await self.execute_command("end")
            
            logger.info(f"Set allowed VLANs on trunk {interface}: {vlan_list}")
            return True
        except Exception as e:
            logger.error(f"Error setting trunk allowed VLANs: {str(e)}")
            return False
    
    # MAC Address Table
    
    async def get_mac_table(self, vlan: Optional[int] = None, interface: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get MAC address table
        
        Command: show mac address-table
        """
        try:
            if vlan:
                command = f"show mac address-table vlan {vlan}"
            elif interface:
                command = f"show mac address-table interface {interface}"
            else:
                command = "show mac address-table"
            
            output = await self.execute_command(command)
            return self._parse_mac_table(output)
        except Exception as e:
            logger.error(f"Error getting MAC table: {str(e)}")
            return []
    
    def _parse_mac_table(self, output: str) -> List[Dict[str, Any]]:
        """Parse MAC address table output for Nexus"""
        mac_entries = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers and separators
            if not line or '----' in line or 'VLAN' in line or 'Mac Address' in line or 'Legend' in line:
                continue
            
            # Skip prompts and command echo
            if line.endswith('#') or line.endswith('>') or 'show mac' in line.lower():
                continue
            
            # Parse MAC entry (Nexus format)
            # Format: *    1    0011.2233.4455    dynamic   0    F    F    Eth1/1
            parts = line.split()
            
            # Look for VLAN and MAC address pattern
            vlan_id = None
            mac_addr = None
            entry_type = 'dynamic'
            interface = ''
            
            for i, part in enumerate(parts):
                # VLAN ID
                if part.isdigit() and 1 <= int(part) <= 4094 and vlan_id is None:
                    vlan_id = int(part)
                
                # MAC address (format: xxxx.xxxx.xxxx)
                elif re.match(r'^[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}$', part.lower()):
                    mac_addr = part
                
                # Type
                elif part.lower() in ['dynamic', 'static']:
                    entry_type = part.lower()
                
                # Interface (usually last or contains Eth/port)
                elif any(x in part for x in ['Eth', 'eth', 'Po', 'po', 'Vlan', 'vlan']):
                    interface = part
            
            if vlan_id and mac_addr:
                mac_entries.append({
                    'vlan': vlan_id,
                    'mac_address': mac_addr,
                    'type': entry_type,
                    'interface': interface
                })
        
        return mac_entries
    
    async def get_arp_table(self) -> List[Dict[str, Any]]:
        """Get ARP table
        
        Command: show ip arp
        """
        try:
            output = await self.execute_command("show ip arp")
            return self._parse_arp_table(output)
        except Exception as e:
            logger.error(f"Error getting ARP table: {str(e)}")
            return []
    
    def _parse_arp_table(self, output: str) -> List[Dict[str, Any]]:
        """Parse ARP table output for Nexus"""
        arp_entries = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers and separators
            if not line or '----' in line or 'Address' in line or 'Total' in line:
                continue
            
            # Skip prompts and command echo
            if line.endswith('#') or line.endswith('>') or 'show ip arp' in line.lower():
                continue
            
            # Parse ARP entry (Nexus format)
            # Format: 192.168.1.1    00:23:45  0011.2233.4455  Vlan1
            parts = line.split()
            
            if len(parts) >= 3:
                ip_addr = None
                mac_addr = None
                interface = ''
                age = '-'
                
                for part in parts:
                    # IP address
                    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', part):
                        ip_addr = part
                    
                    # MAC address
                    elif re.match(r'^[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}$', part.lower()):
                        mac_addr = part
                    
                    # Age (time format like 00:23:45)
                    elif re.match(r'^\d{2}:\d{2}:\d{2}$', part):
                        age = part
                    
                    # Interface
                    elif any(x in part for x in ['Vlan', 'vlan', 'Eth', 'eth', 'Po', 'po']):
                        interface = part
                
                if ip_addr and mac_addr:
                    arp_entries.append({
                        'ip_address': ip_addr,
                        'mac_address': mac_addr,
                        'interface': interface,
                        'age': age
                    })
        
        return arp_entries
    
    # Configuration
    
    async def get_running_config(self) -> str:
        """Get running configuration"""
        try:
            output = await self.execute_command("show running-config")
            return output
        except Exception as e:
            logger.error(f"Error getting running config: {str(e)}")
            return f"Error: {str(e)}"
    
    async def get_startup_config(self) -> str:
        """Get startup configuration"""
        try:
            output = await self.execute_command("show startup-config")
            return output
        except Exception as e:
            logger.error(f"Error getting startup config: {str(e)}")
            return f"Error: {str(e)}"
    
    async def save_config(self) -> bool:
        """Save running configuration to startup"""
        try:
            output = await self.execute_command("copy running-config startup-config")
            return True  # Nexus auto-confirms in most cases
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
            return False
    
    # System Information
    
    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information
        
        Command: show version
        """
        try:
            output = await self.execute_command("show version")
            return self._parse_system_info(output)
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            return {}
    
    def _parse_system_info(self, output: str) -> Dict[str, Any]:
        """Parse system information from show version"""
        info = {}
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            
            # Software version
            if 'NXOS' in line or 'system:' in line.lower():
                match = re.search(r'version\s+(\S+)', line, re.IGNORECASE)
                if match:
                    info['version'] = match.group(1)
            
            # Hostname
            if 'Device name:' in line:
                match = re.search(r'Device name:\s+(\S+)', line)
                if match:
                    info['hostname'] = match.group(1)
            
            # Model
            if 'cisco' in line.lower() and 'chassis' in line.lower():
                match = re.search(r'cisco\s+(\S+)', line, re.IGNORECASE)
                if match:
                    info['model'] = match.group(1)
            
            # Hardware
            if 'Hardware' in line:
                match = re.search(r'Hardware\s*:\s*(.+?)(?:,|$)', line)
                if match:
                    info['hardware'] = match.group(1).strip()
            
            # Uptime
            if 'uptime' in line.lower():
                match = re.search(r'uptime\s+is\s+(.+?)(?:\n|$)', line, re.IGNORECASE)
                if match:
                    info['uptime'] = match.group(1).strip()
            
            # Serial number
            if 'Processor Board ID' in line:
                match = re.search(r'Processor Board ID\s+(\S+)', line)
                if match:
                    info['serial'] = match.group(1)
        
        return info
    
    async def get_port_statistics_summary(self) -> Dict[str, Any]:
        """Get summary of port statistics"""
        try:
            interfaces = await self.get_interfaces()
            
            total = len(interfaces)
            up = sum(1 for iface in interfaces if iface.get('status') == 'up')
            down = total - up
            
            return {
                'total_ports': total,
                'up_ports': up,
                'down_ports': down
            }
        except Exception as e:
            logger.error(f"Error getting port statistics summary: {str(e)}")
            return {}
    
    async def discover_commands(self) -> Dict[str, Any]:
        """Discover supported commands on Nexus switch"""
        try:
            # Commands to test (NX-OS specific)
            test_commands = [
                ('show version', 'System version and hardware info'),
                ('show inventory', 'Hardware inventory'),
                ('show interface', 'All interfaces detailed'),
                ('show interface status', 'Interface status summary'),
                ('show interface description', 'Interface descriptions'),
                ('show interface switchport', 'Switchport configuration'),
                ('show ip interface brief', 'IP interface brief'),
                ('show vlan', 'VLAN database'),
                ('show vlan brief', 'VLAN brief'),
                ('show vlan summary', 'VLAN summary'),
                ('show mac address-table', 'MAC address table'),
                ('show mac address-table dynamic', 'Dynamic MAC addresses'),
                ('show ip arp', 'ARP table'),
                ('show spanning-tree', 'Spanning tree status'),
                ('show spanning-tree summary', 'Spanning tree summary'),
                ('show running-config', 'Running configuration'),
                ('show startup-config', 'Startup configuration'),
                ('show interface trunk', 'Trunk interfaces'),
                ('show port-channel summary', 'Port-channel summary'),
                ('show clock', 'System clock'),
                ('show users', 'Logged in users'),
            ]
            
            successful = []
            failed = []
            
            for command, description in test_commands:
                try:
                    output = await self.execute_command(command)
                    
                    # Check for error indicators
                    error_indicators = [
                        'invalid input',
                        'incomplete command',
                        'unknown command',
                        'invalid command',
                        '% error',
                        'syntax error',
                    ]
                    
                    is_error = any(err in output.lower() for err in error_indicators)
                    
                    if is_error or not output or len(output.strip()) < 10:
                        failed.append({
                            'command': command,
                            'description': description,
                            'error': output[:200] if output else 'No output'
                        })
                    else:
                        successful.append({
                            'command': command,
                            'description': description,
                            'output_size': len(output)
                        })
                except Exception as e:
                    failed.append({
                        'command': command,
                        'description': description,
                        'error': str(e)
                    })
            
            # Detect capabilities based on successful commands
            capabilities = {
                'has_vlans': any('vlan' in cmd['command'] for cmd in successful),
                'has_mac_table': any('mac' in cmd['command'] for cmd in successful),
                'has_arp_table': any('arp' in cmd['command'] for cmd in successful),
                'has_spanning_tree': any('spanning-tree' in cmd['command'] for cmd in successful),
                'has_trunk': any('trunk' in cmd['command'] for cmd in successful),
                'has_port_channel': any('port-channel' in cmd['command'] for cmd in successful),
                'can_save_config': any('running-config' in cmd['command'] for cmd in successful),
            }
            
            return {
                'successful': successful,
                'failed': failed,
                'capabilities': capabilities,
                'total_tested': len(test_commands),
                'success_rate': f"{len(successful)}/{len(test_commands)}"
            }
            
        except Exception as e:
            logger.error(f"Error discovering commands: {str(e)}")
            return {
                'successful': [],
                'failed': [],
                'capabilities': {},
                'error': str(e)
            }
    
    async def discover_vlan_port_mapping(self) -> Dict[str, Any]:
        """Discover VLAN to port mappings on Nexus switch"""
        try:
            raw_outputs = {}
            
            # Get VLAN information
            vlan_output = await self.execute_command('show vlan')
            raw_outputs['show_vlan'] = vlan_output
            
            # Get switchport information
            switchport_output = await self.execute_command('show interface switchport')
            raw_outputs['show_interface_switchport'] = switchport_output
            
            # Get interface status
            status_output = await self.execute_command('show interface status')
            raw_outputs['show_interface_status'] = status_output
            
            # Parse VLANs
            vlans = []
            vlan_dict = {}
            
            for line in vlan_output.split('\n'):
                line = line.strip()
                # NX-OS format: "1    default                          active"
                match = re.match(r'(\d+)\s+(\S+)\s+(active|suspended|act/lshut)', line)
                if match:
                    vlan_id = match.group(1)
                    vlan_name = match.group(2)
                    vlan_status = match.group(3)
                    
                    vlan_info = {
                        'vlan_id': int(vlan_id),
                        'name': vlan_name,
                        'status': vlan_status.lower(),
                        'ports': []
                    }
                    vlans.append(vlan_info)
                    vlan_dict[int(vlan_id)] = vlan_info
            
            # Parse port configurations
            ports = {}
            current_interface = None
            current_mode = None
            current_access_vlan = None
            current_native_vlan = None
            current_allowed_vlans = None
            
            for line in switchport_output.split('\n'):
                line = line.strip()
                
                # Match interface name
                if line.startswith('Name:'):
                    match = re.search(r'Name:\s+(\S+)', line)
                    if match:
                        current_interface = match.group(1)
                        current_mode = None
                        current_access_vlan = None
                        current_native_vlan = None
                        current_allowed_vlans = None
                
                # Match operational mode
                elif 'Operational Mode:' in line or 'Switchport:' in line:
                    if 'trunk' in line.lower():
                        current_mode = 'trunk'
                    elif 'access' in line.lower():
                        current_mode = 'access'
                
                # Match access VLAN
                elif 'Access Mode VLAN:' in line:
                    match = re.search(r'VLAN:\s+(\d+)', line)
                    if match:
                        current_access_vlan = int(match.group(1))
                
                # Match native VLAN
                elif 'Trunking Native Mode VLAN:' in line:
                    match = re.search(r'VLAN:\s+(\d+)', line)
                    if match:
                        current_native_vlan = int(match.group(1))
                
                # Match allowed VLANs
                elif 'Trunking VLANs Allowed:' in line:
                    match = re.search(r'Allowed:\s+(.+)', line)
                    if match:
                        current_allowed_vlans = match.group(1).strip()
                
                # Save port info when we have complete data
                if current_interface and current_mode:
                    if current_interface not in ports:
                        port_info = {
                            'interface': current_interface,
                            'mode': current_mode,
                            'access_vlan': current_access_vlan if current_mode == 'access' else None,
                            'native_vlan': current_native_vlan if current_mode == 'trunk' else None,
                            'allowed_vlans': current_allowed_vlans if current_mode == 'trunk' else None,
                            'status': 'unknown'
                        }
                        ports[current_interface] = port_info
            
            # Add status information from interface status
            for line in status_output.split('\n'):
                line = line.strip()
                parts = line.split()
                
                if len(parts) >= 3 and parts[0] in ports:
                    ports[parts[0]]['status'] = parts[2]
                    if len(parts) > 3:
                        ports[parts[0]]['vlan'] = parts[3]
            
            # Update VLAN port lists
            for interface, info in ports.items():
                if info['mode'] == 'access' and info.get('access_vlan'):
                    vlan_id = info['access_vlan']
                    if vlan_id in vlan_dict:
                        vlan_dict[vlan_id]['ports'].append(interface)
            
            # Create port-to-VLAN summary
            summary = []
            for interface, info in sorted(ports.items()):
                if info['mode'] == 'access':
                    vlan_str = str(info.get('access_vlan', 'N/A'))
                elif info['mode'] == 'trunk':
                    vlan_str = info.get('allowed_vlans', 'ALL')
                else:
                    vlan_str = 'N/A'
                
                summary.append({
                    'port': interface,
                    'mode': info['mode'],
                    'vlans': vlan_str,
                    'status': info.get('status', 'unknown')
                })
            
            return {
                'vlans': vlans,
                'ports': ports,
                'summary': summary,
                'raw_outputs': raw_outputs
            }
            
        except Exception as e:
            logger.error(f"Error discovering VLAN port mapping: {str(e)}")
            return {
                'vlans': [],
                'ports': {},
                'summary': [],
                'error': str(e)
            }
    
    async def get_switch_capabilities(self) -> Dict[str, Any]:
        """Get Nexus switch capabilities and features"""
        try:
            # Get system info
            system_info = await self.get_system_info()
            
            # Get interfaces to count ports
            interfaces = await self.get_interfaces()
            
            # Get VLANs to determine VLAN range
            vlans = await self.get_vlans()
            vlan_ids = [v.get('vlan_id') for v in vlans if v.get('vlan_id')]
            
            capabilities = {
                'manufacturer': 'Cisco',
                'product_line': 'Nexus',
                'os': 'NX-OS',
                'model': system_info.get('model', 'Unknown'),
                'os_version': system_info.get('version', 'Unknown'),
                'serial': system_info.get('serial', 'Unknown'),
                'hostname': system_info.get('hostname', 'Unknown'),
                'uptime': system_info.get('uptime', 'Unknown'),
                'supported_features': [
                    'vlan_management',
                    'interface_configuration',
                    'mac_address_table',
                    'arp_table',
                    'spanning_tree',
                    'trunk_ports',
                    'access_ports',
                    'port_channel',
                    'port_statistics',
                    'configuration_save',
                    'vpc',  # Virtual Port Channel (Nexus feature)
                ],
                'port_count': len(interfaces),
                'vlan_range': {
                    'min': 1,
                    'max': 4094,
                    'configured_vlans': len(vlans),
                    'min_configured': min(vlan_ids) if vlan_ids else None,
                    'max_configured': max(vlan_ids) if vlan_ids else None,
                },
                'interface_types': list(set(
                    iface.get('interface', '').split('/')[0] if '/' in iface.get('interface', '') else 'Unknown'
                    for iface in interfaces
                )),
                'protocol': self.device.protocol,
                'management_ip': self.device.host,
            }
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Error getting switch capabilities: {str(e)}")
            return {
                'manufacturer': 'Cisco',
                'product_line': 'Nexus',
                'os': 'NX-OS',
                'error': str(e)
            }

