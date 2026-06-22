"""
Devices API Endpoints

Device management CRUD endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import time

from app.database import get_db
from app.models import Device
from app.schemas.device_schemas import (
    DeviceCreate,
    DeviceUpdate,
    DeviceResponse,
    DeviceDetail,
    ConnectionTestRequest,
    ConnectionTestResponse
)
from app.services.device_factory import DeviceFactory
from app.utils.logging import logger

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    device: DeviceCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new device.
    
    - **name**: Unique device name
    - **manufacturer**: Device manufacturer (huawei, bdcom, zte, smartolt, mikrotik)
    - **device_type**: Type of device (olt, router, switch)
    - **host**: IP address or hostname
    - **port**: Connection port (optional, uses default for protocol)
    - **protocol**: Connection protocol (ssh, telnet, api, snmp)
    - **username**: Login username
    - **password**: Login password (will be stored securely)
    - **enable_password**: Enable/privileged mode password (optional)
    - **api_token**: API token for API-based devices (optional)
    """
    try:
        # Check if device with same name already exists
        result = await db.execute(
            select(Device).where(Device.name == device.name)
        )
        existing_device = result.scalar_one_or_none()
        
        if existing_device:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Device with name '{device.name}' already exists"
            )
        
        # Create new device - manually map fields to ensure enum values are used
        db_device = Device(
            name=device.name,
            manufacturer=device.manufacturer.value if hasattr(device.manufacturer, 'value') else device.manufacturer,
            device_type=device.device_type.value if hasattr(device.device_type, 'value') else device.device_type,
            host=device.host,
            port=device.port,
            protocol=device.protocol.value if hasattr(device.protocol, 'value') else device.protocol,
            username=device.username,
            password=device.password,
            enable_password=device.enable_password,
            api_token=device.api_token,
            is_active=device.is_active,
            verify_ssl=device.verify_ssl,
            timeout=device.timeout,
            description=device.description,
            location=device.location
        )
        db.add(db_device)
        await db.commit()
        await db.refresh(db_device)
        
        logger.info(f"Created device: {db_device.name} (ID: {db_device.id})")
        
        return db_device
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating device: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create device: {str(e)}"
        )


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    skip: int = 0,
    limit: int = 100,
    manufacturer: str = None,
    device_type: str = None,
    is_active: bool = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all devices with optional filtering.
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **manufacturer**: Filter by manufacturer
    - **device_type**: Filter by device type
    - **is_active**: Filter by active status
    """
    try:
        query = select(Device)
        
        # Apply filters
        if manufacturer:
            query = query.where(Device.manufacturer == manufacturer)
        if device_type:
            query = query.where(Device.device_type == device_type)
        if is_active is not None:
            query = query.where(Device.is_active == is_active)
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        devices = result.scalars().all()
        
        return devices
    
    except Exception as e:
        logger.error(f"Error listing devices: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list devices: {str(e)}"
        )


@router.get("/{device_id}", response_model=DeviceDetail)
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific device.
    
    Note: Sensitive fields like passwords are not returned.
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
        
        return device
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get device: {str(e)}"
        )


@router.get("/by-ip/{ip_address:path}", response_model=DeviceDetail)
async def get_device_by_ip(
    ip_address: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a device by its IP address.
    
    - **ip_address**: The IP address or hostname of the device
    
    Note: Sensitive fields like passwords are not returned.
    """
    try:
        result = await db.execute(
            select(Device).where(Device.host == ip_address)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with IP address '{ip_address}' not found"
            )
        
        logger.info(f"Retrieved device by IP: {ip_address} (Device: {device.name}, ID: {device.id})")
        
        return device
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device by IP {ip_address}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get device by IP: {str(e)}"
        )


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    device_update: DeviceUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a device's information.
    
    Only provided fields will be updated.
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
        
        # Update only provided fields
        update_data = device_update.model_dump(exclude_unset=True)
        
        # Check if name is being changed and if it conflicts
        if 'name' in update_data and update_data['name'] != device.name:
            result = await db.execute(
                select(Device).where(Device.name == update_data['name'])
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Device with name '{update_data['name']}' already exists"
                )
        
        for field, value in update_data.items():
            setattr(device, field, value)
        
        await db.commit()
        await db.refresh(device)
        
        logger.info(f"Updated device: {device.name} (ID: {device_id})")
        
        return device
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update device: {str(e)}"
        )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a device.
    
    This is a hard delete and cannot be undone.
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
        
        device_name = device.name
        await db.delete(device)
        await db.commit()
        
        logger.info(f"Deleted device: {device_name} (ID: {device_id})")
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete device: {str(e)}"
        )


