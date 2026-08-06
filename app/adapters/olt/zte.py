"""
ZTE OLT Adapter

ZTE OLT device implementation using SSH/Telnet.
Supports ZTE C320 and similar models.

Working Commands discovered:
- show card: Rack/Shelf/Slot/Card information
- show running-config: Configuration
- show gpon onu state: ONU states
- show gpon onu detail gpon-onu_1/1/1:X: Detailed ONU info
- show system-group: System information
"""
from typing import Dict, Any, List, Optional
import asyncio
import re

from app.adapters.olt.base_olt import BaseOLTAdapter
from app.connectors.ssh_connector import SSHConnector
from app.connectors.telnet_connector import TelnetConnector
from app.utils.logging import logger
from app.config import settings


class ZTEOLTAdapter(BaseOLTAdapter):
    """ZTE OLT adapter implementation"""
    
    def __init__(self, device_config: Dict[str, Any]):
        super().__init__(device_config)
        self.connector = None
        self.is_connected = False
        
    async def connect(self) -> bool:
        """Establish connection to ZTE OLT"""
        port = self.device_config.get('port', 22)
        protocol = 'telnet' if (port == 23 or self.device_config.get('protocol', 'ssh') == 'telnet') else 'ssh'
        
        # Log credentials from device config (mask password)
        username = self.device_config.get('username', '')
        password = self.device_config.get('password', '')
        masked_pwd = password[:2] + '*' * (len(password) - 2) if len(password) > 2 else '*' * len(password)
        logger.info(f"[ZTE CONNECT] Connecting to {self.device_config['host']}:{port} via {protocol.upper()}")
        logger.info(f"[ZTE CONNECT] Using credentials - Username: '{username}' | Password: '{masked_pwd}' (length: {len(password)})")
        logger.debug(f"[ZTE CONNECT] Actual credentials from DB - Username: '{username}' | Password: '{password}'")
        
        if port == 23 or self.device_config.get('protocol', 'ssh') == 'telnet':
            self.connector = TelnetConnector(
                host=self.device_config['host'],
                port=port,
                username=username,
                password=password
            )
        else:
            self.connector = SSHConnector(
                host=self.device_config['host'],
                port=port,
                username=username,
                password=password
            )
        
        try:
            connected = await self.connector.connect()
            self.is_connected = connected
            
            if connected:
                logger.info(f"[ZTE CONNECT] Successfully connected to ZTE OLT at {self.device_config['host']}")
                
                # Check what reader/writer attributes we have
                has_direct_access = hasattr(self.connector, 'writer') and hasattr(self.connector, 'reader')
                logger.debug(f"[ZTE CONNECT] Direct reader/writer access: {has_direct_access}")
                
                # Disable pagination to avoid --More-- prompts
                try:
                    logger.debug(f"[ZTE CONNECT] Attempting to disable pagination...")
                    await self.connector.execute("terminal length 0")
                    logger.info(f"[ZTE CONNECT] Disabled pagination (terminal length 0)")
                except Exception as e:
                    logger.warning(f"[ZTE CONNECT] Could not disable pagination: {e}")
            else:
                logger.error(f"[ZTE CONNECT] Failed to connect to {self.device_config['host']}")
            
            return connected
            
        except PermissionError:
            # Authentication failed - propagate to API layer
            self.is_connected = False
            logger.error(f"[ZTE CONNECT] Authentication failed for {self.device_config['host']}")
            raise
    
    async def disconnect(self) -> bool:
        """Close connection"""
        if self.connector:
            logger.info(f"Disconnecting from ZTE OLT at {self.device_config['host']}")
            self.is_connected = False
            return await self.connector.disconnect()
        return True
    
    async def _check_and_reauth(self) -> bool:
        """Check if ZTE is prompting for credentials and re-authenticate if needed
        
        Returns:
            bool: True if authenticated/ready, False if failed
        """
        if not hasattr(self.connector, 'writer') or not hasattr(self.connector, 'reader'):
            return True  # Can't check, assume OK
        
        try:
            # Send Enter to check current state
            self.connector.writer.write('\n')
            await self.connector.writer.drain()
            await asyncio.sleep(0.3)
            
            # Read what comes back
            prompt = ''
            try:
                prompt = await asyncio.wait_for(
                    self.connector.reader.read(4096),
                    timeout=2.0
                )
                logger.debug(f"[ZTE AUTH CHECK] Received prompt: {repr(prompt[:200])}")
            except asyncio.TimeoutError:
                logger.debug("[ZTE AUTH CHECK] No prompt received (timeout) - assuming authenticated")
                # No response is OK, might be already at prompt
                return True
            
            prompt_lower = prompt.lower()
            logger.debug(f"[ZTE AUTH CHECK] Prompt lowercase: {repr(prompt_lower[:200])}")
            
            # Check if asking for username
            if 'username:' in prompt_lower or 'login:' in prompt_lower:
                logger.info("ZTE requesting username, re-authenticating...")
                self.connector.writer.write(self.device_config['username'] + '\n')
                await self.connector.writer.drain()
                await asyncio.sleep(0.5)
                
                # Read password prompt
                pwd_prompt = await asyncio.wait_for(
                    self.connector.reader.read(4096),
                    timeout=2.0
                )
                
                if 'password:' in pwd_prompt.lower():
                    self.connector.writer.write(self.device_config['password'] + '\n')
                    await self.connector.writer.drain()
                    await asyncio.sleep(0.5)
                    
                    # Read login response
                    await asyncio.wait_for(
                        self.connector.reader.read(4096),
                        timeout=2.0
                    )
                    logger.info("Re-authentication completed")
                    return True
                    
            # Check if asking for password directly
            elif 'password:' in prompt_lower:
                logger.info("ZTE requesting password, re-authenticating...")
                self.connector.writer.write(self.device_config['password'] + '\n')
                await self.connector.writer.drain()
                await asyncio.sleep(0.5)
                
                # Read response
                await asyncio.wait_for(
                    self.connector.reader.read(4096),
                    timeout=2.0
                )
                logger.info("Re-authentication completed")
                return True
            
            # If we see the prompt (#), we're good
            elif '#' in prompt or 'ZXAN#' in prompt:
                return True
            
            # Otherwise, assume we're OK
            return True
            
        except Exception as e:
            logger.warning(f"Error checking auth state: {e}")
            return True  # Continue anyway
    
    async def execute_command(self, command: str, timeout: float = 5.0) -> str:
        """Execute command on ZTE OLT
        
        ZTE-specific implementation that works better with ZTE's CLI behavior.
        Includes automatic re-authentication if session expires.
        """
        if not self.is_connected or not self.connector:
            raise ConnectionError("Not connected to device")
        
        # Log command being sent
        logger.info(f"[ZTE CMD SENT] {self.device_config['host']}: {command}")
        
        # For ZTE, we use direct reader/writer access for better control
        if hasattr(self.connector, 'writer') and hasattr(self.connector, 'reader'):
            try:
                logger.debug(f"[ZTE CMD] Using direct reader/writer for command: {command}")
                # Check authentication state and re-auth if needed
                #await self._check_and_reauth()
                
                # Send command
                command_with_newline = command + '\n'
                logger.debug(f"[ZTE CMD] Writing command to device: {repr(command_with_newline)}")
                self.connector.writer.write(command_with_newline)
                await self.connector.writer.drain()
                logger.debug(f"[ZTE CMD] Command sent and drained, waiting for response...")
                
                # Read response with ZTE-specific handling
                output = ''
                iteration = 0
                logger.debug(f"[ZTE CMD] Starting response read loop (max 40 iterations)")
                for iteration in range(40):  # Max 40 iterations
                    try:
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Waiting for data (timeout 1.5s)...")
                        chunk = await asyncio.wait_for(
                            self.connector.reader.read(8192),
                            timeout=1.5
                        )
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Read {len(chunk)} bytes")
                        
                        if not chunk:
                            logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Empty chunk received, breaking")
                            break
                        
                        output += chunk
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Total output now {len(output)} bytes")
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Chunk content: {repr(chunk)}")
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Last 100 chars of output: {repr(output[-100:])}")
                        
                        # Check for prompt (ZXAN#) at end
                        prompt_found = chunk.endswith('#') or '\r\nZXAN#' in chunk or '\nZXAN#' in chunk
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Checking for prompt - ends with '#': {chunk.endswith('#')}, contains ZXAN#: {'ZXAN#' in chunk}")
                        
                        if prompt_found:
                            logger.info(f"[ZTE CMD] Iteration {iteration+1}: Found prompt marker in chunk, command complete")
                            break
                            
                    except asyncio.TimeoutError:
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Read timeout - current output length: {len(output)}")
                        logger.debug(f"[ZTE CMD] Iteration {iteration+1}: Current output tail: {repr(output[-100:] if output else 'empty')}")
                        
                        # If we have some output and it ends with #, we're done
                        if output and (output.strip().endswith('#') or 'ZXAN#' in output[-20:]):
                            logger.info(f"[ZTE CMD] Output ends with prompt marker, command complete")
                            break
                        # Otherwise, no more data
                        if len(output) > 50:  # We got something, that's enough
                            logger.warning(f"[ZTE CMD] Timeout but have {len(output)} bytes, accepting as complete")
                            break
                        logger.error(f"[ZTE CMD] Timeout with insufficient data ({len(output)} bytes)")
                        logger.error(f"[ZTE CMD] Output received so far: {repr(output)}")
                        raise  # Re-raise if we got nothing
                
                logger.info(f"[ZTE CMD] Finished reading after {iteration+1} iterations, total: {len(output)} bytes")
                logger.debug(f"[ZTE CMD] Final output tail (last 200 chars): {repr(output[-200:])}")
                
                # Clean up output
                logger.debug(f"[ZTE CMD] Raw output before cleaning (first 200): {repr(output[:200])}")
                logger.debug(f"[ZTE CMD] Raw output before cleaning (last 200): {repr(output[-200:])}")
                output = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', output)  # Remove ANSI
                logger.debug(f"[ZTE CMD] Output after ANSI removal (first 200): {repr(output[:200])}")
                logger.debug(f"[ZTE CMD] Output after ANSI removal (last 200): {repr(output[-200:])}")
                
                # Log received output
                logger.info(f"[ZTE CMD RECV] {self.device_config['host']}: {len(output)} bytes received")
                logger.debug(f"[ZTE CMD OUTPUT] {self.device_config['host']}:\n{output}")
                
                if not output or len(output.strip()) == 0:
                    logger.warning(f"[ZTE CMD] Received empty output for command: {command}")
                
                self.log_command(command, output)
                return output
                
            except Exception as e:
                logger.error(f"[ZTE CMD ERROR] {self.device_config['host']}: Error executing command '{command}': {e}")
                logger.error(f"[ZTE CMD ERROR] Exception type: {type(e).__name__}")
                logger.error(f"[ZTE CMD ERROR] Current output length: {len(output) if 'output' in locals() else 0}")
                import traceback
                logger.error(f"[ZTE CMD ERROR] Traceback:\n{traceback.format_exc()}")
                raise
        else:
            # Fallback to connector's execute
            output = await self.connector.execute(command, handle_pagination=True)
            output = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', output)
            
            # Log received output
            logger.info(f"[ZTE CMD RECV] {self.device_config['host']}: {len(output)} bytes received")
            logger.debug(f"[ZTE CMD OUTPUT] {self.device_config['host']}:\n{output}")
            
            self.log_command(command, output)
            return output
    
    async def get_device_info(self) -> Dict[str, Any]:
        """Get ZTE OLT device information"""
        try:
            # Get system information
            system_output = await self.execute_command("show system-group")
            
            # Get card information
            card_output = await self.execute_command("show card")
            
            device_info = {
                'manufacturer': 'ZTE',
                'model': 'Unknown'
            }
            
            # Parse system information
            # Format: "System Description: C320 Version V2.1.0 Software..."
            model_match = re.search(r'System Description:\s+(\S+)', system_output)
            if model_match:
                device_info['model'] = model_match.group(1)
            
            # Parse system name
            name_match = re.search(r'System name:\s+(.+)', system_output)
            if name_match:
                device_info['hostname'] = name_match.group(1).strip()
            
            # Parse location
            location_match = re.search(r'Location:\s+(.+)', system_output)
            if location_match:
                device_info['location'] = location_match.group(1).strip()
            
            # Parse uptime
            uptime_match = re.search(r'Started before:\s+(.+)', system_output)
            if uptime_match:
                device_info['uptime'] = uptime_match.group(1).strip()
            
            # Parse running configuration version
            config_output = await self.execute_command("show running-config")
            version_match = re.search(r'config-version\s+([\d.]+)', config_output)
            if version_match:
                device_info['config_version'] = version_match.group(1)
            
            # Count boards from card output
            board_count = len(re.findall(r'^\s*\d+\s+\d+\s+\d+', card_output, re.MULTILINE))
            device_info['board_count'] = board_count
            
            return device_info
            
        except Exception as e:
            logger.error(f"Error getting device info from ZTE OLT: {str(e)}")
            return {
                'manufacturer': 'ZTE',
                'error': str(e)
            }
    
    async def provision_onu(self, onu_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provision ONU on ZTE OLT
        
        ZTE provisioning sequence:
        1. Navigate to PON interface (interface gpon-olt_1/1/1)
        2. Add ONU with serial number (onu X type ZTE sn ABCD12345678)
        3. Configure ONU interface (interface gpon-onu_1/1/1:X)
        4. Configure line/service profiles
        5. Set VLAN
        """
        try:
            slot = onu_config.get('slot', 1)
            port = onu_config.get('port', 1)
            ont_id = onu_config.get('ont_id')
            serial_no = onu_config.get('serial_no')
            line_profile = onu_config.get('line_profile_id', 1)
            service_profile = onu_config.get('service_profile_id', 1)
            vlan = onu_config.get('vlan')
            description = onu_config.get('description', '')
            onu_type = onu_config.get('onu_type', 'ZTE-F622')
            
            # Enter configuration mode
            await self.execute_command("configure terminal")
            
            # Enter interface mode
            interface_cmd = f"interface gpon-olt_1/{slot}/{port}"
            await self.execute_command(interface_cmd)
            
            # Register ONU with serial number
            register_cmd = f"onu {ont_id} type {onu_type} sn {serial_no}"
            output = await self.execute_command(register_cmd)
            
            # Check if ONU was added successfully
            if "Error" in output or "fail" in output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to add ONU: {output}',
                    'output': output,
                    'ont_id': None
                }
            
            # Exit interface mode
            await self.execute_command("exit")
            
            # Configure ONU interface
            onu_interface = f"interface gpon-onu_1/{slot}/{port}:{ont_id}"
            await self.execute_command(onu_interface)
            
            # Set name/description
            if description:
                safe_desc = description.replace('"', '').replace("'", "")[:64]
                await self.execute_command(f"name {safe_desc}")
            
            # Set service profiles
            await self.execute_command(f"tcont 1 profile {line_profile}")
            await self.execute_command(f"gemport 1 tcont 1")
            await self.execute_command(f"switchport mode hybrid vport 1")
                
            # Set VLAN
            if vlan:
                await self.execute_command(f"switchport vlan {vlan} tag vport 1")
            
            # Exit configuration mode
            await self.execute_command("exit")
            await self.execute_command("end")
            
            # Save configuration
            await self.execute_command("write")
            
            logger.info(f"ONU {serial_no} provisioned successfully on ZTE OLT with ONT ID {ont_id}")
            
            return {
                'status': 'success',
                'ont_id': ont_id,
                'message': f'ONU provisioned successfully with ID {ont_id}',
                'serial_no': serial_no,
                'vlan': vlan
            }
            
        except Exception as e:
            logger.error(f"Error provisioning ONU on ZTE OLT: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'ont_id': None
            }
    
    async def remove_onu(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Remove ONU from ZTE OLT"""
        try:
            slot = onu_location.get('slot', 1)
            port = onu_location.get('port', 1)
            ont_id = onu_location.get('ont_id')
            
            # Enter configuration mode
            await self.execute_command("configure terminal")
            
            # Enter interface mode
            interface_cmd = f"interface gpon-olt_1/{slot}/{port}"
            await self.execute_command(interface_cmd)
            
            # Remove ONU
            remove_cmd = f"no onu {ont_id}"
            output = await self.execute_command(remove_cmd)
            
            # Exit and save
            await self.execute_command("exit")
            await self.execute_command("end")
            await self.execute_command("write")
            
            if "Error" in output or "fail" in output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to remove ONU: {output}'
                }
            
            logger.info(f"ONU removed from ZTE OLT: slot {slot}, port {port}, ONT ID {ont_id}")
            return {
                'status': 'success',
                'message': 'ONU removed successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to remove ONU from ZTE: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def get_onts(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get list of ONTs/ONUs on the ZTE OLT
        
        Uses: show gpon onu state
        """
        try:
            # Get ONU states
            output = await self.execute_command("show gpon onu state")
            
            onts = self._parse_gpon_onu_state(output)
            
            # Apply filters if provided
            if filters:
                if 'port' in filters:
                    onts = [ont for ont in onts if ont.get('port') == filters['port']]
                if 'slot' in filters:
                    onts = [ont for ont in onts if ont.get('slot') == filters['slot']]
                if 'state' in filters:
                    onts = [ont for ont in onts if ont.get('phase_state') == filters['state']]
            
            return onts
            
        except Exception as e:
            logger.error(f"Failed to get ONTs from ZTE: {e}")
            return []
    
    def _parse_gpon_onu_state(self, output: str) -> List[Dict[str, Any]]:
        """Parse show gpon onu state output
        
        Format:
        OnuIndex   Admin State  OMCC State  Phase State  Channel
        1/1/1:1     enable       disable     OffLine      1(GPON)
        1/1/1:2     enable       disable     OffLine      1(GPON)
        
        Note: Format is rack/shelf/port:ont_id (not rack/shelf/slot/port)
        """
        onts = []
        lines = output.split('\n')
        
        for line in lines:
            # Match pattern: rack/shelf/port:ont_id  admin  omcc  phase  channel
            match = re.match(r'(\d+)/(\d+)/(\d+):(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)', line.strip())
            if match:
                rack, shelf, port, ont_id, admin, omcc, phase, channel = match.groups()
                
                onts.append({
                    'rack': int(rack),
                    'shelf': int(shelf),
                    'slot': int(shelf),  # Shelf is the slot in ZTE terminology
                    'port': int(port),
                    'ont_id': int(ont_id),
                    'onu_index': f"{rack}/{shelf}/{port}:{ont_id}",
                    'admin_state': admin,
                    'omcc_state': omcc,
                    'phase_state': phase,
                    'channel': channel.strip(),
                    'status': 'online' if phase.lower() == 'working' else 'offline'
                })
        
        return onts
    
    async def get_ont_status(self, ont_location: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed ONU status
        
        Uses: show gpon onu detail gpon-onu_1/1/1:X
        """
        try:
            slot = ont_location.get('slot', 1)
            port = ont_location.get('port', 1)
            ont_id = ont_location.get('ont_id')
            
            cmd = f"show gpon onu detail gpon-onu_1/{slot}/{port}:{ont_id}"
            output = await self.execute_command(cmd)
            
            status = self._parse_gpon_onu_detail(output)
            status['slot'] = slot
            status['port'] = port
            status['ont_id'] = ont_id
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get ONU status from ZTE: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _parse_gpon_onu_detail(self, output: str) -> Dict[str, Any]:
        """Parse show gpon onu detail output"""
        status = {}
        
        # Parse key-value pairs
        patterns = {
            'interface': r'ONU interface:\s+(.+)',
            'name': r'Name:\s+(.+)',
            'type': r'Type:\s+(.+)',
            'state': r'State:\s+(.+)',
            'admin_state': r'Admin state:\s+(.+)',
            'phase_state': r'Phase state:\s+(\S+)',
            'config_state': r'Config state:\s+(.+)',
            'authentication_mode': r'Authentication mode:\s+(.+)',
            'serial_number': r'Serial number:\s+(\S+)',
            'description': r'Description:\s+(.+)',
            'vport_mode': r'Vport mode:\s+(.+)',
            'dba_mode': r'DBA Mode:\s+(.+)',
            'current_channel': r'Current channel:\s+(.+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                status[key] = match.group(1).strip()
        
        # Determine online/offline status
        phase_state = status.get('phase_state', '').lower()
        status['online'] = phase_state not in ['offline', 'los']
        
        return status
    
    async def discover_onts(self, port: int, slot: int = 1) -> List[Dict[str, Any]]:
        """Discover unconfigured ONTs on a port
        
        Note: ZTE command 'show gpon onu uncfg' returns "No related information"
        when there are no unconfigured ONUs. This is normal behavior.
        """
        try:
            # Try to get unconfigured ONUs
            cmd = f"show gpon onu uncfg gpon-olt_1/{slot}/{port}"
            output = await self.execute_command(cmd)
            
            # Check if there are any unconfigured ONUs
            if "No related information" in output or len(output.strip()) < 50:
                logger.info(f"No unconfigured ONUs found on port {slot}/{port}")
                return []
            
            # Parse unconfigured ONUs
            onts = []
            lines = output.split('\n')
            
            for line in lines:
                # Parse line with SN
                if re.match(r'^\s*\d+', line):
                    parts = line.split()
                    if len(parts) >= 3:
                        onts.append({
                            'slot': slot,
                            'port': port,
                            'serial_number': parts[1] if len(parts) > 1 else '',
                            'status': 'unconfigured'
                        })
            
            return onts
            
        except Exception as e:
            logger.error(f"Failed to discover ONTs on ZTE: {e}")
            return []
    
    async def get_running_config(self) -> str:
        """Get running configuration"""
        try:
            return await self.execute_command("show running-config")
        except Exception as e:
            logger.error(f"Failed to get running config from ZTE: {e}")
            return ""
    
    async def get_startup_config(self) -> str:
        """Get startup configuration
        
        Note: ZTE uses 'show running-config' for both running and startup
        """
        try:
            return await self.execute_command("show running-config")
        except Exception as e:
            logger.error(f"Failed to get startup config from ZTE: {e}")
            return ""
    
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """Get interface information
        
        Note: Many ZTE interface commands return "Incomplete" or "Invalid" errors.
        Using show card to return board/slot interfaces.
        
        ZTE show card format:
        Rack Shelf Slot CfgType RealType Port  HardVer SoftVer         Status
        1    1     1    GTGH    GTGHK    16    V1.0.0  V2.1.0          INSERVICE
        """
        try:
            # Use show card to get board information
            output = await self.execute_command("show card")
            
            interfaces = []
            lines = output.split('\n')
            
            for line in lines:
                # Skip header and separator lines
                if 'Rack' in line or '---' in line or not line.strip():
                    continue
                
                # Match: Rack Shelf Slot CfgType RealType Port ...
                # More flexible pattern to handle varying whitespace
                parts = line.split()
                if len(parts) >= 6 and parts[0].isdigit():
                    try:
                        rack = int(parts[0])
                        shelf = int(parts[1])
                        slot = int(parts[2])
                        cfg_type = parts[3]
                        real_type = parts[4]
                        port_count = int(parts[5])
                        
                        # GTGH/GTGHK cards have GPON ports
                        if 'GTGH' in real_type:
                            # Create interface entry for each GPON port on the card
                            for p in range(1, port_count + 1):
                                interfaces.append({
                                    'name': f"gpon-olt_{rack}/{shelf}/{p}",
                                    'rack': rack,
                                    'shelf': shelf,
                                    'slot': slot,
                                    'port': p,
                                    'card_type': real_type,
                                    'card_slot': slot,
                                    'status': 'up',
                                    'type': 'GPON'
                                })
                        else:
                            # Other card types (PRAM, SMXA, etc.)
                            interfaces.append({
                                'name': f"{real_type}-{slot}",
                                'rack': rack,
                                'shelf': shelf,
                                'slot': slot,
                                'port': 0,
                                'card_type': real_type,
                                'card_slot': slot,
                                'status': 'up',
                                'type': 'Control/Management'
                            })
                    except (ValueError, IndexError):
                        continue
            
            return interfaces
            
        except Exception as e:
            logger.error(f"Failed to get interfaces from ZTE: {e}")
            return []
    
    async def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information
        
        Note: 'show memory' command returns "Invalid command" on ZTE C320.
        Returning basic info from system-group instead.
        """
        try:
            output = await self.execute_command("show system-group")
            
            memory_info = {
                'available': True,
                'note': 'ZTE C320 does not provide detailed memory stats via CLI'
            }
            
            # Try to extract system info
            info_match = re.search(r'System Info:\s+(.+)', output)
            if info_match:
                memory_info['system_info'] = info_match.group(1).strip()
            
            return memory_info
            
        except Exception as e:
            logger.error(f"Failed to get memory info from ZTE: {e}")
            return {'error': str(e)}
    
    async def get_system_logs(self, lines: int = 100) -> List[str]:
        """Get system logs
        
        Note: Log commands may vary by ZTE model. Returning empty list
        as log commands were not discovered in testing.
        """
        try:
            # Try common log commands
            for cmd in ["show log", "show alarm", "show alarm active"]:
                output = await self.execute_command(cmd)
                if "Error" not in output and "Invalid" not in output:
                    log_lines = [l.strip() for l in output.split('\n') if l.strip()]
                    return log_lines[:lines]
            
            logger.warning("No working log commands found on ZTE OLT")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get system logs from ZTE: {e}")
            return []
    
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get VLAN list
        
        Note: 'show vlan' and 'show vlan all' return "Incomplete" or "Invalid" errors.
        Parse VLANs from running configuration instead.
        """
        try:
            config = await self.execute_command("show running-config")
            
            vlans = []
            
            # Parse VLAN configurations from config
            # Look for patterns like "vlan 100" or "switchport vlan 200"
            vlan_ids = set()
            
            for match in re.finditer(r'\bvlan\s+(\d+)', config):
                vlan_ids.add(int(match.group(1)))
            
            for vlan_id in sorted(vlan_ids):
                vlans.append({
                    'vlan_id': vlan_id,
                    'name': f'VLAN{vlan_id}',
                    'status': 'active'
                })
            
            return vlans
            
        except Exception as e:
            logger.error(f"Failed to get VLANs from ZTE: {e}")
            return []
    
    async def get_boards(self) -> List[Dict[str, Any]]:
        """Get board/card information
        
        Uses: show card
        
        Format:
        Rack Shelf Slot CfgType RealType Port  HardVer SoftVer         Status
        1    1     1    GTGH    GTGHK    16    V1.0.0  V2.1.0          INSERVICE
        """
        try:
            output = await self.execute_command("show card")
            
            boards = []
            lines = output.split('\n')
            
            for line in lines:
                # Skip header and separator lines
                if 'Rack' in line or '---' in line or not line.strip():
                    continue
                
                # Split by whitespace and parse
                parts = line.split()
                if len(parts) >= 9 and parts[0].isdigit():
                    try:
                        boards.append({
                            'rack': int(parts[0]),
                            'shelf': int(parts[1]),
                            'slot': int(parts[2]),
                            'configured_type': parts[3],
                            'real_type': parts[4],
                            'port_count': int(parts[5]),
                            'hardware_version': parts[6],
                            'software_version': parts[7],
                            'status': parts[8],
                            'name': f"{parts[4]} (Slot {parts[2]})"
                        })
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Skipping line in board parse: {line} - {e}")
                        continue
            
            return boards
            
        except Exception as e:
            logger.error(f"Failed to get boards from ZTE: {e}")
            return []
    
    async def reboot_ont(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """Reboot ONU"""
        try:
            board = onu_location.get('board', 1)
            slot = onu_location.get('slot', 1)
            port = onu_location.get('port', 1)
            ont_id = onu_location.get('ont_id')
            
            # ZTE reboot command
            cmd = f"pon-onu-mng gpon-onu_{board}/{slot}/{port}:{ont_id}"
            commands = [
                "configure terminal",
                cmd,
                "reboot",
                "yes",
                "exit",
                "exit"
            ]
            reboot_output = ""
            for cmd in commands:
                output = await self.execute_command(cmd)
                reboot_output += f"\n> {cmd}\n{output.strip()}\n"
            
            logger.info(f"Reboot Output {reboot_output}")
            if "Error" in reboot_output or "Invalid" in reboot_output or "Failed" in reboot_output or "not exist" in reboot_output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to reboot ONU: {reboot_output}'
                }
            
            logger.info(f"Rebooted ONU {ont_id} on ZTE OLT")
            return {
                'status': 'success',
                'message': 'ONU rebooted successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to reboot ONU on ZTE: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def get_ont_path_by_serial(self, sn: str) -> Dict[str, Any]:
        """Get ONU information by serial number"""
        try:
            # ZTE command to show ONU information
            cmd = f"show gpon onu by sn {sn}"
            output = await self.execute_command(cmd)
            
            logger.info(f"Find ONU Output {output}")
            if "Error" in output or "no entries found" in output.lower():
                return {
                    'status': 'error',
                    'message': f'Failed to find ONU: {output}'
                }
            
            logger.info(f"Found ONU {sn} on ZTE OLT")
            result = self._parse_ont_path(output)
            if not result:
                return {
                    "status": "error",
                    "message": "ONU not found"
                }

            return {
                "status": "success",
                "data": result
            }
            
        except Exception as e:
            logger.error(f"Failed to find ONU on ZTE: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _parse_ont_path(self, output: str) -> Dict[str, Any] | None:
        """
        Parse 'show pon onu by sn' output from ZTE OLT.
        
        Example output:
        Search result
        -----------------
        gpon-olt_1/1/1:102
        
        Format: gpon-olt_board/card/port:ont_id
        """
        for line in output.splitlines():
            line = line.strip()

            if (
                not line
                or "Search" in line
                or "---" in line
            ):
                continue
            
            if line.startswith("gpon-olt_"):
                match = re.search(
                    r"gpon-olt_(\d+)/(\d+)/(\d+):(\d+)",
                    line
                )

                if match:
                    board, slot, port, ont_id = match.groups()

                    return {
                        "interface": line,
                        "board": int(board),
                        "slot": int(slot),
                        "port": int(port),
                        "ont_id": int(ont_id)
                    }
        
        return None
    
    async def get_unconfigured_onts(self) -> List[Dict[str, Any]]:
        """
        Get list of unconfigured ONUs on ZTE OLT.
        
        Returns list of ONUs that are detected but not yet configured.
        Uses 'show pon onu uncfg' command.
        
        Returns:
            List of dicts with keys: olt_index, model, serial_number, password
        """
        try:
            output = await self.execute_command("show pon onu uncfg")
            
            uncfg_onts = self._parse_unconfigured_onts(output)
            
            logger.info(f"Found {len(uncfg_onts)} unconfigured ONUs on ZTE OLT")
            return uncfg_onts
            
        except Exception as e:
            logger.error(f"Failed to get unconfigured ONUs from ZTE: {e}")
            return []
    
    def _parse_unconfigured_onts(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'show pon onu uncfg' output from ZTE OLT.
        
        Example output:
        OltIndex            Model                SN                 PW
        -------------------------------------------------------------------------
        gpon-olt_1/1/2      MH80                 MHAR08DF4BD9       N/A
        gpon-olt_1/1/2      F612WV6.0            RLGMFE1CB160       0123456789
        
        Format: gpon-olt_rack/shelf/port
        """
        uncfg_onts = []
        lines = output.split('\n')
        
        for line in lines:
            # Skip header and separator lines
            if 'OltIndex' in line or '---' in line or not line.strip():
                continue
            
            # Match pattern: gpon-olt_rack/shelf/port  model  serial  password
            # Use flexible whitespace matching since columns are space-separated
            parts = line.split()
            
            if len(parts) >= 4 and parts[0].startswith('gpon-olt_'):
                olt_index = parts[0]
                model = parts[1]
                serial_number = parts[2]
                password = parts[3] if len(parts) > 3 else 'N/A'
                
                # Parse rack/shelf/port from gpon-olt_1/1/2 format
                olt_match = re.match(r'gpon-olt_(\d+)/(\d+)/(\d+)', olt_index)
                if olt_match:
                    rack, shelf, port = olt_match.groups()
                    
                    uncfg_onts.append({
                        'olt_index': olt_index,
                        'rack': int(rack),
                        'shelf': int(shelf),
                        'slot': int(shelf),  # ZTE uses shelf as slot
                        'port': int(port),
                        'model': model,
                        'serial_number': serial_number,
                        'password': password if password != 'N/A' else None
                    })
        
        return uncfg_onts
    
    async def create_tcont_profile(self, profile_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create T-CONT (Traffic Container) profile on ZTE OLT.
        
        T-CONT profiles define bandwidth allocation for ONUs.
        
        Note: ZTE OLT only supports the 'maximum' bandwidth parameter.
        The 'assured_bandwidth' and 'fixed_bandwidth' parameters are ignored.
        
        Args:
            profile_config: Dict containing:
                - profile_name: Profile name (e.g., '10M')
                - profile_type: 1-5 (1=Fixed, 2=Assured, 3=Non-Assured, 4=Best-Effort, 5=Mixed)
                - maximum_bandwidth: Max bandwidth in bytes
                - assured_bandwidth: (ignored - not supported by ZTE)
                - fixed_bandwidth: (ignored - not supported by ZTE)
        
        Returns:
            Dict with status, profile_name, message, command_output
        """
        try:
            profile_name = profile_config['profile_name']
            profile_type = profile_config['profile_type']
            max_bw = profile_config['maximum_bandwidth']
            
            # Enter config mode
            await self.execute_command("configure terminal")
            await self.execute_command("gpon")
            
            # Build T-CONT profile command
            # Format: profile tcont <name> type <type> maximum <bytes>
            # Note: ZTE only supports maximum bandwidth, not assured or fixed
            cmd = f"profile tcont {profile_name} type {profile_type} maximum {max_bw}"
            
            output = await self.execute_command(cmd)
            
            # Exit config mode
            await self.execute_command("exit")
            await self.execute_command("exit")
            
            # Check for errors
            if "Error" in output or "Invalid" in output or "Failed" in output:
                return {
                    'status': 'error',
                    'profile_name': profile_name,
                    'profile_type': profile_type,
                    'maximum_bandwidth': max_bw,
                    'message': f'Failed to create T-CONT profile: {output}',
                    'command_output': output
                }
            
            logger.info(f"Created T-CONT profile '{profile_name}' on ZTE OLT")
            return {
                'status': 'success',
                'profile_name': profile_name,
                'profile_type': profile_type,
                'maximum_bandwidth': max_bw,
                'message': f'T-CONT profile {profile_name} created successfully',
                'command_output': output
            }
            
        except Exception as e:
            logger.error(f"Failed to create T-CONT profile on ZTE: {e}")
            return {
                'status': 'error',
                'profile_name': profile_config.get('profile_name', 'unknown'),
                'profile_type': profile_config.get('profile_type', 0),
                'maximum_bandwidth': profile_config.get('maximum_bandwidth', 0),
                'message': str(e),
                'command_output': None
            }
    
    async def create_vlan_profile(self, profile_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create VLAN profile on ZTE OLT.
        
        VLAN profiles define VLAN tagging behavior for ONUs.
        
        Note: ZTE OLT only supports basic VLAN profile parameters.
        The 'svlan' and 'priority' parameters are ignored.
        
        Args:
            profile_config: Dict containing:
                - profile_name: Profile name (e.g., 'vlan100')
                - tag_mode: 'tag', 'untag', or 'translate' (defaults to 'tag')
                - cvlan: Customer VLAN ID (1-4094)
                - svlan: (ignored - not supported by ZTE)
                - priority: (ignored - not supported by ZTE)
        
        Returns:
            Dict with status, profile_name, message, command_output
        """
        try:
            profile_name = profile_config['profile_name']
            tag_mode = profile_config.get('tag_mode', 'tag')  # Default to 'tag'
            cvlan = profile_config['cvlan']
            
            # Enter config mode
            await self.execute_command("configure terminal")
            await self.execute_command("gpon")
            
            # Build VLAN profile command
            # Format: onu profile vlan <name> tag-mode <mode> cvlan <vlan>
            # Note: ZTE only supports name, tag-mode, and cvlan
            cmd = f"onu profile vlan {profile_name} tag-mode {tag_mode} cvlan {cvlan}"
            
            output = await self.execute_command(cmd)
            
            # Exit config mode
            await self.execute_command("exit")
            await self.execute_command("exit")
            
            # Check for errors
            if "Error" in output or "Invalid" in output or "Failed" in output:
                return {
                    'status': 'error',
                    'profile_name': profile_name,
                    'tag_mode': tag_mode,
                    'cvlan': cvlan,
                    'message': f'Failed to create VLAN profile: {output}',
                    'command_output': output
                }
            
            logger.info(f"Created VLAN profile '{profile_name}' on ZTE OLT")
            return {
                'status': 'success',
                'profile_name': profile_name,
                'tag_mode': tag_mode,
                'cvlan': cvlan,
                'message': f'VLAN profile {profile_name} created successfully',
                'command_output': output
            }
            
        except Exception as e:
            logger.error(f"Failed to create VLAN profile on ZTE: {e}")
            return {
                'status': 'error',
                'profile_name': profile_config.get('profile_name', 'unknown'),
                'tag_mode': profile_config.get('tag_mode', 'unknown'),
                'cvlan': profile_config.get('cvlan', 0),
                'message': str(e),
                'command_output': None
            }
    
    async def get_tcont_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of T-CONT profiles configured on ZTE OLT.
        
        Uses: show run | include profile tcont
        
        Returns:
            List of T-CONT profile dictionaries
        """
        try:
            output = await self.execute_command("show run | include profile tcont")
            profiles = self._parse_tcont_profiles(output)
            return profiles
        except Exception as e:
            logger.error(f"Failed to get T-CONT profiles from ZTE: {e}")
            return []
    
    async def get_vlan_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of VLAN profiles configured on ZTE OLT.
        
        Uses: show run | include onu profile vlan
        
        Returns:
            List of VLAN profile dictionaries
        """
        try:
            output = await self.execute_command("show run | include onu profile vlan")
            profiles = self._parse_vlan_profiles(output)
            return profiles
        except Exception as e:
            logger.error(f"Failed to get VLAN profiles from ZTE: {e}")
            return []
    
    def _parse_tcont_profiles(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'show run | include profile tcont' output.
        
        Example output:
          profile tcont 10M type 4 maximum 102400
          profile tcont 50M type 4 maximum 6250000
        """
        profiles = []
        lines = output.split('\n')
        
        for line in lines:
            # Match: profile tcont <name> type <type> maximum <bandwidth>
            match = re.match(r'\s*profile\s+tcont\s+(\S+)\s+type\s+(\d+)\s+maximum\s+(\d+)', line.strip())
            if match:
                profile_name, profile_type, max_bw = match.groups()
                profiles.append({
                    'profile_name': profile_name,
                    'profile_type': int(profile_type),
                    'maximum_bandwidth': int(max_bw)
                })
        
        return profiles
    
    def _parse_vlan_profiles(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'show run | include onu profile vlan' output.
        
        Example output:
          onu profile vlan vlan100 tag-mode tag cvlan 100
          onu profile vlan vlan200 tag-mode tag cvlan 200
        """
        profiles = []
        lines = output.split('\n')
        
        for line in lines:
            # Example: Profile: 10M, Type: 4, Maximum: 102400
            if 'Profile:' in line or 'profile' in line.lower():
                # This is a simplified parser - adjust based on actual ZTE output
                match = re.search(r'(\S+).*type[:\s]+(\d+).*maximum[:\s]+(\d+)', line, re.IGNORECASE)
                if match:
                    profiles.append({
                        'profile_name': match.group(1),
                        'profile_type': int(match.group(2)),
                        'maximum_bandwidth': int(match.group(3))
                    })
        
        return profiles
    
    def _parse_vlan_profiles(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'show run | include onu profile vlan' output.
        
        Example output:
          onu profile vlan vlan100 tag-mode tag cvlan 100
          onu profile vlan vlan200 tag-mode tag cvlan 200
        """
        profiles = []
        lines = output.split('\n')
        
        for line in lines:
            # Match: onu profile vlan <name> tag-mode <mode> cvlan <vlan>
            match = re.match(r'\s*onu\s+profile\s+vlan\s+(\S+)\s+tag-mode\s+(\S+)\s+cvlan\s+(\d+)', line.strip())
            if match:
                profile_name, tag_mode, cvlan = match.groups()
                profiles.append({
                    'profile_name': profile_name,
                    'tag_mode': tag_mode,
                    'cvlan': int(cvlan)
                })
        
        return profiles

    
    async def delete_tcont_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Delete T-CONT profile from ZTE OLT.
        
        Args:
            profile_name: Name of the T-CONT profile to delete
        
        Returns:
            Dict with status and message
        """
        try:
            # Enter config mode
            await self.execute_command("configure terminal")
            await self.execute_command("gpon")
            
            # Delete T-CONT profile
            # Format: no profile tcont <name>
            cmd = f"no profile tcont {profile_name}"
            output = await self.execute_command(cmd)
            
            # Exit config mode
            await self.execute_command("exit")
            await self.execute_command("exit")
            
            # Check for errors
            if "Error" in output or "Invalid" in output or "Failed" in output or "not exist" in output.lower():
                return {
                    'status': 'error',
                    'profile_name': profile_name,
                    'message': f'Failed to delete T-CONT profile: {output}',
                    'command_output': output
                }
            
            logger.info(f"Deleted T-CONT profile '{profile_name}' from ZTE OLT")
            return {
                'status': 'success',
                'profile_name': profile_name,
                'message': f'T-CONT profile {profile_name} deleted successfully',
                'command_output': output
            }
            
        except Exception as e:
            logger.error(f"Failed to delete T-CONT profile from ZTE: {e}")
            return {
                'status': 'error',
                'profile_name': profile_name,
                'message': str(e),
                'command_output': None
            }
    
    async def delete_vlan_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Delete VLAN profile from ZTE OLT.
        
        Args:
            profile_name: Name of the VLAN profile to delete
        
        Returns:
            Dict with status and message
        """
        try:
            # Enter config mode
            await self.execute_command("configure terminal")
            await self.execute_command("gpon")
            
            # Delete VLAN profile
            # Format: no onu profile vlan <name>
            cmd = f"no onu profile vlan {profile_name}"
            output = await self.execute_command(cmd)
            
            # Exit config mode
            await self.execute_command("exit")
            await self.execute_command("exit")
            
            # Check for errors
            if "Error" in output or "Invalid" in output or "Failed" in output or "not exist" in output.lower():
                return {
                    'status': 'error',
                    'profile_name': profile_name,
                    'message': f'Failed to delete VLAN profile: {output}',
                    'command_output': output
                }
            
            logger.info(f"Deleted VLAN profile '{profile_name}' from ZTE OLT")
            return {
                'status': 'success',
                'profile_name': profile_name,
                'message': f'VLAN profile {profile_name} deleted successfully',
                'command_output': output
            }
            
        except Exception as e:
            logger.error(f"Failed to delete VLAN profile from ZTE: {e}")
            return {
                'status': 'error',
                'profile_name': profile_name,
                'message': str(e),
                'command_output': None
            }
    
    async def get_next_onu_id(self, board: int, card: int, port: int) -> int:
        """
        Get the next available ONU ID for a specific port.
        
        Args:
            board: Board number
            card: Card number
            port: Port number
        
        Returns:
            int: Next available ONU ID (starts from 1)
        """
        try:
            interface = f"gpon-olt_{board}/{card}/{port}"
            output = await self.execute_command(f"show pon onu information {interface}")
            
            # Parse to find highest ONU ID
            # Example line: 1/1/1:1     SN(MHAR080384D N/A    SN(MHAR080384D9)   OffLine            0
            max_id = 0
            for line in output.split('\n'):
                # Look for lines with ONU information (format: X/X/X:ID)
                match = re.search(rf'{board}/{card}/{port}:(\d+)', line)
                if match:
                    onu_id = int(match.group(1))
                    if onu_id > max_id:
                        max_id = onu_id
            
            next_id = max_id + 1
            logger.info(f"Next available ONU ID for {interface}: {next_id}")
            return next_id
            
        except Exception as e:
            logger.error(f"Failed to get next ONU ID from ZTE: {e}")
            # Default to 1 if we can't determine
            return 1
    
    async def find_unconfigured_onu_by_serial(self, serial_number: str) -> Optional[Dict[str, Any]]:
        """
        Find an unconfigured ONU by its serial number.
        
        Args:
            serial_number: ONU serial number to search for
        
        Returns:
            Dict with board, card, port, model if found, None otherwise
            
        Example output parsing:
            OltIndex            Model                SN                 PW
            -------------------------------------------------------------------------
            gpon-olt_1/1/2      MH80                 MHAR08DF4BD9       N/A
        """
        try:
            output = await self.execute_command("show pon onu uncfg")
            
            # Parse the output to find the serial number
            for line in output.split('\n'):
                # Skip header and separator lines
                if 'OltIndex' in line or '---' in line or not line.strip():
                    continue
                
                # Parse line format: gpon-olt_1/1/2      MH80                 MHAR08DF4BD9       N/A
                parts = line.split()
                if len(parts) >= 3:
                    olt_index = parts[0]  # gpon-olt_1/1/2
                    model = parts[1]      # MH80
                    sn = parts[2]         # MHAR08DF4BD9
                    
                    # Check if this is the serial number we're looking for
                    if sn.upper() == serial_number.upper():
                        # Parse OltIndex: gpon-olt_X/X/X
                        match = re.search(r'gpon-olt_(\d+)/(\d+)/(\d+)', olt_index)
                        if match:
                            board = int(match.group(1))
                            card = int(match.group(2))
                            port = int(match.group(3))
                            
                            logger.info(f"Found unconfigured ONU {serial_number} on {olt_index}, model: {model}")
                            return {
                                'board': board,
                                'card': card,
                                'port': port,
                                'model': model,
                                'serial_number': sn,
                                'olt_index': olt_index
                            }
            
            logger.warning(f"Unconfigured ONU with serial number {serial_number} not found")
            return None
            
        except Exception as e:
            logger.error(f"Failed to find unconfigured ONU from ZTE: {e}")
            return None
    
    async def register_onu(self, registration_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register and configure an ONU on the OLT.
        
        This performs a complete 4-step registration process:
        1. Enter the OLT interface and register the ONU with its serial number
        2. Configure the ONU interface (name, description, tcont, gemport, service-port)
        3. Configure the pon-onu-mng settings (service, switchport, ip-host, vlan port)
        4. Return complete registration status
        
        Args:
            registration_data: Dict containing:
                - pppoe_user: Username of the PPPoe User
                - pppoe_pass: key of the PPPoe User
                - onu_serial_number: Serial number of the ONU (will be looked up in unconfigured list)
                - onu_type: ONU type (default: ZTE-F622)
                - name: ONU name
                - description: ONU description
                - tcont_profile: T-CONT profile name
                - gemport: GEM port number
                - tcont: T-CONT number
                - service_port: Service port number
                - vport: Virtual port number
                - user_vlan: User VLAN ID
                - vlan: VLAN ID
                - switchport_bind: Switch port binding
                - iphost: IP host number
                - dhcp_enable: Enable DHCP
                - ping_response: Enable ping response
                - traceroute_response: Enable traceroute response
                - vlan_port: VLAN port identifier
                - mode: VLAN mode (tag/untag)
        
        Returns:
            Dict with status, message, onu_id, interface, and command_outputs
        """
        try:
            serial_number = registration_data['onu_serial_number']
            onu_type = registration_data.get('onu_type', 'ZTE-F622')
            
            # Step 0: Find the unconfigured ONU to get board/card/port
            logger.info(f"Looking up unconfigured ONU with serial number {serial_number}")
            onu_info = await self.find_unconfigured_onu_by_serial(serial_number)
            
            if not onu_info:
                return {
                    'status': 'error',
                    'message': f'Unconfigured ONU with serial number {serial_number} not found. Please verify the ONU is connected and unconfigured.',
                    'onu_id': None,
                    'interface': None,
                    'serial_number': serial_number,
                    'command_outputs': {}
                }
            
            board = onu_info['board']
            card = onu_info['card']
            port = onu_info['port']
            
            logger.info(f"Found ONU at {onu_info['olt_index']}, model: {onu_info['model']}")
            
            # Get next available ONU ID
            onu_id = await self.get_next_onu_id(board, card, port)
            
            olt_interface = f"gpon-olt_{board}/{card}/{port}"
            onu_interface = f"gpon-onu_{board}/{card}/{port}:{onu_id}"
            
            command_outputs = {}
            
            # Step 1: Register ONU on the OLT interface
            logger.info(f"Step 1: Registering ONU {serial_number} on {olt_interface}")
            commands = [
                "configure terminal",
                f"interface {olt_interface}",
                f"onu {onu_id} type {onu_type} sn {serial_number}",
                "exit",
                "exit"
            ]
            
            step1_output = ""
            for cmd in commands:
                output = await self.execute_command(cmd)
                step1_output += f"{cmd}\n{output}\n"
            
            command_outputs['step1_register'] = step1_output
            
            # Step 2: Configure ONU interface settings
            logger.info(f"Step 2: Configuring ONU interface {onu_interface}")
            gemport = registration_data.get('gemport', 1)
            tcont = registration_data.get('tcont', 1)
            service_port = registration_data.get('service_port', 1)
            vport = registration_data.get('vport', 1)
            user_vlan = registration_data['user_vlan']
            vlan = registration_data['vlan']
            
            commands = [
                "configure terminal",
                f"interface {onu_interface}",
                f"name {registration_data['name']}",
                f"description {registration_data['description']}",
                f"tcont {tcont} profile {registration_data['tcont_profile']}",
                f"gemport {gemport} tcont {tcont}",
                f"service-port {service_port} vport {vport} user-vlan {user_vlan} vlan {vlan}",
                # Additional MGMT VLAN configuration (TCONT 2, gemport 2, service-port 2)
                "tcont 2 profile MGMT",
                "gemport 2 tcont 2",
                "service-port 2 vport 2 user-vlan 200 vlan 200",
                "exit",
                "exit"
            ]
            
            step2_output = ""
            for cmd in commands:
                output = await self.execute_command(cmd)
                step2_output += f"{cmd}\n{output}\n"
            
            command_outputs['step2_configure'] = step2_output
            
            # Step 3: Configure pon-onu-mng settings
            logger.info(f"Step 3: Configuring pon-onu-mng for {onu_interface}")
            switchport_bind = registration_data.get('switchport_bind', 'switch_0/1')
            iphost = registration_data.get('iphost', 1)
            dhcp_enable = "enable" if registration_data.get('dhcp_enable', True) else "disable"
            ping_response = "enable" if registration_data.get('ping_response', True) else "disable"
            traceroute_response = "enable" if registration_data.get('traceroute_response', True) else "disable"
            vlan_port = registration_data.get('vlan_port', 'eth_0/1')
            mode = registration_data.get('mode', 'tag')
            user = registration_data.get('pppoe_user', 'AP0LL0')
            userkey = registration_data.get('pppoe_pass', 'AP0LL02K26')
            
            commands = [
                "configure terminal",
                f"pon-onu-mng {onu_interface}",
                f"service {service_port} gemport {gemport} vlan {vlan}",
                f"switchport-bind {switchport_bind} iphost {iphost}",
                f"ip-host {iphost} dhcp-enable {dhcp_enable} ping-response {ping_response} traceroute-response {traceroute_response}",
                f"vlan port {vlan_port} mode {mode} vlan {vlan}",
                # Additional MGMT VLAN configuration
                "service 2 gemport 2 vlan 200",
                "switchport-bind switch_0/2 iphost 2",
                "ip-host 2 dhcp-enable enable ping-response enable traceroute-response enable",
                "vlan port eth_0/2 mode tag vlan 200",
                f"wan-ip 2 mode pppoe username {user} password {userkey} service-name {settings.ACS_SERVICE_NAME} vlan-profile vlan100 host 1",
                f"tr069-mgmt 1 state unlock acs {settings.ACS_URL} validate basic username onu password onu tag pri 2 vlan 200",
                "wan-ip 1 mode dhcp vlan-profile vlan200 host 2",
                "exit",
                "exit",
                "exit",
                "write",
            ]
            
            step3_output = ""
            for cmd in commands:
                output = await self.execute_command(cmd)
                step3_output += f"{cmd}\n{output}\n"
            
            command_outputs['step3_pon_onu_mng'] = step3_output
            
            logger.info(f"Successfully registered ONU {serial_number} as {onu_interface}")
            
            return {
                'status': 'success',
                'message': f'ONU successfully registered and configured as {onu_interface}',
                'onu_id': onu_id,
                'interface': onu_interface,
                'serial_number': serial_number,
                'command_outputs': command_outputs
            }
            
        except Exception as e:
            logger.error(f"Failed to register ONU on ZTE: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'onu_id': None,
                'interface': None,
                'serial_number': registration_data.get('onu_serial_number'),
                'command_outputs': command_outputs if 'command_outputs' in locals() else {}
            }
    
    async def get_offline_onus(self, board: int, card: int, port: int, state: str = "offline") -> List[int]:
        """
        Get list of ONU IDs matching a specific state on a port.
        
        Args:
            board: Board number
            card: Card number
            port: Port number
            state: ONU state to filter (case-insensitive, e.g., 'offline', 'LOS', 'DyingGasp')
        
        Returns:
            List of ONU IDs matching the specified state
            
        Example output parsing:
                    MAC            LLID                                         Offline
        ONU         SN report      ONU ID Auth configuration State              times
        -------------------------------------------------------------------------------
        1/1/1:1     SN(MHAR080384D N/A    SN(MHAR080384D9)   OffLine            0
                    9)
        1/1/1:2     SN(MHAR083C98D N/A    SN(MHAR083C98D9)   LOS                0
                    9)
        """
        try:
            interface = f"gpon-olt_{board}/{card}/{port}"
            output = await self.execute_command(f"show pon onu information {interface}")
            
            matching_onu_ids = []
            
            for line in output.split('\n'):
                # Skip header and separator lines
                if 'ONU' in line and 'SN report' in line:
                    continue
                if '---' in line or not line.strip():
                    continue
                
                # Look for lines with ONU information and the specified state (case-insensitive)
                # Format: 1/1/1:1     SN(MHAR080384D N/A    SN(MHAR080384D9)   OffLine            0
                if state.lower() in line.lower():
                    # Parse ONU ID from format X/X/X:ID
                    match = re.search(rf'{board}/{card}/{port}:(\d+)', line)
                    if match:
                        onu_id = int(match.group(1))
                        matching_onu_ids.append(onu_id)
                        logger.debug(f"Found ONU ID {onu_id} with state '{state}' on {interface}")
            
            logger.info(f"Found {len(matching_onu_ids)} ONU(s) with state '{state}' on {interface}: {matching_onu_ids}")
            return matching_onu_ids
            
        except Exception as e:
            logger.error(f"Failed to get ONUs with state '{state}' from ZTE: {e}")
            return []
    
    async def unregister_offline_onus(self, port_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unregister ONUs matching a specific state from a port.
        
        This performs:
        1. Gets list of ONUs matching the specified state on the port
        2. Enters the OLT interface configuration
        3. Executes 'no onu X' for each matching ONU
        
        Args:
            port_config: Dict containing:
                - board: Board number
                - card: Card number
                - port: Port number
                - state: ONU state to filter (default: 'offline')
        
        Returns:
            Dict with status, message, offline_onus_found, onus_unregistered, command_outputs
        """
        try:
            board = port_config.get('board', 1)
            card = port_config.get('card', 1)
            port = port_config['port']
            state = port_config.get('state', 'offline')
            
            interface = f"gpon-olt_{board}/{card}/{port}"
            
            # Step 1: Get list of ONUs matching the specified state
            logger.info(f"Checking for ONUs with state '{state}' on {interface}")
            matching_onu_ids = await self.get_offline_onus(board, card, port, state)
            
            if not matching_onu_ids:
                logger.info(f"No ONUs with state '{state}' found on {interface}")
                return {
                    'status': 'success',
                    'message': f'No ONUs with state \'{state}\' found on {interface}',
                    'interface': interface,
                    'offline_onus_found': 0,
                    'onus_unregistered': [],
                    'command_outputs': {}
                }
            
            # Step 2: Unregister each matching ONU
            logger.info(f"Unregistering {len(matching_onu_ids)} ONU(s) with state '{state}' from {interface}")
            command_outputs = {}
            
            commands = ["configure terminal", f"interface {interface}"]
            
            # Add 'no onu X' commands for each matching ONU
            for onu_id in matching_onu_ids:
                commands.append(f"no onu {onu_id}")
            
            commands.extend(["exit", "exit"])
            
            # Execute all commands
            unregister_output = ""
            for cmd in commands:
                output = await self.execute_command(cmd)
                unregister_output += f"{cmd}\n{output}\n"
            
            command_outputs['unregister'] = unregister_output
            
            logger.info(f"Successfully unregistered {len(matching_onu_ids)} ONU(s) with state '{state}' from {interface}")
            
            return {
                'status': 'success',
                'message': f'Successfully unregistered {len(matching_onu_ids)} ONU(s) with state \'{state}\' from {interface}',
                'interface': interface,
                'offline_onus_found': len(matching_onu_ids),
                'onus_unregistered': matching_onu_ids,
                'command_outputs': command_outputs
            }
            
        except Exception as e:
            logger.error(f"Failed to unregister offline ONUs from ZTE: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'interface': f"gpon-olt_{port_config.get('board', 1)}/{port_config.get('card', 1)}/{port_config.get('port', 0)}",
                'offline_onus_found': 0,
                'onus_unregistered': [],
                'command_outputs': {}
            }
    
    async def get_port_info(self, port_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed information about an OLT PON port.
        
        Args:
            port_config: Dict containing:
                - board: Board number (default: 1)
                - card: Card number (default: 1)
                - port: Port number
        
        Returns:
            Dict with port status, ONU counts, and statistics
        """
        try:
            board = port_config.get('board', 1)
            card = port_config.get('card', 1)
            port = port_config['port']
            
            # Build interface name: gpon-olt_board/card/port
            interface = f"gpon-olt_{board}/{card}/{port}"
            
            # Get port information
            output = await self.execute_command(f"show interface {interface}")
            
            # Parse the output
            port_info = self._parse_port_info(output, board, card, port)
            
            logger.info(f"Retrieved port info for {interface}")
            return port_info
            
        except Exception as e:
            logger.error(f"Failed to get port info from ZTE: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'interface': f"gpon-olt_{port_config.get('board', 1)}/{port_config.get('card', 1)}/{port_config.get('port', 0)}"
            }
    
    def _parse_port_info(self, output: str, board: int, card: int, port: int) -> Dict[str, Any]:
        """
        Parse 'show interface gpon-olt_X/X/X' output.
        
        Example output:
        gpon-olt_1/1/2 is activate,line protocol is up.
          The port has 128 onus, the number of registered onus is 0.
        Current channel num : 1
        OLT statistic:
           Input rate :                223 Bps                3 pps
           Output rate:                  0 Bps                0 pps
        """
        port_info = {
            'board': board,
            'card': card,
            'port': port,
            'interface': f"gpon-olt_{board}/{card}/{port}",
            'status': 'unknown',
            'line_protocol': 'unknown',
            'description': None,
            'total_onus': 0,
            'registered_onus': 0,
            'channel_num': 0,
            'statistics': {
                'input_rate_bps': 0,
                'input_rate_pps': 0,
                'output_rate_bps': 0,
                'output_rate_pps': 0,
                'input_bandwidth_percent': 0.0,
                'output_bandwidth_percent': 0.0,
                'input_packets': 0,
                'input_bytes': 0,
                'input_drops': 0,
                'output_packets': 0,
                'output_bytes': 0,
                'input_unicast': 0,
                'input_multicast': 0,
                'input_broadcast': 0,
                'crc_errors': 0
            }
        }
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Parse status line: "gpon-olt_1/1/2 is activate,line protocol is up."
            if 'is activate' in line or 'is deactivate' in line:
                if 'is activate' in line:
                    port_info['status'] = 'activate'
                else:
                    port_info['status'] = 'deactivate'
                    
                if 'line protocol is up' in line:
                    port_info['line_protocol'] = 'up'
                elif 'line protocol is down' in line:
                    port_info['line_protocol'] = 'down'
            
            # Parse description
            if 'Description is' in line:
                match = re.search(r'Description is (.+)\.', line)
                if match and match.group(1) != 'none':
                    port_info['description'] = match.group(1)
            
            # Parse ONU counts: "The port has 128 onus, the number of registered onus is 0."
            if 'has' in line and 'onus' in line and 'registered' in line:
                match = re.search(r'has (\d+) onus.*registered onus is (\d+)', line)
                if match:
                    port_info['total_onus'] = int(match.group(1))
                    port_info['registered_onus'] = int(match.group(2))
            
            # Parse channel number
            if 'Current channel num' in line:
                match = re.search(r'Current channel num\s*:\s*(\d+)', line)
                if match:
                    port_info['channel_num'] = int(match.group(1))
            
            # Parse input rate
            if 'Input rate' in line:
                match = re.search(r'Input rate\s*:\s*(\d+) Bps\s+(\d+) pps', line)
                if match:
                    port_info['statistics']['input_rate_bps'] = int(match.group(1))
                    port_info['statistics']['input_rate_pps'] = int(match.group(2))
            
            # Parse output rate
            if 'Output rate' in line:
                match = re.search(r'Output rate:\s*(\d+) Bps\s+(\d+) pps', line)
                if match:
                    port_info['statistics']['output_rate_bps'] = int(match.group(1))
                    port_info['statistics']['output_rate_pps'] = int(match.group(2))
            
            # Parse bandwidth throughput
            if 'Input Instantaneous bandwidth throughput' in line:
                match = re.search(r'(\d+\.?\d*)%', line)
                if match:
                    port_info['statistics']['input_bandwidth_percent'] = float(match.group(1))
            
            if 'Output Instantaneous bandwidth throughput' in line:
                match = re.search(r'(\d+\.?\d*)%', line)
                if match:
                    port_info['statistics']['output_bandwidth_percent'] = float(match.group(1))
            
            # Parse PassPackets (Input)
            if 'PassPackets' in line and 'Input' in output[max(0, output.find(line)-200):output.find(line)]:
                match = re.search(r'PassPackets\s*:\s*(\d+)', line)
                if match:
                    port_info['statistics']['input_packets'] = int(match.group(1))
                # Check for DropPackets in same line
                match = re.search(r'DropPackets\s*:\s*(\d+)', line)
                if match:
                    port_info['statistics']['input_drops'] = int(match.group(1))
            
            # Parse PassBytes (Input)
            if 'PassBytes' in line and 'Input' in output[max(0, output.find(line)-300):output.find(line)]:
                match = re.search(r'PassBytes\s*:\s*(\d+)', line)
                if match:
                    port_info['statistics']['input_bytes'] = int(match.group(1))
                # Check for UnicastsPkts in same line
                match = re.search(r'UnicastsPkts\s*:\s*(\d+)', line)
                if match:
                    port_info['statistics']['input_unicast'] = int(match.group(1))
            
            # Parse Multicast and Broadcast
            if 'MulticastsPkts' in line:
                match = re.search(r'MulticastsPkts:\s*(\d+)', line)
                if match:
                    port_info['statistics']['input_multicast'] = int(match.group(1))
                match = re.search(r'BroadcastsPkts:\s*(\d+)', line)
                if match:
                    port_info['statistics']['input_broadcast'] = int(match.group(1))
            
            # Parse CRC errors
            if 'CRCAlignErrors' in line:
                match = re.search(r'CRCAlignErrors:\s*(\d+)', line)
                if match:
                    port_info['statistics']['crc_errors'] = int(match.group(1))
            
            # Parse Output PassPackets
            if 'PassPackets' in line and 'Output' in output[max(0, output.find(line)-200):output.find(line)]:
                match = re.search(r'PassPackets\s*:\s*(\d+)', line)
                if match:
                    port_info['statistics']['output_packets'] = int(match.group(1))
            
            # Parse Output PassBytes
            if 'PassBytes' in line and 'Output' in output[max(0, output.find(line)-300):output.find(line)]:
                match = re.search(r'PassBytes\s*:\s*(\d+)', line)
                if match:
                    port_info['statistics']['output_bytes'] = int(match.group(1))
        
        return port_info



