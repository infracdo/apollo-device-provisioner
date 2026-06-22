"""
PPPoE User Schemas

Pydantic models for PPPoE user CRUD operations.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PPPoEUserCreate(BaseModel):
    """Schema for creating a PPPoE user"""
    user_name: str = Field(..., description="PPPoE username")
    user_password: str = Field(..., description="PPPoE password")
    nas_ip_address: Optional[str] = Field(None, description="NAS IP address (e.g., 10.42.10.5)")
    service_type: str = Field("Framed-User", description="RADIUS service type")
    framed_protocol: str = Field("PPP", description="Framed protocol")
    framed_ip_address: Optional[str] = Field(None, description="Assigned IP address (e.g., 10.42.10.5)")
    framed_ip_netmask: Optional[str] = Field(None, description="IP netmask (e.g., 255.255.255.255)")
    framed_pool: Optional[str] = Field(None, description="IP pool name (e.g., 'pppoe_pool')")
    mikrotik_rate_limit: str = Field("5M/5M", description="Rate limit (e.g., '20M/20M 25M/25M 10M/10M 60/5')")
    mikrotik_address_list: Optional[str] = Field(None, description="Address list (e.g., 'active-users')")
    mikrotik_group: Optional[str] = Field(None, description="User group (e.g., 'Residential')")
    mikrotik_recv_limit_gigawords: int = Field(0, description="Receive limit in gigawords")
    mikrotik_xmit_limit_gigawords: int = Field(0, description="Transmit limit in gigawords")
    onu_serial_number: Optional[str] = Field(None, description="ONU serial number")
    onu_secondary_serial_number: Optional[str] = Field(None, description="ONU secondary serial number")
    onu_mac_address: Optional[str] = Field(None, description="ONU MAC address")
    onu_olt_ip: Optional[str] = Field(None, description="OLT IP address")
    onu_olt_interface: Optional[str] = Field(None, description="OLT interface")
    onu_olt_deviceid: Optional[int] = Field(None, description="OLT device ID from devices table")
    acs_device_id: Optional[str] = Field(None, description="GenieACS device ID")
    is_active: bool = Field(True, description="User active status")

    class Config:
        json_schema_extra = {
            "example": {
                "user_name": "user001@isp.com",
                "user_password": "securepass123",
                "nas_ip_address": "10.42.10.5",
                "service_type": "Framed-User",
                "framed_protocol": "PPP",
                "framed_ip_address": "10.42.10.100",
                "framed_ip_netmask": "255.255.255.255",
                "framed_pool": "pppoe_pool",
                "mikrotik_rate_limit": "20M/20M 25M/25M 10M/10M 60/5",
                "mikrotik_address_list": "active-users",
                "mikrotik_group": "Residential",
                "mikrotik_recv_limit_gigawords": 10,
                "mikrotik_xmit_limit_gigawords": 10,
                "onu_serial_number": "MHAR08DF4BD9",
                "onu_mac_address": "00:11:22:33:44:55",
                "onu_olt_ip": "10.42.1.1",
                "onu_olt_interface": "gpon-onu_1/1/2:1",
                "acs_device_id": "E007C2-MH80-MHAR08DF4BD9",
                "is_active": True
            }
        }


class PPPoEUserUpdate(BaseModel):
    """Schema for updating a PPPoE user"""
    user_name: Optional[str] = Field(None, description="PPPoE username")
    user_password: Optional[str] = Field(None, description="PPPoE password")
    nas_ip_address: Optional[str] = Field(None, description="NAS IP address")
    service_type: Optional[str] = Field(None, description="RADIUS service type")
    framed_protocol: Optional[str] = Field(None, description="Framed protocol")
    framed_ip_address: Optional[str] = Field(None, description="Assigned IP address")
    framed_ip_netmask: Optional[str] = Field(None, description="IP netmask")
    framed_pool: Optional[str] = Field(None, description="IP pool name")
    mikrotik_rate_limit: Optional[str] = Field(None, description="Rate limit")
    mikrotik_address_list: Optional[str] = Field(None, description="Address list")
    mikrotik_group: Optional[str] = Field(None, description="User group")
    mikrotik_recv_limit_gigawords: Optional[int] = Field(None, description="Receive limit in gigawords")
    mikrotik_xmit_limit_gigawords: Optional[int] = Field(None, description="Transmit limit in gigawords")
    onu_serial_number: Optional[str] = Field(None, description="ONU serial number")
    onu_secondary_serial_number: Optional[str] = Field(None, description="ONU secondary serial number")
    onu_mac_address: Optional[str] = Field(None, description="ONU MAC address")
    onu_olt_ip: Optional[str] = Field(None, description="OLT IP address")
    onu_olt_interface: Optional[str] = Field(None, description="OLT interface")
    onu_olt_deviceid: Optional[int] = Field(None, description="OLT device ID from devices table")
    acs_device_id: Optional[str] = Field(None, description="GenieACS device ID")
    is_active: Optional[bool] = Field(None, description="User active status")

    class Config:
        json_schema_extra = {
            "example": {
                "user_password": "newpassword123",
                "mikrotik_rate_limit": "30M/30M",
                "mikrotik_address_list": "premium-users",
                "is_active": True
            }
        }


class PPPoEUserUpdateONU(BaseModel):
    """Schema for updating only ONU-related attributes"""
    onu_serial_number: Optional[str] = Field(None, description="ONU serial number")
    onu_secondary_serial_number: Optional[str] = Field(None, description="ONU secondary serial number")
    onu_mac_address: Optional[str] = Field(None, description="ONU MAC address")
    onu_olt_ip: Optional[str] = Field(None, description="OLT IP address")
    onu_olt_interface: Optional[str] = Field(None, description="OLT interface")
    onu_olt_deviceid: Optional[int] = Field(None, description="OLT device ID from devices table")
    acs_device_id: Optional[str] = Field(None, description="GenieACS device ID")

    class Config:
        json_schema_extra = {
            "example": {
                "onu_serial_number": "MHAR08DF4BD9",
                "onu_mac_address": "00:11:22:33:44:55",
                "onu_olt_ip": "10.42.1.1",
                "onu_olt_interface": "gpon-onu_1/1/2:1",
                "onu_olt_deviceid": 1,
                "acs_device_id": "E007C2-MH80-MHAR08DF4BD9"
            }
        }


class PPPoEUserResponse(BaseModel):
    """Schema for PPPoE user response"""
    id: int
    user_name: str
    user_password: str
    nas_ip_address: Optional[str]
    service_type: str
    framed_protocol: str
    framed_ip_address: Optional[str]
    framed_ip_netmask: Optional[str]
    framed_pool: Optional[str]
    mikrotik_rate_limit: str
    mikrotik_address_list: Optional[str]
    mikrotik_group: Optional[str]
    mikrotik_recv_limit_gigawords: int
    mikrotik_xmit_limit_gigawords: int
    onu_serial_number: Optional[str]
    onu_secondary_serial_number: Optional[str]
    onu_mac_address: Optional[str]
    onu_olt_ip: Optional[str]
    onu_olt_interface: Optional[str]
    onu_olt_deviceid: Optional[int]
    acs_device_id: Optional[str]
    is_active: bool
    is_overdue: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "user_name": "user001@isp.com",
                "user_password": "securepass123",
                "nas_ip_address": "10.42.10.5",
                "service_type": "Framed-User",
                "framed_protocol": "PPP",
                "framed_ip_address": "10.42.10.100",
                "framed_ip_netmask": "255.255.255.255",
                "framed_pool": "pppoe_pool",
                "mikrotik_rate_limit": "20M/20M 25M/25M 10M/10M 60/5",
                "mikrotik_address_list": "active-users",
                "mikrotik_group": "Residential",
                "mikrotik_recv_limit_gigawords": 10,
                "mikrotik_xmit_limit_gigawords": 10,
                "onu_serial_number": "MHAR08DF4BD9",
                "onu_mac_address": "00:11:22:33:44:55",
                "onu_olt_ip": "10.42.1.1",
                "onu_olt_interface": "gpon-onu_1/1/2:1",
                "acs_device_id": "E007C2-MH80-MHAR08DF4BD9",
                "is_active": True,
                "created_at": "2025-10-27T10:30:00",
                "updated_at": "2025-10-27T14:45:00"
            }
        }


class PPPoEUserListResponse(BaseModel):
    """Schema for list of PPPoE users"""
    total: int = Field(..., description="Total number of users")
    users: List[PPPoEUserResponse] = Field(..., description="List of users")

    class Config:
        json_schema_extra = {
            "example": {
                "total": 2,
                "users": [
                    {
                        "id": 1,
                        "user_name": "user001@isp.com",
                        "user_password": "securepass123",
                        "nas_ip_address": "10.42.10.5",
                        "service_type": "Framed-User",
                        "framed_protocol": "PPP",
                        "mikrotik_rate_limit": "20M/20M",
                        "mikrotik_address_list": "active-users",
                        "mikrotik_group": "Residential",
                        "is_active": True,
                        "created_at": "2025-10-27T10:30:00",
                        "updated_at": "2025-10-27T14:45:00"
                    }
                ]
            }
        }


class PPPoEUserWiFiConfig(BaseModel):
    """Schema for configuring WiFi on user's ONU"""
    wifi_ssid: str = Field(..., description="WiFi SSID to configure", min_length=1, max_length=32)
    wifi_password: str = Field(..., description="WiFi password", min_length=8, max_length=63)

    class Config:
        json_schema_extra = {
            "example": {
                "wifi_ssid": "MyHomeWiFi",
                "wifi_password": "SecurePass123"
            }
        }


