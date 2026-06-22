"""
RADIUS Change of Authorization (CoA) Client

Implements RFC 5176 for dynamic session management.
Allows updating user session parameters without disconnection.
"""
import socket
import struct
import hashlib
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class RadiusCoA:
    """RADIUS Change of Authorization (RFC 5176) Client"""
    
    # RADIUS Packet Codes (RFC 5176)
    COA_REQUEST = 43
    DISCONNECT_REQUEST = 40
    COA_ACK = 44
    COA_NAK = 45
    DISCONNECT_ACK = 41
    DISCONNECT_NAK = 42
    
    # RADIUS Attribute Types (RFC 2865 + vendor-specific)
    ATTR_USER_NAME = 1
    ATTR_NAS_IP_ADDRESS = 4
    ATTR_NAS_IDENTIFIER = 32
    ATTR_ACCT_SESSION_ID = 44
    ATTR_FRAMED_IP_ADDRESS = 8
    
    # Mikrotik Vendor-Specific Attributes (Vendor-ID: 14988)
    ATTR_VENDOR_SPECIFIC = 26
    MIKROTIK_VENDOR_ID = 14988
    MIKROTIK_RATE_LIMIT = 8
    MIKROTIK_ADDRESS_LIST = 9
    MIKROTIK_GROUP = 10
    
    def __init__(self, nas_ip: str, nas_port: int = 3799, secret: str = "ap0ll0", target_ip: str = None, target_port: int = None):
        """
        Initialize RADIUS CoA client
        
        Args:
            nas_ip: NAS IP address (used in RADIUS attributes for identification)
            nas_port: NAS CoA port (used in RADIUS attributes)
            secret: RADIUS shared secret
            target_ip: Actual IP to send packets to (if different from nas_ip, for NAT scenarios)
            target_port: Actual port to send packets to (if different from nas_port)
        """
        self.nas_ip = nas_ip  # Goes in RADIUS attribute
        self.nas_port = nas_port
        self.secret = secret.encode('utf-8')
        
        # Target for actual packet transmission (may differ for NAT)
        self.target_ip = target_ip if target_ip else nas_ip
        self.target_port = target_port if target_port else nas_port
        
        logger.info(f"[CoA] NAS-IP-Address attribute: {nas_ip}:{nas_port}")
        logger.info(f"[CoA] Sending packets to: {self.target_ip}:{self.target_port}")
        
    def _build_vendor_specific_attr(self, vendor_id: int, vendor_type: int, vendor_value: str) -> bytes:
        """Build a Vendor-Specific attribute (Type 26)"""
        value = vendor_value.encode('utf-8')
        vendor_length = 2 + len(value)  # Vendor Type (1) + Vendor Length (1) + Value
        
        # Vendor-Specific structure:
        # Type (1) | Length (1) | Vendor-ID (4) | Vendor-Type (1) | Vendor-Length (1) | Value
        vendor_data = struct.pack('!I', vendor_id)  # Vendor ID (4 bytes)
        vendor_data += struct.pack('!BB', vendor_type, vendor_length)  # Vendor Type + Vendor Length
        vendor_data += value
        
        # Total attribute length: Type (1) + Length (1) + Vendor-ID (4) + Vendor-Type (1) + Vendor-Length (1) + Value
        attr_length = 2 + len(vendor_data)  # Type + Length fields + vendor_data
        return struct.pack('!BB', self.ATTR_VENDOR_SPECIFIC, attr_length) + vendor_data
        
    def _build_packet(self, code: int, attributes: Dict[str, Any], identifier: int = None) -> bytes:
        """
        Build a RADIUS packet
        
        Args:
            code: RADIUS packet code (COA_REQUEST, DISCONNECT_REQUEST, etc.)
            attributes: Dictionary of attributes to include
            identifier: Packet identifier (random if not provided)
            
        Returns:
            Complete RADIUS packet as bytes
        """
        if identifier is None:
            identifier = int.from_bytes(os.urandom(1), 'big')
            
        # Build attributes first
        attr_data = b''
        
        # Standard attributes
        if 'user_name' in attributes:
            username = attributes['user_name'].encode('utf-8')
            attr_data += struct.pack('!BB', self.ATTR_USER_NAME, len(username) + 2) + username
            
        if 'nas_ip_address' in attributes:
            nas_ip = socket.inet_aton(attributes['nas_ip_address'])
            attr_data += struct.pack('!BB', self.ATTR_NAS_IP_ADDRESS, 6) + nas_ip
            
        if 'session_id' in attributes:
            session = attributes['session_id'].encode('utf-8')
            attr_data += struct.pack('!BB', self.ATTR_ACCT_SESSION_ID, len(session) + 2) + session
            
        if 'framed_ip' in attributes:
            framed_ip = socket.inet_aton(attributes['framed_ip'])
            attr_data += struct.pack('!BB', self.ATTR_FRAMED_IP_ADDRESS, 6) + framed_ip
            
        # Mikrotik Vendor-Specific Attributes
        if 'mikrotik_rate_limit' in attributes:
            attr_data += self._build_vendor_specific_attr(
                self.MIKROTIK_VENDOR_ID,
                self.MIKROTIK_RATE_LIMIT,
                attributes['mikrotik_rate_limit']
            )
            
        if 'mikrotik_address_list' in attributes:
            attr_data += self._build_vendor_specific_attr(
                self.MIKROTIK_VENDOR_ID,
                self.MIKROTIK_ADDRESS_LIST,
                attributes['mikrotik_address_list']
            )
            
        if 'mikrotik_group' in attributes:
            attr_data += self._build_vendor_specific_attr(
                self.MIKROTIK_VENDOR_ID,
                self.MIKROTIK_GROUP,
                attributes['mikrotik_group']
            )
            
        # Build packet header with zero authenticator first
        # RFC 5176: The Authenticator field in CoA/Disconnect-Request must be calculated
        # as MD5(Code + ID + Length + 16 zero octets + Attributes + Secret)
        length = 20 + len(attr_data)  # Header (20) + Attributes
        zero_auth = b'\x00' * 16
        
        # Build initial packet with zero authenticator
        temp_packet = struct.pack('!BBH', code, identifier, length) + zero_auth + attr_data
        
        # Calculate MD5 hash: MD5(packet + secret)
        md5 = hashlib.md5()
        md5.update(temp_packet + self.secret)
        authenticator = md5.digest()
        
        # Build final packet with calculated authenticator
        packet = struct.pack('!BBH', code, identifier, length) + authenticator + attr_data
        
        return packet
        
    def _send_request(self, packet: bytes) -> Dict[str, Any]:
        """
        Send CoA request and wait for response
        
        Returns:
            Dictionary with success status and message
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        
        try:
            # Log details
            code, identifier, length = struct.unpack('!BBH', packet[:4])
            logger.info(f"[CoA] Sending to {self.target_ip}:{self.target_port} (NAS attribute: {self.nas_ip})")
            
            # Send packet to target (may be different from NAS IP in attributes)
            sock.sendto(packet, (self.target_ip, self.target_port))
            logger.info(f"[CoA] Request sent successfully")
            
            # Wait for response
            data, addr = sock.recvfrom(4096)
            code, identifier, length = struct.unpack('!BBH', data[:4])
            
            if code == self.COA_ACK:
                logger.info(f"[CoA] Received CoA-ACK from {addr}")
                return {'success': True, 'message': 'CoA accepted by NAS'}
            elif code == self.COA_NAK:
                logger.warning(f"[CoA] Received CoA-NAK from {addr}")
                return {'success': False, 'message': 'CoA rejected by NAS'}
            elif code == self.DISCONNECT_ACK:
                logger.info(f"[CoA] Received Disconnect-ACK from {addr}")
                return {'success': True, 'message': 'Disconnect accepted by NAS'}
            elif code == self.DISCONNECT_NAK:
                logger.warning(f"[CoA] Received Disconnect-NAK from {addr}")
                return {'success': False, 'message': 'Disconnect rejected by NAS'}
            else:
                logger.error(f"[CoA] Unexpected response code: {code}")
                return {'success': False, 'message': f'Unexpected response code: {code}'}
                
        except socket.timeout:
            logger.error(f"[CoA] Timeout waiting for response from {self.nas_ip}")
            return {'success': False, 'message': 'Timeout - NAS did not respond'}
        except Exception as e:
            logger.error(f"[CoA] Error sending request: {e}")
            return {'success': False, 'message': f'Error: {str(e)}'}
        finally:
            sock.close()
            
    def change_attributes(
        self,
        username: str,
        nas_ip: str = None,
        rate_limit: Optional[str] = None,
        address_list: Optional[str] = None,
        group: Optional[str] = None,
        session_id: Optional[str] = None,
        framed_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send CoA-Request to change user session attributes
        
        Args:
            username: PPPoE username
            nas_ip: NAS IP address (DEPRECATED - not used in CoA, kept for backward compatibility)
            rate_limit: New bandwidth limit (e.g., "50M/50M")
            address_list: New address list
            group: New user group
            session_id: Optional session ID for precise targeting
            framed_ip: Optional framed IP for targeting
            
        Returns:
            Dictionary with success status and message
        """
        attributes = {
            'user_name': username,
        }
        
        # Note: NAS-IP-Address is NOT included in CoA packets
        # CoA identifies the session by username/session_id/framed_ip, not by NAS
        
        # Add optional targeting attributes
        if session_id:
            attributes['session_id'] = session_id
        if framed_ip:
            attributes['framed_ip'] = framed_ip
            
        # Add Mikrotik-specific attributes to change
        if rate_limit:
            attributes['mikrotik_rate_limit'] = rate_limit
        if address_list:
            attributes['mikrotik_address_list'] = address_list
        if group:
            attributes['mikrotik_group'] = group
            
        packet = self._build_packet(self.COA_REQUEST, attributes)
        return self._send_request(packet)
        
    def disconnect_user(
        self,
        username: str,
        nas_ip: str = None,
        session_id: Optional[str] = None,
        framed_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send Disconnect-Request to terminate user session
        
        Args:
            username: PPPoE username
            nas_ip: NAS IP address (DEPRECATED - not used in Disconnect, kept for backward compatibility)
            session_id: Optional session ID
            framed_ip: Optional framed IP
            
        Returns:
            Dictionary with success status and message
        """
        attributes = {
            'user_name': username,
        }
        
        # Note: NAS-IP-Address is NOT included in Disconnect packets
        # Disconnect identifies the session by username/session_id/framed_ip
        
        if session_id:
            attributes['session_id'] = session_id
        if framed_ip:
            attributes['framed_ip'] = framed_ip
            
        packet = self._build_packet(self.DISCONNECT_REQUEST, attributes)
        return self._send_request(packet)
