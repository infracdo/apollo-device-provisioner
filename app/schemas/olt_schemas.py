"""
OLT Pydantic Schemas

Request and response models for OLT API endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime


class StandardONTInfo(BaseModel):
    """Standardized ONT/ONU information model - works across all OLT manufacturers"""
    
    # Location information (standardized)
    port: int = Field(..., description="PON port number")
    ont_id: int = Field(..., description="ONT ID on the port")
    
    # Optional location details (for devices that use them)
    rack: Optional[int] = Field(None, description="Rack number (if applicable)")
    shelf: Optional[int] = Field(None, description="Shelf number (if applicable)")
    slot: Optional[int] = Field(None, description="Slot number (if applicable)")
    frame: Optional[int] = Field(None, description="Frame number (if applicable)")
    
    # Identity
    serial_number: Optional[str] = Field(None, description="ONU serial number")
    interface: Optional[str] = Field(None, description="Interface name (e.g., gpon1/0, 1/1/1:1)")
    
    # Status information (standardized)
    status: str = Field(..., description="Overall status: online, offline, los, dying-gasp, etc.")
    admin_state: Optional[str] = Field(None, description="Admin state: enable, disable, up, down")
    operational_state: Optional[str] = Field(None, description="Operational state")
    phase_state: Optional[str] = Field(None, description="Phase/config state")
    
    # Signal levels
    rx_power: Optional[str] = Field(None, description="RX power level (dBm)")
    tx_power: Optional[str] = Field(None, description="TX power level (dBm)")
    olt_rx_power: Optional[str] = Field(None, description="OLT RX power (from ONU)")
    distance: Optional[str] = Field(None, description="Distance from OLT")
    
    # Additional info
    description: Optional[str] = Field(None, description="ONU description/name")
    register_time: Optional[str] = Field(None, description="Registration time")
    last_down_cause: Optional[str] = Field(None, description="Last down cause")
    
    # Manufacturer-specific data (for backward compatibility)
    vendor_data: Optional[Dict[str, Any]] = Field(None, description="Vendor-specific additional data")


class ONTListResponse(BaseModel):
    """Standardized response for ONT list endpoint"""
    device_id: int = Field(..., description="OLT device ID")
    device_name: str = Field(..., description="OLT device name")
    manufacturer: str = Field(..., description="OLT manufacturer")
    total_onts: int = Field(..., description="Total number of ONTs")
    onts: List[StandardONTInfo] = Field(..., description="List of ONTs")


class StandardUnconfiguredONU(BaseModel):
    """Standardized unconfigured ONU information model - works across all OLT manufacturers"""
    
    # Location information (standardized)
    port: int = Field(..., description="PON port number where ONU is detected")
    
    # Optional location details (for devices that use them)
    rack: Optional[int] = Field(None, description="Rack number (if applicable)")
    shelf: Optional[int] = Field(None, description="Shelf number (if applicable)")
    slot: Optional[int] = Field(None, description="Slot number (if applicable)")
    frame: Optional[int] = Field(None, description="Frame number (if applicable)")
    
    # Identity
    serial_number: str = Field(..., description="ONU serial number detected")
    model: Optional[str] = Field(None, description="ONU model/type detected")
    interface: Optional[str] = Field(None, description="Interface/OLT index (e.g., gpon-olt_1/1/2)")
    
    # Authentication
    password: Optional[str] = Field(None, description="ONU password if available")
    
    # Manufacturer-specific data
    vendor_data: Optional[Dict[str, Any]] = Field(None, description="Vendor-specific additional data")


class UnconfiguredONUListResponse(BaseModel):
    """Standardized response for unconfigured ONU list endpoint"""
    device_id: int = Field(..., description="OLT device ID")
    device_name: str = Field(..., description="OLT device name")
    manufacturer: str = Field(..., description="OLT manufacturer")
    total_unconfigured: int = Field(..., description="Total number of unconfigured ONUs")
    unconfigured_onus: List[StandardUnconfiguredONU] = Field(..., description="List of unconfigured ONUs")


class ONUConfig(BaseModel):
    """ONU configuration model"""
    serial_no: str = Field(..., description="ONU serial number")
    frame: int = Field(default=0, description="Frame number")
    slot: int = Field(..., description="Slot number")
    port: int = Field(..., description="Port number")
    ont_id: Optional[int] = Field(None, description="ONT ID (auto-assigned if not provided)")
    line_profile_id: int = Field(..., description="Line profile ID")
    service_profile_id: int = Field(..., description="Service profile ID")
    vlan: int = Field(..., ge=1, le=4094, description="VLAN number")
    description: str = Field(..., max_length=255, description="Description")
    wan_mode: Literal['dhcp', 'bridge'] = Field(default='dhcp', description="WAN connection mode")
    upload_speed: Optional[int] = Field(None, description="Upload speed in Kbps")
    download_speed: Optional[int] = Field(None, description="Download speed in Kbps")
    onu_type: Optional[str] = Field(None, description="ONU device type (for BDCOM/ZTE)")


class ONUProvisionRequest(BaseModel):
    """ONU provision request model"""
    device_id: int = Field(..., description="OLT device ID")
    onu_config: ONUConfig


class ONUProvisionResponse(BaseModel):
    """ONU provision response model"""
    status: Literal['success', 'error']
    ont_id: Optional[int] = None
    message: str
    output: Optional[str] = None


class ONULocation(BaseModel):
    """ONU location model"""
    frame: int = Field(default=0, description="Frame number")
    slot: int = Field(..., description="Slot number")
    port: int = Field(..., description="Port number")
    ont_id: int = Field(..., description="ONT ID")


class ONURemoveRequest(BaseModel):
    """ONU remove request model"""
    device_id: int = Field(..., description="OLT device ID")
    onu_location: ONULocation


class ONUStatusResponse(BaseModel):
    """ONU status response model"""
    ont_id: int
    serial_no: str
    status: str
    rx_power: Optional[float] = None
    tx_power: Optional[float] = None
    distance: Optional[int] = None


class VLANResponse(BaseModel):
    """VLAN response model"""
    vlan_number: int
    vlan_name: str
    status: Optional[str] = None


class BoardResponse(BaseModel):
    """Board response model"""
    slot: int
    board_type: str
    status: str
    ports: Optional[int] = None


# ============================================================================
# GPON Profile Schemas
# ============================================================================

class TcontProfileRequest(BaseModel):
    """
    Request model for creating T-CONT profile.
    
    Note: For ZTE OLTs, only device_id, profile_name, profile_type, and maximum_bandwidth are used.
    assured_bandwidth and fixed_bandwidth may be supported by other manufacturers (e.g., Huawei).
    """
    device_id: int = Field(..., description="OLT device ID")
    profile_name: str = Field(..., min_length=1, max_length=64, description="T-CONT profile name (e.g., '10M')")
    profile_type: int = Field(..., ge=1, le=5, description="T-CONT type: 1=Fixed, 2=Assured, 3=Non-Assured, 4=Best-Effort, 5=Mixed")
    maximum_bandwidth: int = Field(..., gt=0, description="Maximum bandwidth in bytes (e.g., 1250000 for ~10Mbps)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 9,
                "profile_name": "10M",
                "profile_type": 4,
                "maximum_bandwidth": 1250000
            }
        }


class TcontProfileResponse(BaseModel):
    """Response model for T-CONT profile creation"""
    status: str = Field(..., description="success or error")
    profile_name: str = Field(..., description="Created profile name")
    profile_type: int = Field(..., description="T-CONT type")
    maximum_bandwidth: int = Field(..., description="Maximum bandwidth in bytes")
    message: str = Field(..., description="Status message")
    command_output: Optional[str] = Field(None, description="Raw command output")


class VlanProfileRequest(BaseModel):
    """
    Request model for creating VLAN profile.
    
    Note: For ZTE OLTs, only device_id, profile_name, tag_mode, and cvlan are used.
    svlan and priority may be supported by other manufacturers (e.g., Huawei).
    """
    device_id: int = Field(..., description="OLT device ID")
    profile_name: str = Field(..., min_length=1, max_length=64, description="VLAN profile name (e.g., 'vlan100')")
    tag_mode: Literal['tag', 'untag', 'translate'] = Field(default='tag', description="Tag mode: tag, untag, or translate (default: tag)")
    cvlan: int = Field(..., ge=1, le=4094, description="Customer VLAN ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 9,
                "profile_name": "vlan100",
                "tag_mode": "tag",
                "cvlan": 100
            }
        }


class VlanProfileResponse(BaseModel):
    """Response model for VLAN profile creation"""
    status: str = Field(..., description="success or error")
    profile_name: str = Field(..., description="Created profile name")
    tag_mode: str = Field(..., description="Tag mode")
    cvlan: int = Field(..., description="Customer VLAN")
    message: str = Field(..., description="Status message")
    command_output: Optional[str] = Field(None, description="Raw command output")


class ProfileListResponse(BaseModel):
    """Response model for listing profiles"""
    device_id: int = Field(..., description="OLT device ID")
    device_name: str = Field(..., description="OLT device name")
    manufacturer: str = Field(..., description="OLT manufacturer")
    profile_type: str = Field(..., description="Profile type: tcont or vlan")
    total_profiles: int = Field(..., description="Total number of profiles")
    profiles: List[Dict[str, Any]] = Field(..., description="List of profiles")


class ProfileDeleteResponse(BaseModel):
    """Response model for profile deletion"""
    status: str = Field(..., description="success or error")
    profile_name: str = Field(..., description="Deleted profile name")
    message: str = Field(..., description="Status message")
    command_output: Optional[str] = Field(None, description="Raw command output")


# ============================================================================
# OLT Port Information Schemas
# ============================================================================

class PortStatistics(BaseModel):
    """Port statistics model"""
    input_rate_bps: int = Field(..., description="Input rate in bytes per second")
    input_rate_pps: int = Field(..., description="Input rate in packets per second")
    output_rate_bps: int = Field(..., description="Output rate in bytes per second")
    output_rate_pps: int = Field(..., description="Output rate in packets per second")
    input_bandwidth_percent: float = Field(..., description="Input bandwidth utilization percentage")
    output_bandwidth_percent: float = Field(..., description="Output bandwidth utilization percentage")
    input_packets: int = Field(..., description="Total input packets")
    input_bytes: int = Field(..., description="Total input bytes")
    input_drops: int = Field(..., description="Total input dropped packets")
    output_packets: int = Field(..., description="Total output packets")
    output_bytes: int = Field(..., description="Total output bytes")
    input_unicast: int = Field(..., description="Input unicast packets")
    input_multicast: int = Field(..., description="Input multicast packets")
    input_broadcast: int = Field(..., description="Input broadcast packets")
    crc_errors: int = Field(..., description="CRC/Align errors")


class PortInfoResponse(BaseModel):
    """Response model for OLT port information"""
    board: int = Field(..., description="Board number")
    card: int = Field(..., description="Card number")
    port: int = Field(..., description="Port number")
    interface: str = Field(..., description="Interface name (e.g., gpon-olt_1/1/2)")
    status: str = Field(..., description="Port status: activate or deactivate")
    line_protocol: str = Field(..., description="Line protocol status: up or down")
    description: Optional[str] = Field(None, description="Port description")
    total_onus: int = Field(..., description="Total number of ONUs supported on this port")
    registered_onus: int = Field(..., description="Number of currently registered ONUs")
    channel_num: int = Field(..., description="Number of channels")
    statistics: PortStatistics = Field(..., description="Port statistics")


# ============================================================================
# ONU Registration Schemas
# ============================================================================

class ONURegistrationRequest(BaseModel):
    """Request model for ONU registration"""
    pppoe_user: str = Field(..., description="PPPoe user")
    pppoe_pass: str = Field(..., description="PPPoe key")
    device_id: int = Field(..., description="OLT device ID")
    onu_serial_number: str = Field(..., description="ONU serial number (e.g., MHAR08DF4BD9)")
    onu_type: str = Field("ZTE-F622", description="ONU type/model")
    name: str = Field(..., description="ONU name identifier")
    description: str = Field(..., description="ONU description")
    tcont_profile: str = Field(..., description="T-CONT profile name (e.g., 10M)")
    gemport: int = Field(1, description="GEM port number")
    tcont: int = Field(1, description="T-CONT number")
    service_port: int = Field(1, description="Service port number")
    vport: int = Field(1, description="Virtual port number")
    user_vlan: int = Field(..., description="User VLAN ID")
    vlan: int = Field(..., description="VLAN ID")
    switchport_bind: str = Field("switch_0/1", description="Switch port binding")
    iphost: int = Field(1, description="IP host number")
    dhcp_enable: bool = Field(True, description="Enable DHCP")
    ping_response: bool = Field(True, description="Enable ping response")
    traceroute_response: bool = Field(True, description="Enable traceroute response")
    vlan_port: str = Field("eth_0/1", description="VLAN port identifier")
    mode: str = Field("tag", description="VLAN mode (tag/untag)")

    class Config:
        json_schema_extra = {
            "example": {
                "pppoe_user": "AIS00028",
                "pppoe_pass": "AIS00028",
                "device_id": 9,
                "onu_serial_number": "MHAR08DF4BD9",
                "onu_type": "ZTE-F622",
                "name": "ONU-Customer-001",
                "description": "Customer ABC - Fiber connection",
                "tcont_profile": "10M",
                "gemport": 1,
                "tcont": 1,
                "service_port": 1,
                "vport": 1,
                "user_vlan": 100,
                "vlan": 100,
                "switchport_bind": "switch_0/1",
                "iphost": 1,
                "dhcp_enable": True,
                "ping_response": True,
                "traceroute_response": True,
                "vlan_port": "eth_0/1",
                "mode": "tag"
            }
        }


class ONURegistrationResponse(BaseModel):
    """Response model for ONU registration"""
    status: str = Field(..., description="Registration status: success or error")
    message: str = Field(..., description="Status message")
    onu_id: Optional[int] = Field(None, description="Assigned ONU ID on the port")
    interface: Optional[str] = Field(None, description="Full ONU interface (e.g., gpon-onu_1/1/2:1)")
    serial_number: Optional[str] = Field(None, description="ONU serial number")
    command_outputs: Optional[Dict[str, Any]] = Field(None, description="Command outputs for debugging")


# ============================================================================
# ONU Unregister Offline Schemas
# ============================================================================

class UnregisterOfflineONURequest(BaseModel):
    """Request model for unregistering offline ONUs"""
    device_id: int = Field(..., description="OLT device ID")
    board: int = Field(1, description="Board number")
    card: int = Field(1, description="Card number")
    port: int = Field(..., description="Port number")
    state: str = Field("offline", description="ONU state to filter (e.g., 'offline', 'OffLine', 'LOS', 'DyingGasp')")

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 9,
                "board": 1,
                "card": 1,
                "port": 1,
                "state": "offline"
            }
        }


class UnregisterOfflineONUResponse(BaseModel):
    """Response model for unregistering offline ONUs"""
    status: str = Field(..., description="Unregister status: success or error")
    message: str = Field(..., description="Status message")
    interface: str = Field(..., description="OLT interface (e.g., gpon-olt_1/1/1)")
    offline_onus_found: int = Field(..., description="Number of offline ONUs found")
    onus_unregistered: List[int] = Field(..., description="List of ONU IDs that were unregistered")
    command_outputs: Optional[Dict[str, Any]] = Field(None, description="Command outputs for debugging")


class OltDeviceResponse(BaseModel):
    """Standardized response for OLT list endpoint"""
    id: int = Field(..., description="OLT device ID")
    name: str = Field(..., description="OLT device name")
    manufacturer: str = Field(..., description="OLT manufacturer")
    host: str = Field(..., description="OLT host ip")
    port: int = Field(..., description="OLT port")
    protocol: str = Field(..., description="OLT protocol")
    is_active: bool = Field(..., description="OLT status")
    verify_ssl: bool = Field(..., description="OLT verify ssl")
    timeout: int = Field(..., description="OLT timeout")
    description: str = Field(..., description="OLT description")
    location: str = Field(..., description="OLT locationx")


class OltDeviceListResponse(BaseModel):
    """Schema for list of OLT devices"""
    total: int = Field(..., description="Total number of OLT devices")
    devices: List[OltDeviceResponse] = Field(..., description="List of OLT devices")

    class Config:
        json_schema_extra = {
            "example": {
                "total": 2,
                "users": [
                    {
                        "id": 1,
                        "name": "AM1 2F LAB",
                        "manufacturer": "zte",
                        "host": "10.50.0.3",
                        "port": "23",
                        "protocol": "telnet",
                        "is_active": True,
                        "verify_ssl": True,
                        "timeout": 30,
                        "description": "SBX/TEST",
                        "location": "AM1 2F LAB"
                    }
                ]
            }
        }

