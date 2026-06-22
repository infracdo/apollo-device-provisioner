"""
Telnet Connector

Telnet connection handler using telnetlib3.
"""
import asyncio
import telnetlib3
from typing import Optional
from app.utils.logging import logger


class TelnetConnector:
    """Telnet connection handler"""
    
    def __init__(
        self,
        host: str,
        port: int = 23,
        username: str = "",
        password: str = "",
        timeout: int = 30
    ):
        """Initialize Telnet connector"""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.reader: Optional[telnetlib3.TelnetReader] = None
        self.writer: Optional[telnetlib3.TelnetWriter] = None
        self.is_connected = False
        
        # Log credentials (mask password for security)
        masked_password = password[:2] + '*' * (len(password) - 2) if len(password) > 2 else '*' * len(password)
        logger.info(f"[TELNET INIT] {host}:{port} - Username: '{username}' | Password: '{masked_password}' (length: {len(password)})")
        
    async def connect(self) -> bool:
        """Establish Telnet connection"""
        max_retries = 2
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                # Add a small delay to prevent race conditions with telnetlib3
                if attempt > 0:
                    await asyncio.sleep(retry_delay)
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries} for {self.host}:{self.port}")
                
                # Open connection with connect_minwait to avoid race condition
                self.reader, self.writer = await asyncio.wait_for(
                    telnetlib3.open_connection(
                        self.host, 
                        self.port,
                        connect_minwait=0.5  # Wait 500ms after connection before proceeding
                    ),
                    timeout=self.timeout
                )
                
                # Small delay to ensure telnet client is fully initialized
                await asyncio.sleep(0.2)
                
                # Login
                await self._login()
                
                self.is_connected = True
                logger.info(f"Telnet connected to {self.host}:{self.port}")
                return True
                
            except PermissionError:
                # Authentication failed - propagate this error
                self.is_connected = False
                raise
                
            except AttributeError as e:
                # This is the race condition error - retry
                if attempt < max_retries - 1:
                    logger.warning(f"Telnet race condition on {self.host}:{self.port}: {str(e)} - retrying...")
                    continue
                else:
                    logger.error(f"Telnet connection failed after {max_retries} attempts to {self.host}:{self.port} - {str(e)}")
                    self.is_connected = False
                    return False
                    
            except Exception as e:
                logger.error(f"Telnet connection failed to {self.host}:{self.port} - {str(e)}")
                self.is_connected = False
                return False
        
        return False
    
    async def _login(self):
        """Handle login prompts"""
        logger.debug(f"[TELNET LOGIN] {self.host}: Waiting for username prompt...")
        # Wait for username prompt
        output = await asyncio.wait_for(
            self.reader.read(4096),
            timeout=10
        )
        logger.debug(f"[TELNET LOGIN] {self.host}: Initial prompt ({len(output)} bytes): {repr(output[:200])}")
        
        if 'username:' in output.lower() or 'login:' in output.lower():
            logger.info(f"[TELNET LOGIN] {self.host}: Sending username: '{self.username}'")
            self.writer.write(self.username + '\n')
            await self.writer.drain()
        else:
            logger.warning(f"[TELNET LOGIN] {self.host}: Username prompt not found in initial output")
            
        # Wait for password prompt - may need multiple reads
        logger.debug(f"[TELNET LOGIN] {self.host}: Waiting for password prompt...")
        output = ''
        password_prompt_found = False
        
        for attempt in range(3):
            try:
                chunk = await asyncio.wait_for(
                    self.reader.read(4096),
                    timeout=2.0
                )
                output += chunk
                logger.debug(f"[TELNET LOGIN] {self.host}: Password prompt attempt {attempt+1} ({len(chunk)} bytes): {repr(chunk[:200])}")
                
                # Check if we got the password prompt
                if 'password:' in chunk.lower():
                    logger.debug(f"[TELNET LOGIN] {self.host}: Found password prompt in chunk")
                    password_prompt_found = True
                    break
                    
            except asyncio.TimeoutError:
                logger.debug(f"[TELNET LOGIN] {self.host}: Timeout waiting for password prompt on attempt {attempt+1}")
                if output:
                    break
        
        logger.debug(f"[TELNET LOGIN] {self.host}: Total output after username ({len(output)} bytes): {repr(output)}")
        
        if password_prompt_found or 'password:' in output.lower():
            masked_pwd = self.password[:2] + '*' * (len(self.password) - 2) if len(self.password) > 2 else '*' * len(self.password)
            logger.info(f"[TELNET LOGIN] {self.host}: Found password prompt, sending password: '{masked_pwd}' (length: {len(self.password)} chars)")
            logger.debug(f"[TELNET LOGIN] {self.host}: Actual password being sent: '{self.password}'")
            self.writer.write(self.password + '\n')
            await self.writer.drain()
            
            # Give device time to process authentication
            await asyncio.sleep(0.5)
        else:
            logger.error(f"[TELNET LOGIN] {self.host}: Password prompt NOT found after username! Got: {repr(output)}")
            raise ConnectionError(f"Password prompt not received after sending username to {self.host}")
            
        # Read login response - may need multiple reads to get full prompt
        logger.debug(f"[TELNET LOGIN] {self.host}: Waiting for login response...")
        response = ''
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                chunk = await asyncio.wait_for(
                    self.reader.read(4096),
                    timeout=2.0 if attempt == 0 else 1.0
                )
                response += chunk
                logger.debug(f"[TELNET LOGIN] {self.host}: Login response attempt {attempt+1} ({len(chunk)} bytes): {repr(chunk[:200])}")
                
                # If we got a prompt marker (#, >), we're done
                if any(marker in chunk for marker in ['#', '>', '$']):
                    logger.debug(f"[TELNET LOGIN] {self.host}: Found prompt marker in response")
                    break
                    
                # If still showing password prompt, try reading more
                if chunk.strip().endswith('Password:') or chunk.strip().endswith('password:'):
                    logger.debug(f"[TELNET LOGIN] {self.host}: Still at password prompt, waiting for more data...")
                    await asyncio.sleep(0.3)
                    continue
                    
            except asyncio.TimeoutError:
                logger.debug(f"[TELNET LOGIN] {self.host}: Read timeout on attempt {attempt+1}, response so far: {len(response)} bytes")
                if response:
                    # We got something, break and evaluate it
                    break
                elif attempt < max_attempts - 1:
                    # No response yet, try again
                    continue
                else:
                    # Final attempt failed with no data
                    logger.warning(f"[TELNET LOGIN] {self.host}: No response after password")
                    break
        
        logger.debug(f"[TELNET LOGIN] {self.host}: Total login response ({len(response)} bytes): {repr(response[:300])}")
        logger.info(f"[TELNET LOGIN] {self.host}: Login complete, final prompt: {repr(response[-50:])}")
        
        # Check if login failed
        response_lower = response.lower()
        
        # Check for authentication failure indicators
        if any(indicator in response_lower for indicator in [
            'incorrect password',
            'login incorrect',
            'authentication failed',
            'access denied',
            'login failed',
            'invalid password',
            'bad password'
        ]):
            logger.error(f"[TELNET LOGIN] {self.host}: Authentication failed - incorrect password")
            raise PermissionError(f"Authentication failed for {self.host}: Incorrect password")
        
        # Check if we're still at password prompt (password was rejected silently)
        if response.strip().endswith('Password:') or response.strip().endswith('password:'):
            logger.error(f"[TELNET LOGIN] {self.host}: Still at password prompt after login - password likely incorrect")
            raise PermissionError(f"Authentication failed for {self.host}: Password rejected (still at password prompt)")
        
        # Check if we got a username prompt again (complete auth failure)
        if 'username:' in response_lower or 'login:' in response_lower:
            logger.error(f"[TELNET LOGIN] {self.host}: Back at username prompt - authentication failed")
            raise PermissionError(f"Authentication failed for {self.host}: Credentials rejected")
        
        # Verify we got a command prompt (should contain # or > typically)
        if not any(char in response for char in ['#', '>']):
            logger.warning(f"[TELNET LOGIN] {self.host}: Login response doesn't contain expected prompt markers (# or >), but proceeding...")
        else:
            logger.info(f"[TELNET LOGIN] {self.host}: Successfully authenticated, prompt ready")
    
    async def disconnect(self) -> bool:
        """Close Telnet connection"""
        try:
            if self.writer:
                self.writer.close()
                # TelnetWriterUnicode doesn't have wait_closed(), just close is enough
            self.is_connected = False
            self.writer = None
            self.reader = None
            logger.info(f"Telnet disconnected from {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting Telnet: {str(e)}")
            return False
    
    async def execute(self, command: str, handle_pagination: bool = True) -> str:
        """
        Execute command over Telnet
        
        Args:
            command: Command to execute
            handle_pagination: If True, handle pagination (--More--) by sending space
            
        Returns:
            str: Command output
        """
        if not self.is_connected or not self.writer or not self.reader:
            raise ConnectionError("Not connected to Telnet server")
        
        try:
            # Send command
            self.writer.write(command + '\n')
            await self.writer.drain()
            
            if handle_pagination:
                # Read all output, handling pagination prompts
                output = ""
                chunk_timeout = 3  # Timeout for each chunk
                
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            self.reader.read(65536),
                            timeout=chunk_timeout
                        )
                        
                        if not chunk:  # No more data
                            break
                            
                        output += chunk
                        
                        # Check for pagination prompts (--More--, More, etc.)
                        # These usually appear at the end of the current output
                        last_part = output[-100:].lower() if len(output) > 100 else output.lower()
                        
                        if '--more--' in last_part or '-- more --' in last_part:
                            # Send space to get next page
                            self.writer.write(' ')
                            await self.writer.drain()
                            logger.debug("Sent space for pagination")
                            continue
                        
                        # Check if we've received the command prompt (end of output)
                        # Common prompt patterns: hostname#, hostname>, #, >, $
                        lines = output.split('\n')
                        if len(lines) > 0:
                            last_line = lines[-1].strip()
                            # Check for prompt patterns at end of last line
                            if last_line and any(last_line.endswith(p) for p in ['#', '>', '$']):
                                logger.debug(f"Found prompt: {last_line}")
                                break
                        
                    except asyncio.TimeoutError:
                        # No more data available - we're done
                        logger.debug("Timeout reached, no more data")
                        break
                
                return output
            else:
                # Single read with longer timeout (old behavior)
                output = await asyncio.wait_for(
                    self.reader.read(65536),
                    timeout=self.timeout
                )
                return output
                
        except Exception as e:
            logger.error(f"Error executing Telnet command: {str(e)}")
            raise
