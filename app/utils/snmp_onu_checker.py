"""
SNMP ONU Checker Utility

Checks for unconfigured ONUs via SNMP and returns structured data.
"""
import logging
from typing import List, Dict, Any, Optional
from pysnmp.hlapi import *

logger = logging.getLogger(__name__)


class SNMPONUChecker:
    """Check unconfigured ONUs via SNMP"""
    
    def __init__(self, target_ip: str, community: str = "devCommunity"):
        self.target_ip = target_ip
        self.community = community
    
    @staticmethod
    def decode_serial_number(hex_value: str) -> dict:
        """
        Decode ONT serial number from hex
        Format: 0x4d48415208f6c2d9
        - First 4 bytes (8 hex chars): Vendor ID (ASCII)
        - Remaining bytes: Device serial number
        """
        try:
            if not hex_value or hex_value.strip() == '':
                return {
                    'vendor_id': '',
                    'device_serial': '',
                    'full_serial': '',
                    'is_valid': False
                }
            
            hex_clean = hex_value.replace('0x', '').replace('0X', '')
            
            # Check if it's already ASCII (not hex encoded)
            if not all(c in '0123456789abcdefABCDEF' for c in hex_clean):
                return {
                    'vendor_id': hex_value,
                    'device_serial': '',
                    'full_serial': hex_value,
                    'is_valid': len(hex_value) >= 4
                }
            
            # Skip all-zero or all-one patterns
            if hex_clean == '0' * len(hex_clean) or hex_clean == '1' * len(hex_clean):
                return {
                    'vendor_id': '',
                    'device_serial': '',
                    'full_serial': hex_clean,
                    'is_valid': False
                }
            
            if len(hex_clean) < 8:
                return {
                    'vendor_id': hex_clean,
                    'device_serial': '',
                    'full_serial': hex_clean,
                    'is_valid': False
                }
            
            vendor_bytes = bytes.fromhex(hex_clean[:8])
            vendor_id = vendor_bytes.decode('ascii', errors='ignore').strip()
            device_serial = hex_clean[8:].upper()
            
            is_valid = all(32 <= ord(c) <= 126 for c in vendor_id) and len(vendor_id) > 0
            
            return {
                'vendor_id': vendor_id,
                'device_serial': device_serial,
                'full_serial': f"{vendor_id}{device_serial}",
                'is_valid': is_valid
            }
        except Exception as e:
            logger.warning(f"Failed to decode serial number '{hex_value}': {e}")
            return {
                'vendor_id': 'Unknown',
                'device_serial': 'Unknown',
                'full_serial': hex_value,
                'is_valid': False
            }
    
    @staticmethod
    def decode_olt_port(ont_index: str) -> str:
        """
        Decode OLT port from ONT index
        ONT index format: 285278465 (encoded as 4 bytes)
        Encoding: [rack/frame, slot, subslot, port]
        Display: gpon-olt_slot/subslot/port (skip rack/frame)
        """
        try:
            index = int(ont_index)
            bytes_val = index.to_bytes(4, 'big')
            slot = bytes_val[1]
            subslot = bytes_val[2]
            port = bytes_val[3]
            return f"gpon-olt_{slot}/{subslot}/{port}"
        except Exception as e:
            logger.warning(f"Failed to decode OLT port from '{ont_index}': {e}")
            return "Unknown"
    
    def snmp_walk(self, oid: str) -> List[tuple]:
        """Walk an OID and return all values"""
        results = []
        
        try:
            for (errorIndication,
                 errorStatus,
                 errorIndex,
                 varBinds) in nextCmd(SnmpEngine(),
                                       CommunityData(self.community),
                                       UdpTransportTarget((self.target_ip, 161)),
                                       ContextData(),
                                       ObjectType(ObjectIdentity(oid)),
                                       lexicographicMode=False):
                
                if errorIndication:
                    logger.error(f"SNMP Error: {errorIndication}")
                    break
                elif errorStatus:
                    logger.error(f"SNMP Error: {errorStatus.prettyPrint()}")
                    break
                else:
                    for varBind in varBinds:
                        oid_str = str(varBind[0])
                        value = varBind[1].prettyPrint()
                        results.append((oid_str, value))
            
            return results
            
        except Exception as e:
            logger.error(f"SNMP Walk exception: {e}")
            return []
    
    def get_unconfigured_onus(self, base_oid: str = "1.3.6.1.4.1.3902.1082.500.10.2.2.5.1") -> List[Dict[str, Any]]:
        """
        Get list of unconfigured ONUs via SNMP
        
        Args:
            base_oid: Base OID for unconfigured ONU table
        
        Returns:
            List of unconfigured ONU dictionaries
        """
        logger.info(f"Checking unconfigured ONUs on {self.target_ip}")
        
        # Walk the OID
        results = self.snmp_walk(base_oid)
        
        if not results:
            logger.warning("No SNMP data returned")
            return []
        
        logger.info(f"Retrieved {len(results)} SNMP values")
        
        # Parse results
        uncfg_onus = self._parse_snmp_results(results)
        
        logger.info(f"Found {len(uncfg_onus)} valid unconfigured ONUs")
        return uncfg_onus
    
    def _parse_snmp_results(self, results: List[tuple]) -> List[Dict[str, Any]]:
        """Parse SNMP results to extract unconfigured ONU information"""
        # Build mappings by OLT index and ONU index
        serial_map = {}   # Column 2
        model_map = {}    # Column 7
        firmware_map = {} # Column 8
        
        for oid_str, value in results:
            parts = oid_str.split('.')
            if len(parts) < 3:
                continue
            
            column = parts[-3]
            olt_idx_raw = parts[-2]
            onu_idx = parts[-1]
            
            key = (olt_idx_raw, onu_idx)
            
            if column == '2':  # Serial number
                serial_map[key] = value
            elif column == '7':  # Model
                model_map[key] = value
            elif column == '8':  # Firmware
                firmware_map[key] = value
        
        # Process serial numbers and correlate with model data
        uncfg_onus = []
        
        for key, serial_value in sorted(serial_map.items()):
            olt_idx_raw, onu_idx = key
            
            # Decode serial number
            serial_decoded = self.decode_serial_number(serial_value)
            
            # Only include valid ONUs
            if not serial_decoded.get('is_valid', False):
                continue
            
            # Build OID for reference
            oid_str = f"1.3.6.1.4.1.3902.1082.500.10.2.2.5.1.2.{olt_idx_raw}.{onu_idx}"
            
            # Decode OLT port
            olt_port = self.decode_olt_port(olt_idx_raw)
            
            # Get model and firmware
            model = model_map.get(key, 'Unknown')
            firmware = firmware_map.get(key, 'Unknown')
            
            onu_info = {
                'ont_index': olt_idx_raw,
                'onu_index': onu_idx,
                'oid': oid_str,
                'ont_serial': serial_decoded['full_serial'],
                'vendor_id': serial_decoded['vendor_id'],
                'device_serial': serial_decoded['device_serial'],
                'olt_port': olt_port,
                'ont_model': model,
                'ont_firmware': firmware,
                'raw_value': serial_value
            }
            
            uncfg_onus.append(onu_info)
        
        return uncfg_onus
