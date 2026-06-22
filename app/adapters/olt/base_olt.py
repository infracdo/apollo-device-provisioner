"""
Base OLT Adapter

Abstract base class for OLT (Optical Line Terminal) adapters.
"""
from abc import abstractmethod
from typing import Dict, Any, List, Optional
from app.adapters.base import BaseDeviceAdapter


class BaseOLTAdapter(BaseDeviceAdapter):
    """Base class for OLT adapters"""
    
    @abstractmethod
    async def provision_onu(self, onu_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provision an ONU on the OLT
        
        Args:
            onu_config: ONU configuration dictionary containing:
                - serial_no: ONU serial number (required)
                - frame: Frame number (default: 0)
                - slot: Slot number (required)
                - port: Port number (required)
                - ont_id: ONT ID (optional, auto-assigned if not provided)
                - line_profile_id: Line profile ID (required)
                - service_profile_id: Service profile ID (required)
                - vlan: VLAN number (required)
                - description: Description/identifier (required)
                - wan_mode: 'dhcp' or 'bridge' (default: 'dhcp')
                - upload_speed: Upload speed in Kbps (optional)
                - download_speed: Download speed in Kbps (optional)
                - onu_type: ONU device type for BDCOM/ZTE (optional)
        
        Returns:
            dict: Provisioning result containing:
                - status: 'success' or 'error'
                - ont_id: Assigned ONT ID
                - message: Status message
                - output: Command outputs (optional)
        """
        pass
    
    @abstractmethod
    async def remove_onu(self, onu_location: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove/unprovision an ONU
        
        Args:
            onu_location: ONU location dictionary containing:
                - frame: Frame number
                - slot: Slot number
                - port: Port number
                - ont_id: ONT ID
        
        Returns:
            dict: Removal result containing:
                - status: 'success' or 'error'
                - message: Status message
        """
        pass
    
    @abstractmethod
    async def get_onts(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get list of ONTs/ONUs on the OLT
        
        Args:
            filters: Optional filters (slot, port, status, etc.)
        
        Returns:
            list: List of ONT dictionaries with status information
        """
        pass
    
    @abstractmethod
    async def get_ont_status(self, ont_location: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get ONT status and statistics
        
        Args:
            ont_location: ONU location dictionary
        
        Returns:
            dict: ONT status information including:
                - ont_id, serial_no, status, rx_power, tx_power, distance, etc.
        """
        pass
    
    @abstractmethod
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """
        Get configured VLANs on the OLT
        
        Returns:
            list: List of VLAN dictionaries
        """
        pass
    
    @abstractmethod
    async def get_boards(self) -> List[Dict[str, Any]]:
        """
        Get board/card information from the OLT
        
        Returns:
            list: List of board dictionaries with slot, type, status, etc.
        """
        pass
    
    @abstractmethod
    async def reboot_ont(self, ont_location: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reboot an ONT
        
        Args:
            ont_location: ONU location dictionary
        
        Returns:
            dict: Reboot result
        """
        pass
    
    @abstractmethod
    async def get_unconfigured_onts(self) -> List[Dict[str, Any]]:
        """
        Get list of unconfigured ONUs detected by the OLT.
        
        Returns unconfigured/auto-discovered ONUs that are connected but not yet provisioned.
        
        Returns:
            list: List of unconfigured ONU dictionaries containing:
                - serial_number: ONU serial number (required)
                - model: ONU model/type (optional)
                - port: Port where ONU is detected (required)
                - interface: Interface identifier (optional)
                - rack, shelf, slot, frame: Location details (optional)
                - password: ONU password if available (optional)
        """
        pass
    
    async def get_ont_autofind(self) -> List[Dict[str, Any]]:
        """
        Get unconfigured/auto-discovered ONUs (legacy method)
        
        Deprecated: Use get_unconfigured_onts() instead
        
        Returns:
            list: List of unconfigured ONUs with serial numbers
        """
        # Default implementation calls new method for backward compatibility
        return await self.get_unconfigured_onts()
    
    async def get_ont_mac_table(self, ont_location: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get MAC address table learned by ONT
        
        Args:
            ont_location: ONU location dictionary
        
        Returns:
            list: List of MAC addresses learned
        """
        # Override in subclass if supported
        return []
    
    @abstractmethod
    async def create_tcont_profile(self, profile_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create T-CONT (Traffic Container) profile.
        
        T-CONT profiles define bandwidth allocation for ONUs.
        
        Args:
            profile_config: Profile configuration dictionary containing:
                - profile_name: Profile name
                - profile_type: Type (1=Fixed, 2=Assured, 3=Non-Assured, 4=Best-Effort, 5=Mixed)
                - maximum_bandwidth: Maximum bandwidth in bytes
                - assured_bandwidth: Assured bandwidth (optional)
                - fixed_bandwidth: Fixed bandwidth (optional)
        
        Returns:
            dict: Result containing status, profile_name, message, command_output
        """
        pass
    
    @abstractmethod
    async def create_vlan_profile(self, profile_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create VLAN profile for ONU provisioning.
        
        Args:
            profile_config: Profile configuration dictionary containing:
                - profile_name: Profile name
                - tag_mode: 'tag', 'untag', or 'translate'
                - cvlan: Customer VLAN ID
                - svlan: Service VLAN ID (optional)
                - priority: 802.1p priority (optional)
        
        Returns:
            dict: Result containing status, profile_name, message, command_output
        """
        pass
    
    async def get_tcont_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of configured T-CONT profiles.
        
        Returns:
            list: List of T-CONT profile dictionaries
        """
        # Override in subclass if supported
        return []
    
    async def get_vlan_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of configured VLAN profiles.
        
        Returns:
            list: List of VLAN profile dictionaries
        """
        # Override in subclass if supported
        return []
    
    @abstractmethod
    async def delete_tcont_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Delete T-CONT profile from OLT.
        
        Args:
            profile_name: Name of the T-CONT profile to delete
        
        Returns:
            dict: Result containing status, profile_name, message, command_output
        """
        pass
    
    @abstractmethod
    async def delete_vlan_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Delete VLAN profile from OLT.
        
        Args:
            profile_name: Name of the VLAN profile to delete
        
        Returns:
            dict: Result containing status, profile_name, message, command_output
        """
        pass
    
    @abstractmethod
    async def get_port_info(self, port_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed information about an OLT PON port.
        
        Args:
            port_config: Dictionary containing port location information
                - board: Board number (default: 1)
                - card: Card number (default: 1)
                - port: Port number (required)
        
        Returns:
            dict: Port information containing:
                - board: Board number
                - card: Card number
                - port: Port number
                - interface: Interface identifier
                - status: Port activation status (e.g., 'activate', 'deactivate')
                - line_protocol: Line protocol status (e.g., 'up', 'down')
                - description: Port description
                - total_onus: Total ONU capacity of the port
                - registered_onus: Number of currently registered ONUs
                - channel_num: Current channel number
                - statistics: Dictionary with detailed port statistics:
                    - input_rate_bps: Input rate in bytes per second
                    - input_rate_pps: Input rate in packets per second
                    - output_rate_bps: Output rate in bytes per second
                    - output_rate_pps: Output rate in packets per second
                    - input_bandwidth_percent: Input bandwidth utilization percentage
                    - output_bandwidth_percent: Output bandwidth utilization percentage
                    - input_packets: Total input packets passed
                    - input_bytes: Total input bytes passed
                    - input_drops: Total input packets dropped
                    - output_packets: Total output packets passed
                    - output_bytes: Total output bytes passed
                    - input_unicast: Input unicast packets
                    - input_multicast: Input multicast packets
                    - input_broadcast: Input broadcast packets
                    - crc_errors: CRC/alignment errors
        """
        pass
    
    @abstractmethod
    async def register_onu(self, registration_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register and configure an ONU on the OLT.
        
        This performs a complete registration process including:
        1. Registering the ONU with its serial number on the specified port
        2. Configuring ONU settings (name, description, profiles)
        3. Configuring service settings (VLANs, ports, management)
        
        Args:
            registration_data: Dictionary containing registration parameters:
                - board: Board number
                - card: Card number
                - port: Port number where ONU is connected
                - onu_serial_number: Serial number of the ONU
                - onu_type: ONU type/model
                - name: ONU name identifier
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
                - mode: VLAN mode
        
        Returns:
            dict: Registration result containing:
                - status: 'success' or 'error'
                - message: Status message
                - onu_id: Assigned ONU ID
                - interface: Full ONU interface identifier
                - serial_number: ONU serial number
                - command_outputs: Command outputs for debugging
        """
        pass
    
    @abstractmethod
    async def unregister_offline_onus(self, port_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unregister all offline ONUs from a specific port.
        
        This performs:
        1. Identifies all offline ONUs on the specified port
        2. Removes their configuration from the OLT
        
        Args:
            port_config: Dictionary containing port location information
                - board: Board number
                - card: Card number
                - port: Port number
        
        Returns:
            dict: Unregister result containing:
                - status: 'success' or 'error'
                - message: Status message
                - interface: OLT interface identifier
                - offline_onus_found: Number of offline ONUs found
                - onus_unregistered: List of ONU IDs that were unregistered
                - command_outputs: Command outputs for debugging
        """
        pass


