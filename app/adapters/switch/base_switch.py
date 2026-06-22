"""
Base Switch Adapter

Abstract base class for switch device adapters.
Defines common interface for network switch operations.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from app.models import Device


class BaseSwitchAdapter(ABC):
    """Base class for switch adapters"""
    
    def __init__(self, device: Device):
        """Initialize switch adapter
        
        Args:
            device: Device model instance
        """
        self.device = device
        self.connector = None
        
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to switch
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Close connection to switch
        
        Returns:
            bool: True if disconnection successful
        """
        pass
    
    @abstractmethod
    async def execute_command(self, command: str) -> str:
        """Execute command on switch
        
        Args:
            command: Command string to execute
            
        Returns:
            str: Command output
        """
        pass
    
    # Interface Management
    
    @abstractmethod
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """Get list of all interfaces with status
        
        Returns:
            List of interfaces with properties:
            - name: Interface name (e.g., GigabitEthernet0/1)
            - status: up/down/disabled
            - speed: Interface speed (e.g., 1000, 10000)
            - duplex: full/half/auto
            - description: Interface description
            - vlan: Access VLAN or trunk VLANs
            - type: access/trunk/routed
        """
        pass
    
    @abstractmethod
    async def get_interface_status(self, interface: str) -> Dict[str, Any]:
        """Get detailed status of specific interface
        
        Args:
            interface: Interface name
            
        Returns:
            Dict with interface details
        """
        pass
    
    @abstractmethod
    async def get_interface_statistics(self, interface: str) -> Dict[str, Any]:
        """Get traffic statistics for interface
        
        Args:
            interface: Interface name
            
        Returns:
            Dict with statistics (packets, bytes, errors, etc.)
        """
        pass
    
    @abstractmethod
    async def set_interface_status(self, interface: str, enabled: bool) -> bool:
        """Enable or disable an interface
        
        Args:
            interface: Interface name
            enabled: True to enable, False to disable (shutdown)
            
        Returns:
            bool: True if successful
        """
        pass
    
    @abstractmethod
    async def set_interface_description(self, interface: str, description: str) -> bool:
        """Set interface description
        
        Args:
            interface: Interface name
            description: Description text
            
        Returns:
            bool: True if successful
        """
        pass
    
    # VLAN Management
    
    @abstractmethod
    async def get_vlans(self) -> List[Dict[str, Any]]:
        """Get list of configured VLANs
        
        Returns:
            List of VLANs with properties:
            - vlan_id: VLAN ID number
            - name: VLAN name
            - status: active/suspended
            - ports: List of ports in this VLAN
        """
        pass
    
    @abstractmethod
    async def get_vlan_info(self, vlan_id: int) -> Dict[str, Any]:
        """Get detailed information about specific VLAN
        
        Args:
            vlan_id: VLAN ID
            
        Returns:
            Dict with VLAN details
        """
        pass
    
    @abstractmethod
    async def create_vlan(self, vlan_id: int, name: str) -> bool:
        """Create a new VLAN
        
        Args:
            vlan_id: VLAN ID (1-4094)
            name: VLAN name
            
        Returns:
            bool: True if successful
        """
        pass
    
    @abstractmethod
    async def delete_vlan(self, vlan_id: int) -> bool:
        """Delete a VLAN
        
        Args:
            vlan_id: VLAN ID
            
        Returns:
            bool: True if successful
        """
        pass
    
    @abstractmethod
    async def set_interface_vlan(self, interface: str, vlan_id: int, mode: str = "access") -> bool:
        """Assign interface to VLAN
        
        Args:
            interface: Interface name
            vlan_id: VLAN ID
            mode: 'access' or 'trunk'
            
        Returns:
            bool: True if successful
        """
        pass
    
    @abstractmethod
    async def set_trunk_allowed_vlans(self, interface: str, vlans: List[int]) -> bool:
        """Set allowed VLANs on trunk port
        
        Args:
            interface: Interface name
            vlans: List of VLAN IDs to allow
            
        Returns:
            bool: True if successful
        """
        pass
    
    # MAC Address Table
    
    @abstractmethod
    async def get_mac_table(self, vlan: Optional[int] = None, interface: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get MAC address table
        
        Args:
            vlan: Filter by VLAN ID (optional)
            interface: Filter by interface (optional)
            
        Returns:
            List of MAC entries with:
            - mac_address: MAC address
            - vlan: VLAN ID
            - interface: Interface name
            - type: dynamic/static
        """
        pass
    
    @abstractmethod
    async def get_arp_table(self) -> List[Dict[str, Any]]:
        """Get ARP table
        
        Returns:
            List of ARP entries with:
            - ip_address: IP address
            - mac_address: MAC address
            - interface: Interface name
            - age: Entry age in seconds
        """
        pass
    
    # Configuration
    
    @abstractmethod
    async def get_running_config(self) -> str:
        """Get running configuration
        
        Returns:
            str: Running configuration text
        """
        pass
    
    @abstractmethod
    async def get_startup_config(self) -> str:
        """Get startup configuration
        
        Returns:
            str: Startup configuration text
        """
        pass
    
    @abstractmethod
    async def save_config(self) -> bool:
        """Save running configuration to startup
        
        Returns:
            bool: True if successful
        """
        pass
    
    # System Information
    
    @abstractmethod
    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information
        
        Returns:
            Dict with system info:
            - hostname: Device hostname
            - model: Device model
            - version: Software version
            - uptime: System uptime
            - serial: Serial number
        """
        pass
    
    @abstractmethod
    async def get_port_statistics_summary(self) -> Dict[str, Any]:
        """Get summary of port statistics
        
        Returns:
            Dict with summary:
            - total_ports: Total number of ports
            - up_ports: Number of up ports
            - down_ports: Number of down ports
        """
        pass
    
    # Discovery and Capabilities
    
    @abstractmethod
    async def discover_commands(self) -> Dict[str, Any]:
        """Discover supported commands on the switch
        
        Tests a predefined list of common switch commands and returns which ones work.
        
        Returns:
            Dict with discovery results:
            - successful: List of dicts with successful commands [{command, description, output_size}]
            - failed: List of dicts with failed commands [{command, description, error}]
            - capabilities: Dict of detected capabilities
        """
        pass
    
    @abstractmethod
    async def discover_vlan_port_mapping(self) -> Dict[str, Any]:
        """Discover VLAN to port mappings
        
        Returns detailed VLAN configuration for all ports.
        
        Returns:
            Dict with VLAN mappings:
            - vlans: List of VLANs with their ports
            - ports: Dict of port configurations {port: {mode, vlans, status}}
            - raw_outputs: Dict of raw command outputs for reference
        """
        pass
    
    @abstractmethod
    async def get_switch_capabilities(self) -> Dict[str, Any]:
        """Get switch capabilities and features
        
        Returns:
            Dict with capabilities:
            - manufacturer: Switch manufacturer
            - model: Switch model
            - os_version: Operating system version
            - supported_features: List of supported features
            - port_count: Number of ports
            - vlan_range: Supported VLAN ID range
        """
        pass
