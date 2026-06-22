"""
Database Models

SQLAlchemy models for device provisioning system.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.sql import func
from app.database import Base
import enum

# Import all models
from app.models.accounting import PPPoEAccountingRequest


class DeviceType(str, enum.Enum):
    """Device type enumeration"""
    OLT = "olt"
    ROUTER = "router"
    SWITCH = "switch"


class ConnectionProtocol(str, enum.Enum):
    """Connection protocol enumeration"""
    SSH = "ssh"
    TELNET = "telnet"
    API = "api"
    SNMP = "snmp"


class Device(Base):
    """Device model"""
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    manufacturer = Column(String(100), nullable=False)  # huawei, bdcom, zte, smartolt, mikrotik
    device_type = Column(String(50), nullable=False)  # Using String to avoid enum issues
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=True)
    protocol = Column(String(50), default='ssh')  # Using String to avoid enum issues
    username = Column(String(100), nullable=False)
    password = Column(Text, nullable=False)  # Should be encrypted in production
    enable_password = Column(Text, nullable=True)
    api_token = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    verify_ssl = Column(Boolean, default=True)
    timeout = Column(Integer, default=30)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'manufacturer': self.manufacturer,
            'device_type': self.device_type.value,
            'host': self.host,
            'port': self.port,
            'protocol': self.protocol.value,
            'is_active': self.is_active,
            'description': self.description,
            'location': self.location,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def get_config(self):
        """Get device configuration for adapter"""
        return {
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'enable_password': self.enable_password,
            'protocol': self.protocol.value,
            'api_token': self.api_token,
            'verify_ssl': self.verify_ssl,
            'timeout': self.timeout,
        }


class ONU(Base):
    """ONU model"""
    __tablename__ = "onus"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False)  # Foreign key to devices
    serial_no = Column(String(100), nullable=False, unique=True)
    frame = Column(Integer, default=0)
    slot = Column(Integer, nullable=False)
    port = Column(Integer, nullable=False)
    ont_id = Column(Integer, nullable=False)
    line_profile_id = Column(Integer, nullable=True)
    service_profile_id = Column(Integer, nullable=True)
    vlan = Column(Integer, nullable=True)
    description = Column(String(255), nullable=True)
    wan_mode = Column(String(20), default='dhcp')
    upload_speed = Column(Integer, nullable=True)
    download_speed = Column(Integer, nullable=True)
    status = Column(String(50), default='provisioned')
    provisioned_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=True)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'device_id': self.device_id,
            'serial_no': self.serial_no,
            'frame': self.frame,
            'slot': self.slot,
            'port': self.port,
            'ont_id': self.ont_id,
            'line_profile_id': self.line_profile_id,
            'service_profile_id': self.service_profile_id,
            'vlan': self.vlan,
            'description': self.description,
            'wan_mode': self.wan_mode,
            'upload_speed': self.upload_speed,
            'download_speed': self.download_speed,
            'status': self.status,
            'provisioned_at': self.provisioned_at.isoformat() if self.provisioned_at else None,
        }


class Queue(Base):
    """Queue model for Mikrotik"""
    __tablename__ = "queues"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False)  # Foreign key to devices
    queue_id = Column(String(100), nullable=False)  # RouterOS queue ID
    name = Column(String(255), nullable=False)
    target_ip = Column(String(100), nullable=False)
    upload_kbps = Column(Integer, nullable=False)
    download_kbps = Column(Integer, nullable=False)
    min_upload_kbps = Column(Integer, nullable=True)
    min_download_kbps = Column(Integer, nullable=True)
    priority = Column(Integer, nullable=True)
    parent_queue = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'device_id': self.device_id,
            'queue_id': self.queue_id,
            'name': self.name,
            'target_ip': self.target_ip,
            'upload_kbps': self.upload_kbps,
            'download_kbps': self.download_kbps,
            'min_upload_kbps': self.min_upload_kbps,
            'min_download_kbps': self.min_download_kbps,
            'priority': self.priority,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PPPoEUser(Base):
    """PPPoE User model for RADIUS authentication"""
    __tablename__ = "pppoe_users"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Core RADIUS attributes
    user_name = Column(String(255), nullable=False, unique=True, index=True)
    user_password = Column(String(255), nullable=False)
    nas_ip_address = Column(String(45), nullable=True, index=True)  # IPv4 or IPv6
    
    # Service attributes
    service_type = Column(String(50), default="Framed-User")
    framed_protocol = Column(String(50), default="PPP")
    framed_ip_address = Column(String(45), nullable=True)
    framed_ip_netmask = Column(String(45), nullable=True)
    framed_pool = Column(String(100), nullable=True)
    
    # Mikrotik-specific attributes
    mikrotik_rate_limit = Column(String(100), default="5M/5M")
    mikrotik_address_list = Column(String(100), nullable=True, index=True)
    mikrotik_group = Column(String(100), nullable=True, index=True)
    mikrotik_recv_limit_gigawords = Column(Integer, default=0)
    mikrotik_xmit_limit_gigawords = Column(Integer, default=0)
    
    # ONU-related attributes
    onu_serial_number = Column(String(100), nullable=True)
    onu_secondary_serial_number = Column(String(100), nullable=True)
    onu_mac_address = Column(String(17), nullable=True)
    onu_olt_ip = Column(String(45), nullable=True)
    onu_olt_interface = Column(String(100), nullable=True)
    onu_olt_deviceid = Column(Integer, nullable=True)  # Device ID from devices table
    acs_device_id = Column(String(255), nullable=True, index=True)  # GenieACS device ID
    
    # Metadata
    is_active = Column(Boolean, default=True)
    is_overdue = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'user_name': self.user_name,
            'user_password': self.user_password,
            'nas_ip_address': self.nas_ip_address,
            'service_type': self.service_type,
            'framed_protocol': self.framed_protocol,
            'framed_ip_address': self.framed_ip_address,
            'framed_ip_netmask': self.framed_ip_netmask,
            'framed_pool': self.framed_pool,
            'mikrotik_rate_limit': self.mikrotik_rate_limit,
            'mikrotik_address_list': self.mikrotik_address_list,
            'mikrotik_group': self.mikrotik_group,
            'mikrotik_recv_limit_gigawords': self.mikrotik_recv_limit_gigawords,
            'mikrotik_xmit_limit_gigawords': self.mikrotik_xmit_limit_gigawords,
            'onu_serial_number': self.onu_serial_number,
            'onu_mac_address': self.onu_mac_address,
            'onu_olt_ip': self.onu_olt_ip,
            'onu_olt_interface': self.onu_olt_interface,
            'onu_olt_deviceid': self.onu_olt_deviceid,
            'acs_device_id': self.acs_device_id,
            'is_active': self.is_active,
            'is_overdue': self.is_overdue,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

