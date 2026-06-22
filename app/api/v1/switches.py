"""
Switch API Endpoints

REST API endpoints for managing switch devices.
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field

from app.database import get_db
from app.models import Device
from app.services.device_factory import DeviceFactory
from app.utils.logging import logger


router = APIRouter(prefix="/switches", tags=["Switches"])


# Pydantic schemas for request/response

class InterfaceResponse(BaseModel):
    """Schema for interface information"""
    name: str
    status: str
    description: Optional[str] = None
    speed: Optional[str] = None
    duplex: Optional[str] = None
    vlan: Optional[str] = None


class VLANResponse(BaseModel):
    """Schema for VLAN information"""
    vlan_id: int
    name: str
    status: Optional[str] = "active"
    ports: Optional[str] = ""


class MACEntry(BaseModel):
    """Schema for MAC address table entry"""
    vlan: int
    mac_address: str
    type: str
    interface: str


class ARPEntry(BaseModel):
    """Schema for ARP table entry"""
    ip_address: str
    mac_address: str
    interface: str
    age: str


class CreateVLANRequest(BaseModel):
    """Schema for creating a VLAN"""
    vlan_id: int = Field(..., ge=1, le=4094, description="VLAN ID (1-4094)")
    name: str = Field(..., min_length=1, max_length=32, description="VLAN name")


class SetInterfaceVLANRequest(BaseModel):
    """Schema for setting interface VLAN"""
    interface: str = Field(..., description="Interface name (e.g., GigabitEthernet0/1)")
    vlan_id: int = Field(..., ge=1, le=4094, description="VLAN ID")
    mode: str = Field("access", description="Port mode: access or trunk")


class SetTrunkVLANsRequest(BaseModel):
    """Schema for setting trunk allowed VLANs"""
    interface: str = Field(..., description="Interface name")
    vlans: List[int] = Field(..., description="List of VLAN IDs to allow on trunk")


class SetInterfaceStatusRequest(BaseModel):
    """Schema for enabling/disabling interface"""
    interface: str = Field(..., description="Interface name")
    enabled: bool = Field(..., description="True to enable, False to disable")


class SetInterfaceDescriptionRequest(BaseModel):
    """Schema for setting interface description"""
    interface: str = Field(..., description="Interface name")
    description: str = Field(..., description="Interface description")


# Endpoints

@router.get("/{device_id}/interfaces", response_model=List[InterfaceResponse])
async def get_switch_interfaces(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all interfaces on the switch
    
    Returns interface status, speed, duplex, VLAN assignment, etc.
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        if device.device_type != 'switch':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device {device_id} is not a switch"
            )
        
        # Get switch adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            interfaces = await adapter.get_interfaces()
            await adapter.disconnect()
            
            return interfaces
        
        except Exception as e:
            logger.error(f"Error getting interfaces from switch {device_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get interfaces: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_switch_interfaces: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/interfaces/{interface}")
async def get_interface_detail(
    device_id: int,
    interface: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific interface
    
    Includes status, configuration, and statistics
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            info = await adapter.get_interface_status(interface)
            stats = await adapter.get_interface_statistics(interface)
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "interface": interface,
                "info": info,
                "statistics": stats
            }
        
        except Exception as e:
            logger.error(f"Error getting interface details: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get interface details: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_interface_detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{device_id}/interfaces/status")
async def set_interface_status(
    device_id: int,
    request: SetInterfaceStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Enable or disable an interface (shutdown/no shutdown)
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.set_interface_status(request.interface, request.enabled)
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": f"Interface {request.interface} {'enabled' if request.enabled else 'disabled'}"
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to set interface status"
                )
        
        except Exception as e:
            logger.error(f"Error setting interface status: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not set interface status: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_interface_status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{device_id}/interfaces/description")
async def set_interface_description(
    device_id: int,
    request: SetInterfaceDescriptionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Set description for an interface
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.set_interface_description(request.interface, request.description)
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": f"Description set for interface {request.interface}"
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to set interface description"
                )
        
        except Exception as e:
            logger.error(f"Error setting interface description: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not set interface description: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_interface_description: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/vlans", response_model=List[VLANResponse])
async def get_switch_vlans(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of configured VLANs on the switch
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            vlans = await adapter.get_vlans()
            await adapter.disconnect()
            
            return vlans
        
        except Exception as e:
            logger.error(f"Error getting VLANs: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get VLANs: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_switch_vlans: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/vlans/{vlan_id}")
async def get_vlan_detail(
    device_id: int,
    vlan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific VLAN
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            vlan_info = await adapter.get_vlan_info(vlan_id)
            await adapter.disconnect()
            
            if not vlan_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"VLAN {vlan_id} not found"
                )
            
            return {
                "status": "success",
                "device_id": device_id,
                "vlan": vlan_info
            }
        
        except Exception as e:
            logger.error(f"Error getting VLAN details: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get VLAN details: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_vlan_detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{device_id}/vlans")
async def create_vlan(
    device_id: int,
    request: CreateVLANRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new VLAN on the switch
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.create_vlan(request.vlan_id, request.name)
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": f"VLAN {request.vlan_id} created with name {request.name}",
                    "vlan_id": request.vlan_id,
                    "name": request.name
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create VLAN"
                )
        
        except Exception as e:
            logger.error(f"Error creating VLAN: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not create VLAN: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_vlan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.delete("/{device_id}/vlans/{vlan_id}")
async def delete_vlan(
    device_id: int,
    vlan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a VLAN from the switch
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.delete_vlan(vlan_id)
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": f"VLAN {vlan_id} deleted"
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete VLAN"
                )
        
        except Exception as e:
            logger.error(f"Error deleting VLAN: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not delete VLAN: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_vlan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{device_id}/interfaces/vlan")
async def set_interface_vlan(
    device_id: int,
    request: SetInterfaceVLANRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Assign interface to a VLAN (access or trunk mode)
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.set_interface_vlan(request.interface, request.vlan_id, request.mode)
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": f"Interface {request.interface} assigned to VLAN {request.vlan_id} in {request.mode} mode"
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to assign interface to VLAN"
                )
        
        except Exception as e:
            logger.error(f"Error setting interface VLAN: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not set interface VLAN: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_interface_vlan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{device_id}/interfaces/trunk-vlans")
async def set_trunk_allowed_vlans(
    device_id: int,
    request: SetTrunkVLANsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Set allowed VLANs on a trunk port
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.set_trunk_allowed_vlans(request.interface, request.vlans)
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": f"Allowed VLANs set on trunk {request.interface}",
                    "vlans": request.vlans
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to set trunk allowed VLANs"
                )
        
        except Exception as e:
            logger.error(f"Error setting trunk allowed VLANs: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not set trunk allowed VLANs: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_trunk_allowed_vlans: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/mac-table", response_model=List[MACEntry])
async def get_mac_table(
    device_id: int,
    vlan: Optional[int] = None,
    interface: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get MAC address table
    
    Optional filters:
    - vlan: Filter by VLAN ID
    - interface: Filter by interface name
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            mac_table = await adapter.get_mac_table(vlan=vlan, interface=interface)
            await adapter.disconnect()
            
            return mac_table
        
        except Exception as e:
            logger.error(f"Error getting MAC table: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get MAC table: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_mac_table: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/arp-table", response_model=List[ARPEntry])
async def get_arp_table(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get ARP table
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            arp_table = await adapter.get_arp_table()
            await adapter.disconnect()
            
            return arp_table
        
        except Exception as e:
            logger.error(f"Error getting ARP table: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get ARP table: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_arp_table: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/config/running")
async def get_running_config(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get running configuration
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            config = await adapter.get_running_config()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "config_type": "running",
                "config": config
            }
        
        except Exception as e:
            logger.error(f"Error getting running config: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get running config: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_running_config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/config/startup")
async def get_startup_config(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get startup configuration
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            config = await adapter.get_startup_config()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "config_type": "startup",
                "config": config
            }
        
        except Exception as e:
            logger.error(f"Error getting startup config: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get startup config: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_startup_config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/{device_id}/config/save")
async def save_config(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Save running configuration to startup (write memory / copy run start)
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            success = await adapter.save_config()
            await adapter.disconnect()
            
            if success:
                return {
                    "status": "success",
                    "message": "Configuration saved to startup"
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save configuration"
                )
        
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not save config: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in save_config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/system/info")
async def get_system_info(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get switch system information (hostname, model, version, uptime, etc.)
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            system_info = await adapter.get_system_info()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "system_info": system_info
            }
        
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get system info: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_system_info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/summary")
async def get_switch_summary(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get switch summary with port statistics and VLAN count
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            port_stats = await adapter.get_port_statistics_summary()
            vlans = await adapter.get_vlans()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "device_name": device.name,
                "port_statistics": port_stats,
                "vlan_count": len(vlans)
            }
        
        except Exception as e:
            logger.error(f"Error getting switch summary: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get switch summary: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_switch_summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


# Discovery Endpoints

@router.get("/{device_id}/discovery/commands")
async def discover_switch_commands(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Discover supported commands on the switch
    
    Tests a predefined list of common switch commands and returns which ones work.
    This is useful for understanding the switch's capabilities and command syntax.
    
    Returns:
    - successful: List of working commands with output sizes
    - failed: List of failed/unsupported commands
    - capabilities: Detected capabilities based on successful commands
    - success_rate: Percentage of successful commands
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        if device.device_type != 'switch':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device {device_id} is not a switch (type: {device.device_type})"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            discovery_results = await adapter.discover_commands()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "device_name": device.name,
                "manufacturer": device.manufacturer,
                "discovery": discovery_results
            }
        
        except Exception as e:
            logger.error(f"Error discovering commands: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not discover commands: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in discover_switch_commands: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/discovery/vlan-mapping")
async def discover_vlan_port_mapping(
    device_id: int,
    include_raw: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Discover VLAN to port mappings on the switch
    
    Returns detailed information about which VLANs are configured and
    which ports are assigned to each VLAN.
    
    Query Parameters:
    - include_raw: Include raw command outputs (default: False)
    
    Returns:
    - vlans: List of VLANs with their assigned ports
    - ports: Detailed port configuration for each interface
    - summary: Quick port-to-VLAN mapping table
    - raw_outputs: Raw command outputs (if include_raw=true)
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        if device.device_type != 'switch':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device {device_id} is not a switch (type: {device.device_type})"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            mapping_results = await adapter.discover_vlan_port_mapping()
            await adapter.disconnect()
            
            # Remove raw outputs if not requested
            if not include_raw and 'raw_outputs' in mapping_results:
                del mapping_results['raw_outputs']
            
            return {
                "status": "success",
                "device_id": device_id,
                "device_name": device.name,
                "manufacturer": device.manufacturer,
                "vlan_mapping": mapping_results
            }
        
        except Exception as e:
            logger.error(f"Error discovering VLAN mapping: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not discover VLAN mapping: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in discover_vlan_port_mapping: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/discovery/capabilities")
async def get_switch_capabilities(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get switch capabilities and features
    
    Returns information about the switch's capabilities, supported features,
    hardware details, and configuration limits.
    
    Returns:
    - manufacturer: Switch manufacturer
    - model: Switch model
    - os_version: Operating system version
    - supported_features: List of supported features
    - port_count: Number of ports
    - vlan_range: Supported VLAN ID range
    - interface_types: Types of interfaces available
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        if device.device_type != 'switch':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device {device_id} is not a switch (type: {device.device_type})"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            capabilities = await adapter.get_switch_capabilities()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "device_id": device_id,
                "device_name": device.name,
                "capabilities": capabilities
            }
        
        except Exception as e:
            logger.error(f"Error getting switch capabilities: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not get switch capabilities: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_switch_capabilities: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/{device_id}/discovery/full")
async def full_switch_discovery(
    device_id: int,
    include_raw: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Perform full switch discovery
    
    Combines all discovery endpoints into one comprehensive report.
    This endpoint runs:
    - Command discovery
    - VLAN port mapping discovery
    - Capabilities detection
    
    Query Parameters:
    - include_raw: Include raw command outputs (default: False)
    
    Returns complete discovery report with all information.
    """
    try:
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        if device.device_type != 'switch':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device {device_id} is not a switch (type: {device.device_type})"
            )
        
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            await adapter.connect()
            
            # Run all discovery methods
            commands = await adapter.discover_commands()
            vlan_mapping = await adapter.discover_vlan_port_mapping()
            capabilities = await adapter.get_switch_capabilities()
            
            await adapter.disconnect()
            
            # Remove raw outputs if not requested
            if not include_raw and 'raw_outputs' in vlan_mapping:
                del vlan_mapping['raw_outputs']
            
            return {
                "status": "success",
                "device_id": device_id,
                "device_name": device.name,
                "manufacturer": device.manufacturer,
                "discovery_report": {
                    "capabilities": capabilities,
                    "command_discovery": commands,
                    "vlan_mapping": vlan_mapping
                }
            }
        
        except Exception as e:
            logger.error(f"Error performing full discovery: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not perform full discovery: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in full_switch_discovery: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