@router.post("/{device_id}/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Test connection to a device.
    
    This will attempt to connect to the device and verify credentials
    using the device's stored configuration (host, port, protocol, credentials).
    
    No request body required.
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
        
        start_time = time.time()
        
        try:
            # Get device adapter
            adapter = DeviceFactory.get_adapter(device)
            
            # Test connection
            connected = await adapter.connect()
            
            if connected:
                latency = (time.time() - start_time) * 1000
                
                # Try to get basic device info
                device_info = None
                try:
                    # Try different commands based on device type
                    if device.manufacturer == 'huawei':
                        info_result = await adapter.execute_command("display version")
                    elif device.manufacturer == 'richerlink':
                        info_result = await adapter.execute_command("show version")
                    elif device.manufacturer in ['bdcom', 'zte']:
                        info_result = await adapter.execute_command("show version")
                    elif device.manufacturer == 'smartolt':
                        # SmartOLT uses API, try to get device info via API
                        info_result = "SmartOLT API connection successful"
                    elif device.manufacturer == 'mikrotik':
                        info_result = await adapter.execute_command("/system resource print")
                    else:
                        info_result = "Connection successful"
                    
                    device_info = {"raw_output": info_result[:500]}  # Limit output size
                except Exception as cmd_error:
                    logger.warning(f"Could not get device info: {str(cmd_error)}")
                    device_info = {"note": "Connected but could not retrieve device info"}
                
                await adapter.disconnect()
                
                logger.info(f"Connection test successful for device {device.name}")
                
                return ConnectionTestResponse(
                    status="success",
                    message="Connection successful",
                    latency_ms=round(latency, 2),
                    device_info=device_info
                )
            else:
                elapsed_time = (time.time() - start_time) * 1000
                logger.warning(f"Connection test failed for device {device.name} ({device.host}:{device.port})")
                
                return ConnectionTestResponse(
                    status="down",
                    message=f"Device is unreachable or powered off. Could not connect to {device.host}:{device.port}",
                    latency_ms=round(elapsed_time, 2) if elapsed_time > 0 else None,
                    device_info={
                        "host": device.host,
                        "port": device.port,
                        "protocol": device.protocol,
                        "note": "Connection attempt failed - device may be powered off, network unreachable, or credentials incorrect"
                    }
                )
        
        except TimeoutError:
            elapsed_time = (time.time() - start_time) * 1000
            logger.error(f"Connection timeout for device {device.name} ({device.host}:{device.port})")
            return ConnectionTestResponse(
                status="timeout",
                message=f"Connection timeout. Device at {device.host}:{device.port} did not respond within {elapsed_time/1000:.1f} seconds",
                latency_ms=round(elapsed_time, 2),
                device_info={
                    "host": device.host,
                    "port": device.port,
                    "note": "Device did not respond - may be powered off or network issue"
                }
            )
        except ConnectionRefusedError:
            elapsed_time = (time.time() - start_time) * 1000
            logger.error(f"Connection refused for device {device.name} ({device.host}:{device.port})")
            return ConnectionTestResponse(
                status="down",
                message=f"Connection refused by {device.host}:{device.port}. Device may be powered off or service not running",
                latency_ms=round(elapsed_time, 2),
                device_info={
                    "host": device.host,
                    "port": device.port,
                    "note": "Port is not accepting connections - device may be down"
                }
            )
        except Exception as conn_error:
            elapsed_time = (time.time() - start_time) * 1000
            error_msg = str(conn_error).lower()
            
            # Detect common error scenarios
            if 'timeout' in error_msg or 'timed out' in error_msg:
                status_type = "timeout"
                message = f"Connection timeout to {device.host}:{device.port}. Device may be powered off or unreachable"
            elif 'refused' in error_msg:
                status_type = "down"
                message = f"Connection refused by {device.host}:{device.port}. Device is likely powered off"
            elif 'unreachable' in error_msg or 'no route' in error_msg:
                status_type = "down"
                message = f"Network unreachable. Cannot reach {device.host}:{device.port}"
            else:
                status_type = "failed"
                message = f"Connection failed: {str(conn_error)}"
            
            logger.error(f"Connection test failed for device {device_id}: {str(conn_error)}")
            return ConnectionTestResponse(
                status=status_type,
                message=message,
                latency_ms=round(elapsed_time, 2) if elapsed_time > 0 else None,
                device_info={
                    "host": device.host,
                    "port": device.port,
                    "error": str(conn_error)
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing connection to device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test connection: {str(e)}"
        )


@router.get("/{device_id}/onts")
async def get_device_onts(
    device_id: int,
    port: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of ONTs/ONUs on a device.
    
    Device-agnostic endpoint that works with all OLT manufacturers.
    Currently fully implemented for RicherLink/Corona OLTs.
    
    - **device_id**: Device ID
    - **port**: GPON port number (optional, returns all ONTs if not specified)
    
    Returns list of ONTs with their status, serial numbers, and registration info.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Check if device is an OLT
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        # Get adapter
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"ONT listing not implemented for {device.manufacturer} devices",
                "onts": []
            }
        
        # Connect to device
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            # Check if adapter has get_onts method
            if not hasattr(adapter, 'get_onts'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"ONT listing not implemented for {device.manufacturer} devices",
                    "onts": []
                }
            
            # Get ONTs
            filters = {}
            if port is not None:
                filters['port'] = port
            
            onts = await adapter.get_onts(filters)
            
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "port": port,
                "onts": onts
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ONTs from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ONTs: {str(e)}"
        )


@router.get("/{device_id}/onts/{ont_id}/status")
async def get_ont_status(
    device_id: int,
    ont_id: int,
    port: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed status of a specific ONT.
    
    Device-agnostic endpoint that works with all OLT manufacturers.
    Currently fully implemented for RicherLink/Corona OLTs.
    
    - **device_id**: Device ID
    - **ont_id**: ONT ID
    - **port**: GPON port number (required)
    
    Returns detailed ONT status including optical power levels, statistics, and configuration.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Check if device is an OLT
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        # Get adapter
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"ONT status not implemented for {device.manufacturer} devices"
            }
        
        # Connect to device
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            # Check if adapter has get_ont_status method
            if not hasattr(adapter, 'get_ont_status'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"ONT status not implemented for {device.manufacturer} devices"
                }
            
            # Get ONT status
            ont_location = {
                'port': port,
                'ont_id': ont_id
            }
            
            ont_status = await adapter.get_ont_status(ont_location)
            
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "ont": ont_status
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ONT status from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ONT status: {str(e)}"
        )


