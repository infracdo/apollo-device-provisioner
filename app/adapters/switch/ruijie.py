"""
Ruijie Switch Adapter

Implementation for Ruijie network switches.
Supports Ruijie OS command syntax.
"""
import re
from typing import Dict, List, Any, Optional
from app.adapters.switch.base_switch import BaseSwitchAdapter
from app.connectors.telnet_connector import TelnetConnector
from app.connectors.ssh_connector import SSHConnector
from app.models import Device
from app.utils.logging import logger


class RuijieSwitch(BaseSwitchAdapter):
    """Ruijie switch adapter implementation"""
    
    def __init__(self, device: Device):
        """Initialize Ruijie switch adapter"""
        super().__init__(device)
        self.connector = None
        
    async def connect(self) -> bool:
        """Establish connection to Ruijie switch"""
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
                # Disable pagination to get full command output
                try:
                    await self.execute_command("terminal length 0")
                except Exception as e:
                    logger.debug(f"Could not set terminal length: {str(e)}")
                
                # Enter privileged mode
                await self._enter_enable_mode()
                logger.info(f"Connected to Ruijie switch {self.device.host}")
            
            return connected
            
        except Exception as e:
            logger.error(f"Error connecting to Ruijie switch: {str(e)}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Ruijie switch"""
        if self.connector:
            return await self.connector.disconnect()
        return True
    
    async def execute_command(self, command: str) -> str:
        """Execute command on Ruijie switch"""
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
        
        Try multiple commands to get interface list:
        1. show interface status (preferred but not all models support it)
        2. show interfaces description (widely supported, shows all physical interfaces)
        3. show interface (fallback, parse summary lines)
        """
        try:
            # Try show interface status first
            output = await self.execute_command("show interface status")
            if "unknown command" not in output.lower() and "invalid" not in output.lower():
                interfaces = self._parse_interface_status(output)
                if interfaces:  # Only return if we got valid results
                    return interfaces
        except Exception as e:
            logger.debug(f"show interface status not available: {str(e)}")
        
        try:
            # Fallback to show interfaces description (better for Ruijie)
            output = await self.execute_command("show interfaces description")
            interfaces = self._parse_interfaces_description(output)
            if interfaces:  # Only return if we got valid results
                return interfaces
        except Exception as e:
            logger.debug(f"show interfaces description failed: {str(e)}")
        
        try:
            # Last resort: parse show interface output
            output = await self.execute_command("show interface")
            return self._parse_show_interface(output)
        except Exception as e:
            logger.error(f"Error getting interfaces: {str(e)}")
            return []
    
    def _parse_interface_status(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show interface status' output
        
        Can handle multiple formats:
        - Compact: Gi0/1    up    1000  full  1
        - Ruijie: GigabitEthernet 0/1    down    up
        """
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers, separators, and empty lines
            if not line or '----' in line or 'Port' in line or 'Interface' in line:
                continue
            
            # Skip prompts and pagination
            if line.endswith('#') or line.endswith('>'):
                continue
            if '--More--' in line:
                continue
            
            # Parse interface line
            parts = line.split()
            if len(parts) >= 3:
                # Skip command echoes
                if parts[0].lower() in ['show', 'interface', 'interfaces']:
                    continue
                
                # Check if interface name is split (Ruijie format)
                # e.g., "GigabitEthernet 0/1" -> parts[0]="GigabitEthernet", parts[1]="0/1"
                if len(parts) >= 4 and ('/' in parts[1] or parts[1].isdigit()):
                    # Interface name is split into two parts
                    interface_name = f"{parts[0]}{parts[1]}"
                    # Remaining parts shift by 1
                    status_parts = parts[2:]
                    description = ''
                else:
                    # Compact format: Gi0/1
                    interface_name = parts[0]
                    status_parts = parts[1:]
                    description = parts[1] if len(parts) > 1 and not parts[1].lower() in ['up', 'down', 'disabled'] else ''
                
                interfaces.append({
                    'name': interface_name,
                    'description': description,
                    'status': self._extract_status(status_parts),
                    'speed': self._extract_speed(status_parts),
                    'duplex': self._extract_duplex(status_parts),
                    'vlan': self._extract_vlan(status_parts)
                })
        
        return interfaces
    
    def _extract_status(self, parts: List[str]) -> str:
        """Extract status from interface line parts"""
        for part in parts:
            if part.lower() in ['up', 'down', 'disabled']:
                return part.lower()
        return 'unknown'
    
    def _extract_speed(self, parts: List[str]) -> str:
        """Extract speed from interface line parts"""
        for part in parts:
            if part.isdigit() and int(part) in [10, 100, 1000, 10000, 40000, 100000]:
                return part
        return 'auto'
    
    def _extract_duplex(self, parts: List[str]) -> str:
        """Extract duplex from interface line parts"""
        for part in parts:
            if part.lower() in ['full', 'half', 'auto']:
                return part.lower()
        return 'auto'
    
    def _extract_vlan(self, parts: List[str]) -> str:
        """Extract VLAN from interface line parts"""
        # Usually the last numeric value
        for part in reversed(parts):
            if part.isdigit() and 1 <= int(part) <= 4094:
                return part
        return '1'
    
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
            
            elif 'Hardware is' in line:
                match = re.search(r'Hardware is (.+?),', line)
                if match:
                    info['hardware'] = match.group(1)
            
            elif 'Description:' in line:
                match = re.search(r'Description:\s*(.+)', line)
                if match:
                    info['description'] = match.group(1).strip()
            
            elif 'MTU' in line:
                match = re.search(r'MTU (\d+)', line)
                if match:
                    info['mtu'] = int(match.group(1))
            
            elif 'BW' in line or 'bandwidth' in line.lower():
                match = re.search(r'BW\s+(\d+)', line) or re.search(r'bandwidth\s+(\d+)', line, re.IGNORECASE)
                if match:
                    info['bandwidth'] = match.group(1)
        
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
            
            # Input packets
            if 'input packets' in line.lower():
                match = re.search(r'(\d+)\s+packets', line)
                if match:
                    stats['input_packets'] = int(match.group(1))
            
            # Output packets
            if 'output packets' in line.lower():
                match = re.search(r'(\d+)\s+packets', line)
                if match:
                    stats['output_packets'] = int(match.group(1))
            
            # Input bytes
            if 'input' in line.lower() and 'bytes' in line.lower():
                match = re.search(r'(\d+)\s+bytes', line)
                if match:
                    stats['input_bytes'] = int(match.group(1))
            
            # Output bytes
            if 'output' in line.lower() and 'bytes' in line.lower():
                match = re.search(r'(\d+)\s+bytes', line)
                if match:
                    stats['output_bytes'] = int(match.group(1))
            
            # Errors
            if 'input errors' in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    stats['input_errors'] = int(match.group(1))
            
            if 'output errors' in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    stats['output_errors'] = int(match.group(1))
        
        return stats
    
    def _parse_interfaces_description(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show interfaces description' output
        
        Example format:
        Interface                                Status   Administrative Description
        ---------------------------------------- -------- -------------- -----------
        GigabitEthernet 0/1                      down     up             
        TenGigabitEthernet 0/25                  up       up             Port description
        """
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers, separators, empty lines, and prompts
            if not line or '----' in line or line.startswith('Interface'):
                continue
            if line.endswith('#') or line.endswith('>'):
                continue
            if '--More--' in line:
                continue
            
            # Parse interface line
            # Format: "GigabitEthernet 0/1      down     up"
            parts = line.split()
            if len(parts) >= 3:
                # Check if this looks like an interface line
                # Ruijie format: Interface name is split into two parts with a space
                # e.g., "GigabitEthernet 0/1" becomes parts[0]="GigabitEthernet", parts[1]="0/1"
                if len(parts) >= 4 and ('/' in parts[1] or parts[1].isdigit()):
                    # Interface name is two parts (Ruijie format)
                    interface_name = f"{parts[0]}{parts[1]}"  # Combine: GigabitEthernet0/1
                    # parts[2] = operational status, parts[3] = administrative status
                    status = parts[2]  # Use operational status
                    # Description starts at parts[4] if present
                    description = ' '.join(parts[4:]) if len(parts) > 4 else ''
                elif parts[0].lower().startswith(('gigabitethernet', 'tengigabitethernet', 'fastethernet', 'ethernet', 'vlan')):
                    # Single-part interface name (e.g., "Gi0/1" - some switches use abbreviations)
                    interface_name = parts[0]
                    status = parts[1] if len(parts) > 1 else 'unknown'
                    # Description starts at parts[3] if present
                    description = ' '.join(parts[3:]) if len(parts) > 3 else ''
                else:
                    continue
                
                interfaces.append({
                    'name': interface_name,
                    'status': status,
                    'description': description,
                    'speed': 'auto',
                    'duplex': 'auto',
                    'vlan': '1'
                })
        
        return interfaces
    
    def _parse_ip_interface_brief(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show ip interface brief' output
        
        Expected format:
        Interface              IP Address      Status                Protocol
        GigabitEthernet 0/1    unassigned      down                  down
        TenGigabitEthernet 0/25 unassigned     down                  down
        """
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers, separators, and empty lines
            if not line or '----' in line or line.startswith('Interface'):
                continue
            
            # Skip prompts
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Parse interface line
            parts = line.split()
            if len(parts) >= 4:  # Need at least: Interface, portnum, IP/status, Protocol/status
                # Ruijie format: "GigabitEthernet 0/1    unassigned      down      down"
                # Interface name is split into two parts with a space
                # Check if second part looks like a port number (contains / or is numeric)
                if len(parts) >= 4 and ('/' in parts[1] or parts[1].isdigit()):
                    # Interface name is two parts (e.g., "GigabitEthernet 0/1")
                    interface_name = f"{parts[0]}{parts[1]}"  # Combine without space
                    # Status is typically in parts[3] (protocol status)
                    status = parts[3] if len(parts) > 3 else 'unknown'
                else:
                    # Interface name is single part
                    interface_name = parts[0]
                    status = parts[2] if len(parts) > 2 else 'unknown'
                
                interfaces.append({
                    'name': interface_name,
                    'status': status,
                    'description': '',
                    'speed': 'auto',
                    'duplex': 'auto',
                    'vlan': '1'
                })
        
        return interfaces
    
    def _parse_show_interface(self, output: str) -> List[Dict[str, Any]]:
        """Parse 'show interface' output to extract interface names
        
        Each interface starts with a line like:
        GigabitEthernet 0/1 is down, line protocol is down
        """
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Look for interface header lines
            # Format: "InterfaceName is status, line protocol is status"
            if ' is ' in line and ('line protocol' in line or 'administratively' in line):
                # Extract interface name (everything before " is ")
                interface_name = line.split(' is ')[0].strip()
                
                # Remove spaces from interface name (GigabitEthernet 0/1 -> GigabitEthernet0/1)
                interface_name = interface_name.replace(' ', '')
                
                # Extract status
                status = 'down'
                if ' is up' in line:
                    status = 'up'
                elif 'administratively down' in line:
                    status = 'disabled'
                
                interfaces.append({
                    'name': interface_name,
                    'status': status,
                    'description': '',
                    'speed': 'auto',
                    'duplex': 'auto',
                    'vlan': '1'
                })
        
        return interfaces
    
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
        """Parse 'show vlan' output"""
        vlans = []
        lines = output.split('\n')
        
        in_vlan_section = False
        for line in lines:
            line = line.strip()
            
            # Detect VLAN section header
            if 'VLAN' in line and 'Name' in line:
                in_vlan_section = True
                continue
            
            # Skip separators and empty lines
            if not line or '----' in line:
                continue
            
            # Skip prompts
            if line.endswith('#') or line.endswith('>'):
                continue
            
            if in_vlan_section:
                # Parse VLAN line
                # Format: 1    default                          active
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    vlan_entry = {
                        'vlan_id': int(parts[0]),
                        'name': parts[1] if len(parts) > 1 else '',
                        'status': parts[2] if len(parts) > 2 else 'active'
                    }
                    
                    # Get ports for this VLAN if available
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
        """Parse MAC address table output"""
        mac_entries = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers and separators
            if not line or '----' in line or 'Vlan' in line or 'Mac Address' in line:
                continue
            
            # Skip prompts
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Parse MAC entry
            # Format: 1    0011.2233.4455    dynamic    Gi0/1
            parts = line.split()
            if len(parts) >= 4:
                mac_entries.append({
                    'vlan': int(parts[0]) if parts[0].isdigit() else 0,
                    'mac_address': parts[1],
                    'type': parts[2].lower(),
                    'interface': parts[3]
                })
        
        return mac_entries
    
    async def get_arp_table(self) -> List[Dict[str, Any]]:
        """Get ARP table
        
        Command: show arp
        """
        try:
            output = await self.execute_command("show arp")
            return self._parse_arp_table(output)
        except Exception as e:
            logger.error(f"Error getting ARP table: {str(e)}")
            return []
    
    def _parse_arp_table(self, output: str) -> List[Dict[str, Any]]:
        """Parse ARP table output"""
        arp_entries = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip headers and separators
            if not line or '----' in line or 'Protocol' in line or 'Address' in line:
                continue
            
            # Skip prompts
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Parse ARP entry
            # Format: Internet  192.168.1.1  -  0011.2233.4455  ARPA  Vlan1
            parts = line.split()
            if len(parts) >= 4:
                arp_entries.append({
                    'ip_address': parts[1] if len(parts) > 1 else '',
                    'mac_address': parts[3] if len(parts) > 3 else parts[2],
                    'interface': parts[-1],
                    'age': '-'
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
            output = await self.execute_command("write memory")
            return "success" in output.lower() or "ok" in output.lower()
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
            
            # Hostname
            if 'hostname' in line.lower():
                match = re.search(r'hostname\s+(\S+)', line, re.IGNORECASE)
                if match:
                    info['hostname'] = match.group(1)
            
            # Model
            if 'model' in line.lower() or 'product' in line.lower():
                match = re.search(r'(?:model|product)\s*:\s*(.+)', line, re.IGNORECASE)
                if match:
                    info['model'] = match.group(1).strip()
            
            # Software version
            if 'version' in line.lower() and 'software' in line.lower():
                match = re.search(r'version\s+(\S+)', line, re.IGNORECASE)
                if match:
                    info['version'] = match.group(1)
            
            # Uptime
            if 'uptime' in line.lower():
                match = re.search(r'uptime\s+is\s+(.+)', line, re.IGNORECASE)
                if match:
                    info['uptime'] = match.group(1).strip()
            
            # Serial number
            if 'serial' in line.lower():
                match = re.search(r'serial\s*(?:number|#)?\s*:\s*(\S+)', line, re.IGNORECASE)
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
        """Discover supported commands on Ruijie switch"""
        try:
            # Commands to test
            test_commands = [
                ('show version', 'System version and hardware info'),
                ('show interface', 'All interfaces detailed'),
                ('show interface status', 'Interface status summary'),
                ('show interfaces description', 'Interface descriptions'),
                ('show interfaces switchport', 'Switchport configuration'),
                ('show ip interface brief', 'IP interface brief'),
                ('show vlan', 'VLAN database'),
                ('show vlan id 1', 'Specific VLAN details'),
                ('show vlan summary', 'VLAN summary'),
                ('show mac-address-table', 'MAC address table'),
                ('show arp', 'ARP table'),
                ('show ip arp', 'IP ARP table'),
                ('show spanning-tree', 'Spanning tree status'),
                ('show spanning-tree summary', 'Spanning tree summary'),
                ('show running-config', 'Running configuration'),
                ('show startup-config', 'Startup configuration'),
                ('show interfaces trunk', 'Trunk interfaces'),
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
        """Discover VLAN to port mappings on Ruijie switch"""
        try:
            raw_outputs = {}
            
            # Get VLAN information
            vlan_output = await self.execute_command('show vlan')
            raw_outputs['show_vlan'] = vlan_output
            
            # Get switchport information
            switchport_output = await self.execute_command('show interfaces switchport')
            raw_outputs['show_interfaces_switchport'] = switchport_output
            
            # Get interface status
            status_output = await self.execute_command('show interface status')
            raw_outputs['show_interface_status'] = status_output
            
            # Parse VLANs
            vlans = []
            vlan_dict = {}
            
            for line in vlan_output.split('\n'):
                line = line.strip()
                # Match VLAN lines: "   1 VLAN0001                         STATIC    Gi0/1, Gi0/2, ..."
                match = re.match(r'(\d+)\s+(\S+)\s+(STATIC|DYNAMIC)\s+(.+)', line)
                if match:
                    vlan_id = match.group(1)
                    vlan_name = match.group(2)
                    vlan_status = match.group(3)
                    ports_str = match.group(4)
                    
                    # Parse ports (may span multiple lines)
                    ports = [p.strip() for p in ports_str.split(',') if p.strip()]
                    
                    vlan_info = {
                        'vlan_id': int(vlan_id),
                        'name': vlan_name,
                        'status': vlan_status.lower(),
                        'ports': ports
                    }
                    vlans.append(vlan_info)
                    vlan_dict[int(vlan_id)] = vlan_info
            
            # Parse port configurations
            ports = {}
            current_interface = None
            
            for line in switchport_output.split('\n'):
                line = line.strip()
                
                # Match interface line: "GigabitEthernet 0/1   enabled    ACCESS    1      1      Disabled  ALL"
                match = re.match(r'(\S+\s+\S+)\s+enabled\s+(\S+)\s+(\d+)\s+(\d+)\s+\S+\s+(.+)', line)
                if match:
                    interface = match.group(1).replace(' ', '')  # Remove space: "GigabitEthernet0/1"
                    mode = match.group(2).lower()
                    access_vlan = int(match.group(3))
                    native_vlan = int(match.group(4))
                    vlan_lists = match.group(5).strip()
                    
                    port_info = {
                        'interface': interface,
                        'mode': mode,
                        'access_vlan': access_vlan if mode == 'access' else None,
                        'native_vlan': native_vlan if mode == 'trunk' else None,
                        'allowed_vlans': vlan_lists if mode == 'trunk' else None,
                        'status': 'unknown'
                    }
                    
                    ports[interface] = port_info
            
            # Add status information from interface status
            for line in status_output.split('\n'):
                line = line.strip()
                parts = line.split()
                
                if len(parts) >= 3:
                    interface = parts[0].replace(' ', '')
                    if interface in ports:
                        ports[interface]['status'] = parts[1]
                        if len(parts) > 2:
                            ports[interface]['vlan'] = parts[2]
            
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
        """Get Ruijie switch capabilities and features"""
        try:
            # Get system info
            system_info = await self.get_system_info()
            
            # Get interfaces to count ports
            interfaces = await self.get_interfaces()
            
            # Get VLANs to determine VLAN range
            vlans = await self.get_vlans()
            vlan_ids = [v.get('vlan_id') for v in vlans if v.get('vlan_id')]
            
            capabilities = {
                'manufacturer': 'Ruijie',
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
                    'port_statistics',
                    'configuration_save',
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
                    iface.get('interface', '').split('0/')[0] if '0/' in iface.get('interface', '') else 'Unknown'
                    for iface in interfaces
                )),
                'protocol': self.device.protocol,
                'management_ip': self.device.host,
            }
            
            return capabilities
            
        except Exception as e:
            logger.error(f"Error getting switch capabilities: {str(e)}")
            return {
                'manufacturer': 'Ruijie',
                'error': str(e)
            }

