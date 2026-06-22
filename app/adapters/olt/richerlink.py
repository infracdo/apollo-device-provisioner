"""
RicherLink OLT Adapter

Implementation for RicherLink OLT devices.
RicherLink OLTs use command-line interface via SSH/Telnet.
"""
import re
from typing import Dict, Any, List, Optional
from app.adapters.olt.base_olt import BaseOLTAdapter
from app.connectors.ssh_connector import SSHConnector
from app.connectors.telnet_connector import TelnetConnector
from app.utils.logging import logger


class RicherLinkOLTAdapter(BaseOLTAdapter):
    """RicherLink OLT implementation"""
    
    def __init__(self, device_config: Dict[str, Any]):
        super().__init__(device_config)
        self.command_mode = 0  # 0=normal, 1=enable, 2=config
        
    async def connect(self) -> bool:
        """Establish connection to RicherLink OLT"""
        port = self.device_config.get('port', 22)
        
        if port == 23:
            self.connector = TelnetConnector(
                host=self.device_config['host'],
                port=port,
                username=self.device_config['username'],
                password=self.device_config['password']
            )
        else:
            self.connector = SSHConnector(
                host=self.device_config['host'],
                port=port,
                username=self.device_config['username'],
                password=self.device_config['password']
            )
        
        connected = await self.connector.connect()
        self.is_connected = connected
        
        if connected:
            logger.info(f"Connected to RicherLink OLT at {self.device_config['host']}")
        
        return connected
    
    async def disconnect(self) -> bool:
        """Close connection"""
        if self.connector:
            logger.info(f"Disconnecting from RicherLink OLT at {self.device_config['host']}")
            return await self.connector.disconnect()
        return True
    
    async def execute_command(self, command: str) -> str:
        """Execute command on RicherLink OLT"""
        if not self.is_connected or not self.connector:
            raise ConnectionError("Not connected to device")
        
        # Handle command mode changes
        if command == 'enable':
            self.command_mode = max(1, self.command_mode)
        elif command in ['configure terminal', 'config']:
            self.command_mode = max(2, self.command_mode)
        elif command in ['quit', 'exit', 'end']:
            self.command_mode = max(0, self.command_mode - 1)
        
        output = await self.connector.execute(command)
        
        # Clean up output - remove page breaks and ANSI codes
        output = output.replace("--More--", "")
        output = output.replace("\x1b[42D", "")
        output = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', output)  # Remove ANSI escape sequences
        
        self.log_command(command, output)
        return output
    
    async def get_device_info(self) -> Dict[str, Any]:
        """Get RicherLink OLT device information"""
        try:
            # Get running config to parse hostname
            config = await self.execute_command("show running-config")
            
            # Get memory info
            memory = await self.execute_command("show memory")
            
            device_info = {
                'manufacturer': 'RicherLink',
                'model': 'Corona OLT'
            }
            
            # Parse hostname from config
            hostname_match = re.search(r'hostname\s+(\S+)', config)
            if hostname_match:
                device_info['hostname'] = hostname_match.group(1)
            
            # Parse memory usage percentage
            # Format: "Memory usage: 45.2%" or similar
            memory_match = re.search(r'[\d.]+%', memory)
            if memory_match:
                device_info['memory_usage'] = memory_match.group(0)
            
            return device_info
            
        except Exception as e:
            logger.error(f"Error getting device info from RicherLink OLT: {str(e)}")
            return {
                'manufacturer': 'RicherLink',
                'error': str(e)
            }
    
    async def provision_onu(self, onu_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provision ONU on RicherLink OLT
        
        RicherLink OLT command structure:
        - Enter config mode
        - Enter interface mode for PON port
        - Add ONU with serial number
        - Configure line profile and service profile
        - Configure VLAN and services
        """
        try:
            # Extract parameters
            serial_no = onu_config['serial_no']
            frame = onu_config.get('frame', 0)
            slot = onu_config['slot']
            port = onu_config['port']
            ont_id = onu_config.get('ont_id')  # If not provided, auto-assign
            line_profile = onu_config['line_profile_id']
            service_profile = onu_config['service_profile_id']
            vlan = onu_config['vlan']
            description = onu_config.get('description', '')
            wan_mode = onu_config.get('wan_mode', 'dhcp')
            
            # Enter enable and configuration mode
            await self.execute_command("enable")
            enable_pwd = self.device_config.get('enable_password')
            if enable_pwd:
                await self.execute_command(enable_pwd)
            
            await self.execute_command("configure terminal")
            
            # Enter PON interface mode
            pon_interface = f"interface EPON{frame}/{slot}:{port}"
            await self.execute_command(pon_interface)
            
            # Find available ONT ID if not specified
            if not ont_id:
                # Get list of existing ONUs to find next available ID
                onts_output = await self.execute_command("show onu status")
                existing_ids = re.findall(r'ONU\s+(\d+)', onts_output)
                existing_ids = [int(x) for x in existing_ids]
                ont_id = 1
                while ont_id in existing_ids and ont_id < 128:
                    ont_id += 1
                    
                if ont_id >= 128:
                    return {
                        'status': 'error',
                        'message': 'No available ONT ID slots',
                        'ont_id': None
                    }
            
            # Add ONU with serial number authentication
            # RicherLink: onu <ont-id> type <type> sn <serial>
            add_cmd = f"onu {ont_id} type ALL sn {serial_no}"
            output = await self.execute_command(add_cmd)
            
            # Check if ONU was added successfully
            if "Error" in output or "fail" in output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to add ONU: {output}',
                    'output': output,
                    'ont_id': None
                }
            
            # Configure ONU line profile
            await self.execute_command(f"onu {ont_id} line-profile {line_profile}")
            
            # Configure ONU service profile
            await self.execute_command(f"onu {ont_id} service-profile {service_profile}")
            
            # Set ONU description if provided
            if description:
                # Clean description for command line
                safe_desc = description.replace('"', '').replace("'", "")[:32]
                await self.execute_command(f"onu {ont_id} description {safe_desc}")
            
            # Exit interface mode
            await self.execute_command("exit")
            
            # Configure ONU VLAN and WAN service
            await self.execute_command(f"interface ONU{frame}/{slot}:{port}.{ont_id}")
            
            # Configure service port with VLAN
            if wan_mode == 'bridge':
                await self.execute_command(f"service-port {vlan} vlan {vlan}")
            else:  # dhcp mode
                await self.execute_command(f"ip dhcp enable")
                await self.execute_command(f"service-port {vlan} vlan {vlan} user-vlan {vlan}")
            
            # Enable ONU ports (typically 4 ethernet ports)
            for eth_port in range(1, 5):
                await self.execute_command(f"port eth {eth_port} state enable")
            
            # Exit ONU interface mode
            await self.execute_command("exit")
            
            # Exit configuration mode
            await self.execute_command("end")
            
            # Save configuration
            await self.execute_command("write")
            
            logger.info(f"ONU {serial_no} provisioned successfully on RicherLink OLT with ONT ID {ont_id}")
            
            return {
                'status': 'success',
                'ont_id': ont_id,
                'message': f'ONU provisioned successfully with ID {ont_id}',
                'serial_no': serial_no,
                'vlan': vlan
            }
            
        except Exception as e:
            logger.error(f"Error provisioning ONU on RicherLink OLT: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'ont_id': None
            }
    
    async def remove_onu(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Remove ONU from RicherLink OLT"""
        try:
            frame = onu_location.get('frame', 0)
            slot = onu_location['slot']
            port = onu_location['port']
            ont_id = onu_location['ont_id']
            
            # Enter enable and configuration mode
            await self.execute_command("enable")
            enable_pwd = self.device_config.get('enable_password')
            if enable_pwd:
                await self.execute_command(enable_pwd)
                
            await self.execute_command("configure terminal")
            
            # Enter PON interface mode
            pon_interface = f"interface EPON{frame}/{slot}:{port}"
            await self.execute_command(pon_interface)
            
            # Remove ONU
            output = await self.execute_command(f"no onu {ont_id}")
            
            await self.execute_command("exit")
            await self.execute_command("end")
            await self.execute_command("write")
            
            if "Error" in output or "fail" in output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to remove ONU: {output}'
                }
            
            logger.info(f"ONU removed from RicherLink OLT: slot {slot}, port {port}, ONT ID {ont_id}")
            
            return {
                'status': 'success',
                'message': 'ONU removed successfully'
            }
            
        except Exception as e:
            logger.error(f"Error removing ONU from RicherLink OLT: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def get_onts(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get list of ONTs/ONUs on the RicherLink OLT
        
        Uses discovered command: show ont register information ponid <1-8>
        """
        try:
            port = filters.get('port') if filters else None
            
            if port is not None:
                # Get ONTs for specific GPON port (1-8)
                output = await self.execute_command(f"show ont register information ponid {port}")
            else:
                # Get ONTs from all 8 GPON ports
                all_onts = []
                for p in range(1, 9):  # Ports 1-8
                    try:
                        output = await self.execute_command(f"show ont register information ponid {p}")
                        onts = self._parse_ont_register_info(output, p)
                        all_onts.extend(onts)
                    except Exception as e:
                        logger.warning(f"Error getting ONTs from port {p}: {str(e)}")
                        continue
                return all_onts
            
            # Parse single port output
            return self._parse_ont_register_info(output, port)
            
        except Exception as e:
            logger.error(f"Error getting ONTs from RicherLink OLT: {str(e)}")
            return []
    
    def _parse_ont_register_info(self, output: str, port: int) -> List[Dict[str, Any]]:
        """Parse output from 'show ont register information ponid X' command
        
        Actual format from Corona OLT:
        INTERFACE        SN              REGISTER TIME        TX(dBm)  RX(dBm)  ONT STATUS        REGISTER STATUS       
        ---------  --------------  -------------------------  -------  -------  ----------  --------------------------- 
            0      RLGM-FE1CB160   Thu Jan  1 00:00:00 1970     N/A      N/A     offline          offline config
        """
        onts = []
        lines = output.split('\n')
        
        # Find the header line and data lines
        in_data_section = False
        for line in lines:
            line_stripped = line.strip()
            
            # Skip empty lines
            if not line_stripped:
                continue
            
            # Skip summary lines with asterisks
            if line_stripped.startswith('*'):
                continue
            
            # Detect header (INTERFACE SN REGISTER)
            if 'INTERFACE' in line_stripped and 'SN' in line_stripped:
                in_data_section = True
                continue
            
            # Skip separator lines
            if '----' in line_stripped or '=====' in line_stripped:
                continue
            
            if not in_data_section:
                continue
            
            # Skip summary statistics lines (e.g., "online:0 offline:1")
            if 'online:' in line_stripped or 'config-ok:' in line_stripped:
                continue
            
            # Skip prompt lines
            if '>' in line_stripped and len(line_stripped) < 50:
                continue
            
            # Parse data line format: 0  RLGM-FE1CB160  Thu Jan  1 00:00:00 1970  N/A  N/A  offline  offline config
            parts = line_stripped.split()
            
            # Need at least: interface, serial, date(multiple parts), tx, rx, status
            if len(parts) < 9:
                continue
            
            interface = parts[0]
            
            # Interface should be numeric (0, 1, 2, etc.)
            if not interface.isdigit():
                continue
            
            ont_id = int(interface)
            serial = parts[1]
            
            # Validate serial number format (should be alphanumeric with hyphens)
            # RicherLink serials typically look like: RLGM-FE1CB160
            if not re.match(r'^[A-Z0-9-]+$', serial, re.IGNORECASE):
                continue
            
            # Parse register time: "Thu Jan 1 00:00:00 1970" (5 parts)
            # Format: parts[2-6] = Day Month Date Time Year
            if len(parts) >= 11:
                register_time = ' '.join(parts[2:7])  # "Thu Jan 1 00:00:00 1970"
                tx_power = parts[7]
                rx_power = parts[8]
                status = parts[9]
                register_status = ' '.join(parts[10:]) if len(parts) > 10 else ''
            else:
                # Fallback if format is different
                register_time = ' '.join(parts[2:-4]) if len(parts) > 6 else 'unknown'
                tx_power = parts[-4] if len(parts) > 4 else 'N/A'
                rx_power = parts[-3] if len(parts) > 3 else 'N/A'
                status = parts[-2] if len(parts) > 2 else 'unknown'
                register_status = parts[-1] if len(parts) > 1 else ''
            
            onts.append({
                'port': port,
                'ont_id': ont_id,
                'serial_no': serial,
                'interface': f"gpon{port}/{ont_id}",
                'register_time': register_time,
                'tx_power': tx_power,
                'rx_power': rx_power,
                'status': status,
                'register_status': register_status
            })
        
        return onts
    
    async def get_ont_status(self, ont_location: Dict[str, Any]) -> Dict[str, Any]:
        """Get ONT status and statistics from RicherLink OLT
        
        Uses discovered commands:
        - show ont status-info ponid <port> ontid <id>
        - show ont detail-info ponid <port> ontid <id>
        - show ont statistic ponid <port> ontid <id>
        """
        try:
            port = ont_location['port']
            ont_id = ont_location['ont_id']
            
            # Get ONT status info
            status_output = await self.execute_command(
                f"show ont status-info ponid {port} ontid {ont_id}"
            )
            
            # Get ONT detailed info
            detail_output = await self.execute_command(
                f"show ont detail-info ponid {port} ontid {ont_id}"
            )
            
            # Get ONT statistics
            stats_output = await self.execute_command(
                f"show ont statistic ponid {port} ontid {ont_id}"
            )
            
            # Parse outputs
            status_data = {
                'port': port,
                'ont_id': ont_id,
                'status': 'unknown'
            }
            
            # Parse status-info output
            status_data.update(self._parse_ont_status_info(status_output))
            
            # Parse detail-info output
            status_data.update(self._parse_ont_detail_info(detail_output))
            
            # Parse statistics output
            status_data['statistics'] = self._parse_ont_statistics(stats_output)
            
            return status_data
            
        except Exception as e:
            logger.error(f"Error getting ONT status from RicherLink OLT: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _parse_ont_status_info(self, output: str) -> Dict[str, Any]:
        """Parse output from 'show ont status-info' command
        
        Actual format from Corona OLT:
        GPON ONU status:not_configured
        ONU SN: : 0
        Additional guard time (in bytes) after all bursts for this ONU  : 0
        """
        data = {}
        
        # Extract key-value pairs (format: "Key: value" or "Key:value")
        for line in output.split('\n'):
            line = line.strip()
            
            # Skip empty lines and prompts
            if not line or '>' in line:
                continue
            
            if ':' in line:
                # Split only on first colon
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower().replace(' ', '_').replace('(', '').replace(')', '')
                    value = parts[1].strip()
                    
                    # Handle double colon case (ONU SN: : 0)
                    if value.startswith(':'):
                        value = value[1:].strip()
                    
                    # Convert numeric values
                    if key in ['tx_power', 'rx_power', 'distance', 'temperature', 'additional_guard_time_in_bytes_after_all_bursts_for_this_onu']:
                        try:
                            data[key] = float(value) if value and value != 'N/A' else None
                        except ValueError:
                            data[key] = value
                    else:
                        data[key] = value
        
        return data
    
    def _parse_ont_detail_info(self, output: str) -> Dict[str, Any]:
        """Parse output from 'show ont detail-info' command
        
        Actual format from Corona OLT (when ONT is offline/not configured):
        % unkown(0):0/1/0 is not activation online
        
        When online, it would show detailed info
        """
        data = {}
        
        # Check for error messages
        if 'not activation online' in output or 'not configured' in output:
            data['detail_status'] = 'offline_or_not_configured'
            data['message'] = output.strip()
            return data
        
        # Parse key-value pairs
        for line in output.split('\n'):
            line = line.strip()
            
            # Skip empty lines and prompts
            if not line or '>' in line:
                continue
            
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower().replace(' ', '_').replace('(', '').replace(')', '')
                    value = parts[1].strip()
                    data[key] = value
        
        return data
    
    def _parse_ont_statistics(self, output: str) -> Dict[str, Any]:
        """Parse output from 'show ont statistic' command"""
        stats = {}
        
        # Parse statistics (format may vary - adapt based on actual output)
        for line in output.split('\n'):
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower().replace(' ', '_')
                value = value.strip()
                
                # Try to convert to int
                try:
                    stats[key] = int(value)
                except ValueError:
                    stats[key] = value
        
        return stats
    
    async def discover_onts(self, port: int) -> List[Dict[str, Any]]:
        """Discover unregistered/unconfigured ONTs on a GPON port
        
        Uses discovered command: show ont discover-info ponid <1-8>
        """
        try:
            output = await self.execute_command(f"show ont discover-info ponid {port}")
            return self._parse_ont_discover_info(output, port)
            
        except Exception as e:
            logger.error(f"Error discovering ONTs on port {port}: {str(e)}")
            return []
    
    def _parse_ont_discover_info(self, output: str, port: int) -> List[Dict[str, Any]]:
        """Parse output from 'show ont discover-info ponid X' command
        
        This command shows ONTs that are physically connected but not yet registered
        
        Expected format:
        INTERFACE        SN        RECORD  AUTH       DISCOVER_TIME             LOID              LPWD
        ---------  --------------  ------  ----  -----------------------  ----------------  ----------------
        <data lines or empty if none>
        """
        discovered = []
        lines = output.split('\n')
        
        # Find data lines after the header
        in_data_section = False
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Skip command echo
            if line.startswith('show ont discover-info'):
                continue
            
            # Skip prompts (ends with # or >)
            if line.endswith('#') or line.endswith('>'):
                continue
            
            # Detect header line (contains column names like INTERFACE, SN, etc.)
            if 'INTERFACE' in line.upper() and 'SN' in line.upper():
                in_data_section = True
                continue
            
            # Skip separator line (dashes)
            if set(line.replace(' ', '')) <= set('-'):
                continue
            
            # If we're in data section and line doesn't look like header/separator/prompt
            # then it's an ONT entry
            if in_data_section:
                # Split by whitespace
                parts = line.split()
                
                # Valid ONT entry should have multiple fields
                # Format: INTERFACE SN RECORD AUTH DISCOVER_TIME LOID LPWD
                if len(parts) >= 2:
                    discovered.append({
                        'port': port,
                        'interface': parts[0] if len(parts) > 0 else '',
                        'serial_no': parts[1] if len(parts) > 1 else '',
                        'record': parts[2] if len(parts) > 2 else '',
                        'auth': parts[3] if len(parts) > 3 else '',
                        'discover_time': ' '.join(parts[4:6]) if len(parts) > 5 else '',
                        'loid': parts[6] if len(parts) > 6 else '',
                        'status': 'discovered',
                        'raw_info': line
                    })
        
        return discovered
    
    async def get_running_config(self) -> str:
        """Get running configuration from RicherLink OLT
        
        Command: show running-config (requires enable mode)
        """
        try:
            # Enter enable mode with password handling
            await self._enter_enable_mode()
            
            # Execute show running-config
            output = await self.execute_command("show running-config")
            
            return output
        except Exception as e:
            logger.error(f"Error getting running config from RicherLink OLT: {str(e)}")
            return f"Error: {str(e)}"
    
    async def get_startup_config(self) -> str:
        """Get startup configuration from RicherLink OLT
        
        Command: show startup-config (requires enable mode)
        """
        try:
            # Enter enable mode with password handling
            await self._enter_enable_mode()
            
            # Execute show startup-config
            output = await self.execute_command("show startup-config")
            
            return output
        except Exception as e:
            logger.error(f"Error getting startup config from RicherLink OLT: {str(e)}")
            return f"Error: {str(e)}"
    
    async def _enter_enable_mode(self):
        """Enter enable/privileged mode with password handling"""
        # Send enable command
        output = await self.execute_command("enable")
        
        # Check if password is required
        if "Password:" in output or "password:" in output:
            # Send enable password (same as login password for this device)
            enable_password = self.device_config.get('enable_password') or self.device_config.get('password')
            await self.connector.execute(enable_password)
    
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """Get interface information from RicherLink OLT
        
        Command: show interface
        """
        try:
            output = await self.execute_command("show interface")
            return self._parse_interfaces(output)
        except Exception as e:
            logger.error(f"Error getting interfaces from RicherLink OLT: {str(e)}")
            return []
    
    def _parse_interfaces(self, output: str) -> List[Dict[str, Any]]:
        """Parse interface output
        
        Looks for patterns like:
        gpon1 is up, line protocol is up
        Hardware is GPON
        MTU 1500 bytes, BW 1000000 Kbit
        """
        interfaces = []
        lines = output.split('\n')
        
        current_interface = None
        for line in lines:
            line = line.strip()
            
            # Detect interface header: "gpon1 is up, line protocol is up"
            if ' is ' in line and 'line protocol' in line:
                parts = line.split()
                if len(parts) >= 2:
                    interface_name = parts[0]
                    status = 'up' if 'up' in line else 'down'
                    protocol_status = 'up' if 'line protocol is up' in line else 'down'
                    
                    current_interface = {
                        'name': interface_name,
                        'status': status,
                        'protocol': protocol_status
                    }
                    interfaces.append(current_interface)
            
            # Parse additional info for current interface
            elif current_interface:
                if 'Hardware is' in line:
                    hw_match = re.search(r'Hardware is (.+)', line)
                    if hw_match:
                        current_interface['hardware'] = hw_match.group(1).strip()
                
                elif 'MTU' in line:
                    mtu_match = re.search(r'MTU (\d+)', line)
                    if mtu_match:
                        current_interface['mtu'] = int(mtu_match.group(1))
                    
                    bw_match = re.search(r'BW ([\d]+)', line)
                    if bw_match:
                        current_interface['bandwidth'] = int(bw_match.group(1))
                
                elif 'packets input' in line.lower() or 'packets output' in line.lower():
                    # Parse packet stats
                    numbers = re.findall(r'(\d+) packets', line)
                    if 'input' in line.lower() and numbers:
                        current_interface['input_packets'] = int(numbers[0])
                    elif 'output' in line.lower() and numbers:
                        current_interface['output_packets'] = int(numbers[0])
        
        return interfaces
    
    async def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information from RicherLink OLT
        
        Command: show memory
        """
        try:
            output = await self.execute_command("show memory")
            return self._parse_memory(output)
        except Exception as e:
            logger.error(f"Error getting memory info from RicherLink OLT: {str(e)}")
            return {}
    
    def _parse_memory(self, output: str) -> Dict[str, Any]:
        """Parse memory output"""
        memory_info = {}
        
        for line in output.split('\n'):
            line = line.strip()
            
            # Look for memory usage patterns
            # "Memory usage: 45.2%"
            # "Total memory: 512 MB"
            # "Free memory: 280 MB"
            
            if 'usage' in line.lower() and '%' in line:
                match = re.search(r'([\d.]+)%', line)
                if match:
                    memory_info['usage_percent'] = float(match.group(1))
            
            if 'total' in line.lower():
                match = re.search(r'(\d+)\s*(MB|KB|GB)', line, re.IGNORECASE)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2).upper()
                    memory_info['total'] = f"{value} {unit}"
                    # Convert to MB
                    if unit == 'GB':
                        memory_info['total_mb'] = value * 1024
                    elif unit == 'KB':
                        memory_info['total_mb'] = value / 1024
                    else:
                        memory_info['total_mb'] = value
            
            if 'free' in line.lower():
                match = re.search(r'(\d+)\s*(MB|KB|GB)', line, re.IGNORECASE)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2).upper()
                    memory_info['free'] = f"{value} {unit}"
            
            if 'used' in line.lower() and 'usage' not in line.lower():
                match = re.search(r'(\d+)\s*(MB|KB|GB)', line, re.IGNORECASE)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2).upper()
                    memory_info['used'] = f"{value} {unit}"
        
        return memory_info
    
    async def get_system_logs(self, lines: int = 100) -> List[str]:
        """Get system logs from RicherLink OLT
        
        Note: 'show log' command may not be available on this device.
        Returns message if not available.
        """
        try:
            # Try show log command (may not work)
            output = await self.execute_command("show log")
            
            # Check if command failed
            if "Invalid input" in output or "%" in output:
                return ["Note: System logs command not available on this device type"]
            
            log_lines = output.split('\n')
            
            # Filter out empty lines and prompts
            filtered_logs = [
                line for line in log_lines
                if line.strip() and '>' not in line and '#' not in line and not line.startswith('show log')
            ]
            
            # Return last N lines
            return filtered_logs[-lines:] if lines and filtered_logs else filtered_logs
            
        except Exception as e:
            logger.error(f"Error getting logs from RicherLink OLT: {str(e)}")
            return [f"Error: {str(e)}"]
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get configured VLANs on the RicherLink OLT
        
        Actual format:
        VLAN ID  Name            State   Instance  L3 Interface Member ports                   
        ======= ================ ======= ========= ============ ===============================
        1       default          ACTIVE  0(MSTP)   vlan1.1      gpon2(u) gpon3(u) gpon4(u)
        22      pppoe            ACTIVE  0(MSTP)   -            ge2(t)
        """
        try:
            output = await self.execute_command("show vlan")
            
            vlans = []
            lines = output.split('\n')
            
            in_data_section = False
            for line in lines:
                line_stripped = line.strip()
                
                # Skip empty lines
                if not line_stripped:
                    continue
                
                # Detect header
                if 'VLAN ID' in line_stripped and 'Name' in line_stripped:
                    in_data_section = True
                    continue
                
                # Skip separator
                if '=====' in line_stripped:
                    continue
                
                if not in_data_section:
                    continue
                
                # Skip prompts
                if '>' in line_stripped or '#' in line_stripped:
                    break
                
                # Parse VLAN line: "1       default          ACTIVE  0(MSTP)   vlan1.1      ..."
                parts = line_stripped.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    vlan_id = int(parts[0])
                    name = parts[1] if len(parts) > 1 else f"VLAN{vlan_id}"
                    state = parts[2] if len(parts) > 2 else 'UNKNOWN'
                    instance = parts[3] if len(parts) > 3 else '-'
                    l3_interface = parts[4] if len(parts) > 4 else '-'
                    
                    # Member ports are rest of the line
                    member_ports = ' '.join(parts[5:]) if len(parts) > 5 else ''
                    
                    vlans.append({
                        'vlan_id': vlan_id,
                        'name': name,
                        'state': state,
                        'instance': instance,
                        'l3_interface': l3_interface,
                        'member_ports': member_ports
                    })
            
            return vlans
            
        except Exception as e:
            logger.error(f"Error getting VLANs from RicherLink OLT: {str(e)}")
            return []
    
    async def get_boards(self) -> List[Dict[str, Any]]:
        """Get board/card information from RicherLink OLT"""
        try:
            await self.execute_command("enable")
            output = await self.execute_command("show card")
            
            boards = []
            lines = output.split('\n')
            
            for line in lines:
                # Parse board/card line
                match = re.search(r'Slot\s+(\d+)\s+:\s+(\w+)', line)
                if match:
                    slot, board_type = match.groups()
                    boards.append({
                        'slot': int(slot),
                        'type': board_type,
                        'status': 'online'  # RicherLink specific parsing
                    })
            
            return boards
            
        except Exception as e:
            logger.error(f"Error getting boards from RicherLink OLT: {str(e)}")
            return []
    
    async def reboot_ont(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Reboot ONU on RicherLink OLT"""
        try:
            frame = onu_location.get('frame', 0)
            slot = onu_location['slot']
            port = onu_location['port']
            ont_id = onu_location['ont_id']
            
            await self.execute_command("enable")
            enable_pwd = self.device_config.get('enable_password')
            if enable_pwd:
                await self.execute_command(enable_pwd)
                
            await self.execute_command("configure terminal")
            
            # Enter PON interface
            pon_interface = f"interface EPON{frame}/{slot}:{port}"
            await self.execute_command(pon_interface)
            
            # Reboot ONU
            output = await self.execute_command(f"onu {ont_id} reset")
            
            await self.execute_command("exit")
            await self.execute_command("end")
            
            if "Error" in output or "fail" in output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to reboot ONU: {output}'
                }
            
            logger.info(f"ONU rebooted on RicherLink OLT: slot {slot}, port {port}, ONT ID {ont_id}")
            
            return {
                'status': 'success',
                'message': 'ONU rebooted successfully'
            }
            
        except Exception as e:
            logger.error(f"Error rebooting ONU on RicherLink OLT: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