@router.get("/{device_id}/onts/discover")
async def discover_onts(
    device_id: int,
    port: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Discover unregistered/unconfigured ONTs on a GPON port.
    
    Device-agnostic endpoint that works with all OLT manufacturers.
    Currently fully implemented for RicherLink/Corona OLTs.
    
    - **device_id**: Device ID
    - **port**: GPON port number (required)
    
    Returns list of discovered but not yet registered ONTs.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Check if device is an OLT
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        # Get adapter
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"ONT discovery not implemented for {device.manufacturer} devices",
                "discovered": []
            }
        
        # Connect to device
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            # Check if adapter has discover_onts method
            if not hasattr(adapter, 'discover_onts'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"ONT discovery not implemented for {device.manufacturer} devices",
                    "discovered": []
                }
            
            # Discover ONTs
            discovered = await adapter.discover_onts(port)
            
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "port": port,
                "discovered": discovered
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering ONTs on device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover ONTs: {str(e)}"
        )


@router.get("/{device_id}/config/running")
async def get_device_running_config(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device running configuration.
    
    Device-agnostic endpoint. Returns the current running configuration
    of the device. Supported for devices with CLI-based configuration.
    
    - **device_id**: Device ID
    
    Returns the raw configuration text.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Get adapter
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"Configuration retrieval not implemented for {device.manufacturer} devices"
            }
        
        # Connect to device
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            # Check if adapter has get_running_config method
            if not hasattr(adapter, 'get_running_config'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"Configuration retrieval not implemented for {device.manufacturer} devices"
                }
            
            # Get running config
            config = await adapter.get_running_config()
            
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "config_type": "running",
                "config": config
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting running config from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get running config: {str(e)}"
        )