class PPPoEUserWiFiConfigResponse(BaseModel):
    """Schema for WiFi configuration response"""
    status: str = Field(..., description="Configuration status")
    message: str = Field(..., description="Status message")
    username: str = Field(..., description="PPPoE username")
    acs_device_id: Optional[str] = Field(None, description="GenieACS device ID")
    wifi_ssid: str = Field(..., description="Configured WiFi SSID")
    kafka_published: bool = Field(..., description="Whether message was published to Kafka")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "WiFi configuration request sent to Kafka",
                "username": "MYB-779",
                "acs_device_id": "E007C2-MH80-MHAR08F6C2D9",
                "wifi_ssid": "MyHomeWiFi",
                "kafka_published": True
            }
        }


class PPPoEUserAdminPasswordChange(BaseModel):
    """Schema for changing admin password on user's ONU"""
    password: str = Field(..., description="New admin password", min_length=4, max_length=63)

    class Config:
        json_schema_extra = {
            "example": {
                "password": "NewAdminPass123"
            }
        }


class PPPoEUserAdminPasswordChangeResponse(BaseModel):
    """Schema for admin password change response"""
    status: str = Field(..., description="Configuration status")
    message: str = Field(..., description="Status message")
    username: str = Field(..., description="PPPoE username")
    acs_device_id: Optional[str] = Field(None, description="GenieACS device ID")
    kafka_published: bool = Field(..., description="Whether message was published to Kafka")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Admin password change request sent to Kafka",
                "username": "MYB-779",
                "acs_device_id": "E007C2-MH80-MHAR08F6C2D9",
                "kafka_published": True
            }
        }
