"""
Device Schemas

Pydantic schemas for device management.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DeviceTypeEnum(str, Enum):
    """Device type enumeration"""
    olt = "olt"
    router = "router"
    switch = "switch"


class ConnectionProtocolEnum(str, Enum):
    """Connection protocol enumeration"""
    ssh = "ssh"
    telnet = "telnet"
    api = "api"
    snmp = "snmp"


class Manufacturer(str, Enum):
    """Supported manufacturers"""
    # OLT Manufacturers
    HUAWEI = "huawei"
    BDCOM = "bdcom"
    ZTE = "zte"
    SMARTOLT = "smartolt"
    RICHERLINK = "richerlink"
    # Router Manufacturers
    MIKROTIK = "mikrotik"
    # Switch Manufacturers
    RUIJIE = "ruijie"
    NEXUS = "nexus"
    CISCO_NEXUS = "cisco_nexus"
    ARISTA = "arista"


class DeviceBase(BaseModel):
    """Base device schema"""
    name: str = Field(..., description="Device name (must be unique)", min_length=1, max_length=255)
    manufacturer: Manufacturer = Field(..., description="Device manufacturer")
    device_type: DeviceTypeEnum = Field(..., description="Device type")
    host: str = Field(..., description="Device IP address or hostname", min_length=1, max_length=255)
    port: Optional[int] = Field(None, description="Connection port", ge=1, le=65535)
    protocol: ConnectionProtocolEnum = Field(ConnectionProtocolEnum.ssh, description="Connection protocol")
    username: str = Field(..., description="Login username", min_length=1, max_length=100)
    password: str = Field(..., description="Login password")
    enable_password: Optional[str] = Field(None, description="Enable/privileged mode password")
    api_token: Optional[str] = Field(None, description="API token (for API-based devices)")
    is_active: bool = Field(True, description="Whether the device is active")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")
    timeout: int = Field(30, description="Connection timeout in seconds", ge=1, le=300)
    description: Optional[str] = Field(None, description="Device description")
    location: Optional[str] = Field(None, description="Physical location", max_length=255)


class DeviceCreate(DeviceBase):
    """Schema for creating a device"""
    pass


class DeviceUpdate(BaseModel):
    """Schema for updating a device (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    manufacturer: Optional[Manufacturer] = None
    device_type: Optional[DeviceTypeEnum] = None
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    protocol: Optional[ConnectionProtocolEnum] = None
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = None
    enable_password: Optional[str] = None
    api_token: Optional[str] = None
    is_active: Optional[bool] = None
    verify_ssl: Optional[bool] = None
    timeout: Optional[int] = Field(None, ge=1, le=300)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=255)


class DeviceResponse(BaseModel):
    """Schema for device response"""
    id: int
    name: str
    manufacturer: str
    device_type: str
    host: str
    port: Optional[int]
    protocol: str
    is_active: bool
    description: Optional[str]
    location: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DeviceDetail(DeviceResponse):
    """Schema for detailed device response (includes sensitive data)"""
    username: str
    verify_ssl: bool
    timeout: int
    
    # Note: password, enable_password, and api_token are intentionally excluded
    # from the response for security reasons


class ConnectionTestRequest(BaseModel):
    """Schema for connection test request"""
    protocol: Optional[ConnectionProtocolEnum] = Field(None, description="Override protocol for testing")
    timeout: Optional[int] = Field(None, description="Override timeout for testing", ge=1, le=300)


class ConnectionTestResponse(BaseModel):
    """Schema for connection test response"""
    status: str = Field(..., description="Connection status: success, failed, timeout")
    message: str = Field(..., description="Detailed message")
    latency_ms: Optional[float] = Field(None, description="Connection latency in milliseconds")
    device_info: Optional[dict] = Field(None, description="Additional device information if available")