@router.get("/{device_id}/config/startup")
async def get_device_startup_config(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device startup/saved configuration.
    
    Device-agnostic endpoint. Returns the saved startup configuration.
    
    - **device_id**: Device ID
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
        
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"Startup config retrieval not implemented for {device.manufacturer} devices"
            }
        
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            if not hasattr(adapter, 'get_startup_config'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"Startup config retrieval not implemented for {device.manufacturer} devices"
                }
            
            config = await adapter.get_startup_config()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "config_type": "startup",
                "config": config
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting startup config from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get startup config: {str(e)}"
        )


@router.get("/{device_id}/interfaces")
async def get_device_interfaces(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device interface information.
    
    Device-agnostic endpoint. Returns list of all interfaces with
    their status, statistics, and configuration.
    
    - **device_id**: Device ID
    
    Returns list of interfaces with name, status, hardware type, MTU, bandwidth, etc.
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
        
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"Interface listing not implemented for {device.manufacturer} devices",
                "interfaces": []
            }
        
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            if not hasattr(adapter, 'get_interfaces'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"Interface listing not implemented for {device.manufacturer} devices",
                    "interfaces": []
                }
            
            interfaces = await adapter.get_interfaces()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "interfaces": interfaces
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting interfaces from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get interfaces: {str(e)}"
        )


@router.get("/{device_id}/vlans")
async def get_device_vlans(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device VLAN configuration.
    
    Device-agnostic endpoint. Returns list of configured VLANs.
    
    - **device_id**: Device ID
    
    Returns list of VLANs with ID, name, and membership information.
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
        
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"VLAN listing not implemented for {device.manufacturer} devices",
                "vlans": []
            }
        
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            if not hasattr(adapter, 'get_vlans'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"VLAN listing not implemented for {device.manufacturer} devices",
                    "vlans": []
                }
            
            vlans = await adapter.get_vlans()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "vlans": vlans
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VLANs from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get VLANs: {str(e)}"
        )


@router.get("/{device_id}/system/memory")
async def get_device_memory(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device memory information.
    
    Device-agnostic endpoint. Returns memory usage statistics.
    
    - **device_id**: Device ID
    
    Returns memory usage percentage, total memory, free memory, etc.
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
        
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"Memory info not implemented for {device.manufacturer} devices"
            }
        
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            if not hasattr(adapter, 'get_memory_info'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"Memory info not implemented for {device.manufacturer} devices"
                }
            
            memory_info = await adapter.get_memory_info()
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "memory": memory_info
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memory info from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory info: {str(e)}"
        )


@router.get("/{device_id}/system/logs")
async def get_device_logs(
    device_id: int,
    lines: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device system logs.
    
    Device-agnostic endpoint. Returns recent system log entries.
    
    - **device_id**: Device ID
    - **lines**: Number of log lines to return (default: 100)
    
    Returns list of log entries.
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
        
        try:
            adapter = DeviceFactory.get_adapter(device)
        except NotImplementedError as e:
            return {
                "status": "not_implemented",
                "manufacturer": device.manufacturer,
                "message": f"System logs not implemented for {device.manufacturer} devices",
                "logs": []
            }
        
        connected = await adapter.connect()
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to device"
            )
        
        try:
            if not hasattr(adapter, 'get_system_logs'):
                await adapter.disconnect()
                return {
                    "status": "not_implemented",
                    "manufacturer": device.manufacturer,
                    "message": f"System logs not implemented for {device.manufacturer} devices",
                    "logs": []
                }
            
            logs = await adapter.get_system_logs(lines)
            await adapter.disconnect()
            
            return {
                "status": "success",
                "manufacturer": device.manufacturer,
                "device_id": device_id,
                "lines_requested": lines,
                "lines_returned": len(logs),
                "logs": logs
            }
        
        except Exception as e:
            await adapter.disconnect()
            raise e
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting logs from device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get logs: {str(e)}"
        )
