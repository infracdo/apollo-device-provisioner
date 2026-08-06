"""
OLT API Endpoints

RESTful API endpoints for OLT device operations.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.schemas.olt_schemas import (
    ONUProvisionRequest,
    ONUProvisionResponse,
    ONURemoveRequest,
    ONUStatusResponse,
    OltDeviceResponse,
    OltDeviceListResponse,
    OltMappingCreate,
    OltResponse,
    VLANResponse,
    BoardResponse,
    ONTListResponse,
    UnconfiguredONUListResponse,
    TcontProfileRequest,
    TcontProfileResponse,
    VlanProfileRequest,
    VlanProfileResponse,
    ProfileListResponse,
    ProfileDeleteResponse,
    PortInfoResponse,
    ONURegistrationRequest,
    ONURegistrationResponse,
    UnregisterOfflineONURequest,
    UnregisterOfflineONUResponse
)
from app.services.device_factory import DeviceFactory
from app.utils.logging import logger
from app.utils.ont_mapper import normalize_ont_response, normalize_unconfigured_ont_response
from app.utils.profile_mapper import normalize_profile_list
from app.utils.snmp_onu_checker import SNMPONUChecker
from app.utils.kafka import publish_to_kafka
from app.database import get_db
from app.models import Device, Olt

router = APIRouter(prefix="/olt")


def handle_device_error(e: Exception, context: str, device_id: int = None) -> HTTPException:
    """
    Convert device operation exceptions to appropriate HTTP exceptions.
    
    Args:
        e: The caught exception
        context: Description of what operation failed
        device_id: Optional device ID for logging
        
    Returns:
        HTTPException with appropriate status code and message
    """
    device_info = f"device {device_id}" if device_id else "device"
    
    if isinstance(e, HTTPException):
        return e
    elif isinstance(e, PermissionError):
        logger.error(f"Authentication failed for {device_info}: {str(e)}")
        return HTTPException(
            status_code=401,
            detail=f"Authentication failed - incorrect username/password configured for this device. Please verify the device credentials in the database. Details: {str(e)}"
        )
    elif isinstance(e, ConnectionError):
        logger.error(f"Connection error for {device_info}: {str(e)}")
        return HTTPException(
            status_code=503,
            detail=f"Could not connect to device: {str(e)}"
        )
    elif isinstance(e, TimeoutError):
        logger.error(f"Timeout error for {device_info}: {str(e)}")
        return HTTPException(
            status_code=504,
            detail=f"Device operation timed out: {str(e)}"
        )
    else:
        logger.error(f"{context} for {device_info}: {str(e)}")
        return HTTPException(
            status_code=500,
            detail=f"{context}: {str(e)}"
        )


@router.post("/provision-onu", response_model=ONUProvisionResponse)
async def provision_onu(
    request: ONUProvisionRequest,
    background_tasks: BackgroundTasks
):
    """
    Provision an ONU on OLT device
    
    This endpoint is device-agnostic and works with:
    - Huawei OLT
    - BDCOM OLT
    - ZTE OLT
    - SmartOLT
    """
    try:
        # Get device configuration from database
        # For now, using mock data
        device_config = {
            'id': request.device_id,
            'ip_address': '192.168.1.1',  # Would come from database
            'port': 22,
            'username': 'admin',
            'password': 'admin',
            'manufacturer': 'huawei'  # Would come from database
        }
        
        # Create adapter using factory
        adapter = DeviceFactory.create_olt_adapter(
            manufacturer=device_config['manufacturer'],
            device_config=device_config
        )
        
        # Use async context manager for automatic connection handling
        async with adapter:
            result = await adapter.provision_onu(request.onu_config.model_dump())
        
        return ONUProvisionResponse(**result)
        
    except Exception as e:
        logger.error(f"Error provisioning ONU: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/onu")
async def remove_onu(request: ONURemoveRequest):
    """Remove/unprovision an ONU"""
    try:
        # Similar implementation to provision_onu
        device_config = {
            'id': request.device_id,
            'ip_address': '192.168.1.1',
            'port': 22,
            'username': 'admin',
            'password': 'admin',
            'manufacturer': 'huawei'
        }
        
        adapter = DeviceFactory.create_olt_adapter(
            manufacturer=device_config['manufacturer'],
            device_config=device_config
        )
        
        async with adapter:
            result = await adapter.remove_onu(request.onu_location.model_dump())
        
        return result
        
    except Exception as e:
        logger.error(f"Error removing ONU: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/onu/{device_id}/status", response_model=ONTListResponse)
async def get_onts_status(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all ONUs/ONTs status from an OLT device.
    
    Returns a standardized list of all configured ONUs with their current status,
    signal levels, and other metrics. The response format is consistent across
    all OLT manufacturers (RicherLink, ZTE, Huawei, BDCOM, etc.).
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Get ONTs list from adapter (manufacturer-specific format)
            raw_onts = await adapter.get_onts()
            
            # Normalize each ONT to standardized format
            standardized_onts = [
                normalize_ont_response(device.manufacturer, ont_data)
                for ont_data in raw_onts
            ]
            
            logger.info(f"Retrieved and normalized {len(standardized_onts)} ONUs from device {device.name}")
            
            return ONTListResponse(
                device_id=device_id,
                device_name=device.name,
                manufacturer=device.manufacturer,
                total_onts=len(standardized_onts),
                onts=standardized_onts
            )
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except Exception as e:
        raise handle_device_error(e, "Failed to get ONU status", device_id)


@router.get("/onu/{device_id}/unconfigured", response_model=UnconfiguredONUListResponse)
async def get_unconfigured_onus(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all unconfigured ONUs detected by the OLT.
    
    Returns a standardized list of ONUs that are connected to the OLT but not yet
    provisioned/configured. These are auto-discovered ONUs waiting to be authorized.
    The response format is consistent across all OLT manufacturers (ZTE, RicherLink, 
    Huawei, BDCOM, etc.).
    
    This is useful for:
    - Discovering new ONUs connected to the network
    - Identifying unauthorized ONUs
    - Provisioning workflows where you need to see available ONUs
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Get unconfigured ONUs from adapter (manufacturer-specific format)
            raw_uncfg_onus = await adapter.get_unconfigured_onts()
            
            # Normalize each unconfigured ONU to standardized format
            standardized_uncfg_onus = [
                normalize_unconfigured_ont_response(device.manufacturer, onu_data)
                for onu_data in raw_uncfg_onus
            ]
            
            logger.info(f"Retrieved and normalized {len(standardized_uncfg_onus)} unconfigured ONUs from device {device.name}")
            
            return UnconfiguredONUListResponse(
                device_id=device_id,
                device_name=device.name,
                manufacturer=device.manufacturer,
                total_unconfigured=len(standardized_uncfg_onus),
                unconfigured_onus=standardized_uncfg_onus
            )
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except Exception as e:
        raise handle_device_error(e, "Failed to get unconfigured ONUs", device_id)


@router.post("/onu/{device_id}/{ont_id}/reboot")
async def reboot_onu(device_id: int, ont_id: int, slot: int, port: int):
    """Reboot an ONU"""
    try:
        device_config = {
            'id': device_id,
            'ip_address': '192.168.1.1',
            'port': 22,
            'username': 'admin',
            'password': 'admin',
            'manufacturer': 'huawei'
        }
        
        adapter = DeviceFactory.create_olt_adapter(
            manufacturer=device_config['manufacturer'],
            device_config=device_config
        )
        
        async with adapter:
            result = await adapter.reboot_ont({
                'board': 1,
                'slot': slot,
                'port': port,
                'ont_id': ont_id
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error rebooting ONU: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onu/serial/{sn}/reboot")
async def reboot_any_onu_by_serial(sn: str,
    db: AsyncSession = Depends(get_db)):
    """Reboot an ONU by serial number from any OLT"""
    try:
        # NOTE -- get all devices from db where device_type == 'olt' and loop through them to find the ONU by serial number 
        # TODO -- find more efficient way for scenarios with more than 100 OLTs  
        # Get all OLT devices
        result = await db.execute(
            select(Device).where(Device.device_type.ilike("olt"))
        )
        devices = result.scalars().all()

        if not devices:
            raise HTTPException(
                status_code=404,
                detail="No OLT devices found"
            )

        for device in devices:
            adapter = DeviceFactory.get_adapter(device)
            try:
                connected = await adapter.connect()

                if not connected:
                    logger.warning(
                        "Cannot connect to OLT %s",
                        device.name
                    )
                    continue

                ont_location = await adapter.get_ont_path_by_serial(sn)
                if not ont_location:
                    logger.info(
                        "ONU %s not found on %s",
                        sn,
                        device.name
                    )
                    continue

                board = ont_location["board"]
                slot = ont_location["slot"]
                port = ont_location["port"]
                ont_id = ont_location["ont_id"]

                logger.info("Rebooting ONU %s on gpon-onu_%s/%s/%s:%s (%s)", 
                            sn, board, slot, port, ont_id, device.name)

                result = await adapter.reboot_ont({
                    "board": board,
                    "slot": slot,
                    "port": port,
                    "ont_id": ont_id
                })

                if result['status'] == 'error':
                    raise HTTPException(
                        status_code=500,
                        detail=result['message']
                    )
                return result

            finally:
                if hasattr(adapter, "disconnect"):
                    await adapter.disconnect()

        raise HTTPException(
            status_code=404,
            detail=f"ONU with serial number {sn} not found on any OLT"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error rebooting ONU by serial")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
        

@router.post("/{device_id}/onu/serial/{sn}/reboot")
async def reboot_olt_onu_by_serial(device_id: int, sn: str,
    db: AsyncSession = Depends(get_db)):
    """Reboot an ONU in a specified OLT"""
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            logger.error(f"Device with ID {device_id} not found")
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Verify device is an OLT
        if device.device_type.lower() != 'olt':
            logger.error(f"Device {device_id} is not an OLT")
            raise HTTPException(
                status_code=400,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        adapter = DeviceFactory.get_adapter(device)

        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            ont_location = await adapter.get_ont_path_by_serial(sn)
            if not ont_location:
                raise HTTPException(
                    status_code=404,
                    detail=f"ONU with serial number {sn} not found"
                )
            
            board = ont_location['board']
            slot = ont_location['slot']
            port = ont_location['port']
            ont_id = ont_location['ont_id']

            logger.info(f"Rebooting ONU on gpon-onu_{board}/{slot}/{port}:{ont_id} of OLT device {device.name}")
            
            result = await adapter.reboot_ont({
                'board': board,
                'slot': slot,
                'port': port,
                'ont_id': ont_id
            })
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            return result
        
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rebooting ONU: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vlans/{device_id}", response_model=List[VLANResponse])
async def get_vlans(device_id: int):
    """Get VLANs configured on OLT"""
    # Implementation
    return []


@router.get("/boards/{device_id}", response_model=List[BoardResponse])
async def get_boards(device_id: int):
    """Get board/card information from OLT"""
    # Implementation
    return []


# ============================================================================
# GPON Profile Management Endpoints
# ============================================================================

@router.post("/profiles/tcont", response_model=TcontProfileResponse)
async def create_tcont_profile(
    request: TcontProfileRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a T-CONT (Traffic Container) profile on an OLT device.
    
    T-CONT profiles define bandwidth allocation for ONUs. Different types provide
    different QoS guarantees:
    
    - Type 1 (Fixed): Guaranteed fixed bandwidth
    - Type 2 (Assured): Guaranteed minimum + burst capability
    - Type 3 (Non-Assured): Best effort with no guarantee
    - Type 4 (Best-Effort): Shared bandwidth, no guarantee
    - Type 5 (Mixed): Combination of fixed and assured
    
    **Example ZTE Command Generated:**
    ```
    configure terminal
    gpon
    profile tcont 10M type 4 maximum 102400
    ```
    
    **Bandwidth Calculation:**
    - 1 Mbps ≈ 125,000 bytes
    - 10 Mbps ≈ 1,250,000 bytes (or use 102400 for ~800 Kbps)
    - 100 Mbps ≈ 12,500,000 bytes
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == request.device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {request.device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Create T-CONT profile
            profile_config = {
                'profile_name': request.profile_name,
                'profile_type': request.profile_type,
                'maximum_bandwidth': request.maximum_bandwidth
            }
            
            result = await adapter.create_tcont_profile(profile_config)
            
            logger.info(f"T-CONT profile creation result for device {device.name}: {result['status']}")
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            
            return TcontProfileResponse(**result)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating T-CONT profile for device {request.device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create T-CONT profile: {str(e)}"
        )


@router.post("/profiles/vlan", response_model=VlanProfileResponse)
async def create_vlan_profile(
    request: VlanProfileRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a VLAN profile on an OLT device.
    
    VLAN profiles define how VLAN tagging is handled for ONUs:
    
    - **tag**: Add VLAN tag to untagged traffic
    - **untag**: Remove VLAN tag from tagged traffic
    - **translate**: Change VLAN tag (CVLAN to SVLAN)
    
    **Example ZTE Command Generated:**
    ```
    configure terminal
    gpon
    onu profile vlan vlan100 tag-mode tag cvlan 100
    ```
    
    **Common Use Cases:**
    - Residential broadband: tag mode with customer VLAN
    - Enterprise services: translate mode with CVLAN→SVLAN mapping
    - L2 bridging: untag mode for transparent service
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == request.device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {request.device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Create VLAN profile
            profile_config = {
                'profile_name': request.profile_name,
                'tag_mode': request.tag_mode,
                'cvlan': request.cvlan
            }
            
            result = await adapter.create_vlan_profile(profile_config)
            
            logger.info(f"VLAN profile creation result for device {device.name}: {result['status']}")
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            
            return VlanProfileResponse(**result)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating VLAN profile for device {request.device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create VLAN profile: {str(e)}"
        )


@router.get("/profiles/tcont/{device_id}", response_model=ProfileListResponse)
async def get_tcont_profiles(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all T-CONT profiles configured on an OLT device.
    
    Returns a standardized list of T-CONT profiles with their bandwidth settings.
    Useful for viewing available profiles before provisioning ONUs.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Get T-CONT profiles
            raw_profiles = await adapter.get_tcont_profiles()
            
            # Normalize profiles
            normalized_profiles = normalize_profile_list(
                device.manufacturer,
                'tcont',
                raw_profiles
            )
            
            logger.info(f"Retrieved {len(normalized_profiles)} T-CONT profiles from device {device.name}")
            
            return ProfileListResponse(
                device_id=device_id,
                device_name=device.name,
                manufacturer=device.manufacturer,
                profile_type='tcont',
                total_profiles=len(normalized_profiles),
                profiles=normalized_profiles
            )
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting T-CONT profiles for device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get T-CONT profiles: {str(e)}"
        )


@router.get("/profiles/vlan/{device_id}", response_model=ProfileListResponse)
async def get_vlan_profiles(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all VLAN profiles configured on an OLT device.
    
    Returns a standardized list of VLAN profiles with their tagging settings.
    Useful for viewing available profiles before provisioning ONUs.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Get VLAN profiles
            raw_profiles = await adapter.get_vlan_profiles()
            
            # Normalize profiles
            normalized_profiles = normalize_profile_list(
                device.manufacturer,
                'vlan',
                raw_profiles
            )
            
            logger.info(f"Retrieved {len(normalized_profiles)} VLAN profiles from device {device.name}")
            
            return ProfileListResponse(
                device_id=device_id,
                device_name=device.name,
                manufacturer=device.manufacturer,
                profile_type='vlan',
                total_profiles=len(normalized_profiles),
                profiles=normalized_profiles
            )
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VLAN profiles for device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get VLAN profiles: {str(e)}"
        )


@router.delete("/profiles/tcont/{device_id}/{profile_name}", response_model=ProfileDeleteResponse)
async def delete_tcont_profile(
    device_id: int,
    profile_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a T-CONT profile from an OLT device.
    
    Removes a T-CONT bandwidth profile configuration. This profile must not be
    currently in use by any provisioned ONUs.
    
    **Example ZTE Command Generated:**
    ```
    configure terminal
    gpon
    no profile tcont sampleprofile
    ```
    
    **Warning:** Deleting a profile that is in use by ONUs may cause service disruption.
    Verify the profile is not in use before deletion.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Delete T-CONT profile
            result = await adapter.delete_tcont_profile(profile_name)
            
            logger.info(f"T-CONT profile deletion result for device {device.name}: {result['status']}")
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            
            return ProfileDeleteResponse(**result)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting T-CONT profile for device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete T-CONT profile: {str(e)}"
        )


@router.delete("/profiles/vlan/{device_id}/{profile_name}", response_model=ProfileDeleteResponse)
async def delete_vlan_profile(
    device_id: int,
    profile_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a VLAN profile from an OLT device.
    
    Removes a VLAN profile configuration. This profile must not be currently
    in use by any provisioned ONUs.
    
    **Example ZTE Command Generated:**
    ```
    configure terminal
    gpon
    no onu profile vlan vlan200
    ```
    
    **Warning:** Deleting a profile that is in use by ONUs may cause service disruption.
    Verify the profile is not in use before deletion.
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"Device with ID {device_id} not found"
            )
        
        # Verify it's an OLT device
        if device.device_type != 'olt':
            raise HTTPException(
                status_code=400,
                detail=f"Device {device.name} is not an OLT device (type: {device.device_type})"
            )
        
        # Get adapter
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            connected = await adapter.connect()
            if not connected:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not connect to OLT device {device.name}"
                )
            
            # Delete VLAN profile
            result = await adapter.delete_vlan_profile(profile_name)
            
            logger.info(f"VLAN profile deletion result for device {device.name}: {result['status']}")
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            
            return ProfileDeleteResponse(**result)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting VLAN profile for device {device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete VLAN profile: {str(e)}"
        )


@router.get("/ports/{device_id}/{port}", response_model=PortInfoResponse)
async def get_port_info(
    device_id: int,
    port: int,
    board: int = 1,
    card: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about an OLT PON port.
    
    This endpoint retrieves comprehensive information about a specific GPON port,
    including status, ONU capacity, registration status, and detailed statistics.
    
    Args:
        device_id: Database ID of the OLT device
        port: Port number to query
        board: Board number (default: 1)
        card: Card number (default: 1)
        db: Database session
        
    Returns:
        PortInfoResponse: Port information with status, ONUs, and statistics
        
    Raises:
        HTTPException: 404 if device not found, 400 if not an OLT, 503 if connection fails
        
    Example:
        ```
        GET /api/v1/olt/ports/9/2?board=1&card=1
        
        Response:
        {
            "board": 1,
            "card": 1,
            "port": 2,
            "interface": "gpon-olt_1/1/2",
            "status": "activate",
            "line_protocol": "up",
            "description": "none",
            "total_onus": 128,
            "registered_onus": 0,
            "channel_num": 1,
            "statistics": {
                "input_rate_bps": 223,
                "input_rate_pps": 3,
                "output_rate_bps": 0,
                "output_rate_pps": 0,
                "input_bandwidth_percent": 0.0,
                "output_bandwidth_percent": 0.0,
                "input_packets": 6605,
                "input_bytes": 317040,
                "input_drops": 32,
                "output_packets": 0,
                "output_bytes": 0,
                "input_unicast": 6605,
                "input_multicast": 0,
                "input_broadcast": 0,
                "crc_errors": 32
            }
        }
        ```
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            logger.error(f"Device with ID {device_id} not found")
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Verify device is an OLT
        if device.device_type.lower() != 'olt':
            logger.error(f"Device {device_id} is not an OLT")
            raise HTTPException(
                status_code=400,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        logger.info(f"Getting port information for device {device.name} (ID: {device_id}), port {port}")
        
        # Create device adapter using factory
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            await adapter.connect()
            
            # Build port configuration
            port_config = {
                'board': board,
                'card': card,
                'port': port
            }
            
            # Get port information
            port_info = await adapter.get_port_info(port_config)
            
            logger.info(f"Port information retrieved successfully for device {device.name}, port {port}")
            
            # Check if result contains error
            if 'error' in port_info:
                raise HTTPException(
                    status_code=500,
                    detail=port_info['error']
                )
            
            return PortInfoResponse(**port_info)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting port info for device {device_id}, port {port}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get port information: {str(e)}"
        )


@router.post("/onu/register", response_model=ONURegistrationResponse)
async def register_onu(
    request: ONURegistrationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register and configure an ONU on an OLT port.
    
    This endpoint performs a complete ONU registration process:
    1. Looks up the ONU in the unconfigured list using its serial number to find the port
    2. Finds the next available ONU ID on the specified port
    3. Registers the ONU with its serial number on the OLT interface
    4. Configures ONU settings (name, description, T-CONT, GEM port, service port)
    5. Configures pon-onu-mng settings (service, switchport, IP host, VLAN)
    
    Args:
        request: ONURegistrationRequest with serial number and configuration parameters
        db: Database session
        
    Returns:
        ONURegistrationResponse: Registration result with ONU ID and interface
        
    Raises:
        HTTPException: 404 if device/ONU not found, 400 if not an OLT, 500 if registration fails
        
    Example:
        ```json
        POST /api/v1/olt/onu/register
        {
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
            "dhcp_enable": true,
            "ping_response": true,
            "traceroute_response": true,
            "vlan_port": "eth_0/1",
            "mode": "tag"
        }
        
        Response:
        {
            "status": "success",
            "message": "ONU successfully registered and configured as gpon-onu_1/1/2:1",
            "onu_id": 1,
            "interface": "gpon-onu_1/1/2:1",
            "serial_number": "MHAR08DF4BD9",
            "command_outputs": {...}
        }
        ```
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == request.device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            logger.error(f"Device with ID {request.device_id} not found")
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Verify device is an OLT
        if device.device_type.lower() != 'olt':
            logger.error(f"Device {request.device_id} is not an OLT")
            raise HTTPException(
                status_code=400,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        logger.info(f"Registering ONU {request.onu_serial_number} on device {device.name} (ID: {request.device_id})")
        
        # Create device adapter using factory
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            await adapter.connect()
            
            # Build registration data dictionary (board/card/port will be looked up from unconfigured list)
            registration_data = {
                'pppoe_user': request.pppoe_user,
                'pppoe_pass': request.pppoe_pass,
                'onu_serial_number': request.onu_serial_number,
                'onu_type': request.onu_type,
                'name': request.name,
                'description': request.description,
                'tcont_profile': request.tcont_profile,
                'gemport': request.gemport,
                'tcont': request.tcont,
                'service_port': request.service_port,
                'vport': request.vport,
                'user_vlan': request.user_vlan,
                'vlan': request.vlan,
                'switchport_bind': request.switchport_bind,
                'iphost': request.iphost,
                'dhcp_enable': request.dhcp_enable,
                'ping_response': request.ping_response,
                'traceroute_response': request.traceroute_response,
                'vlan_port': request.vlan_port,
                'mode': request.mode
            }
            
            # Register ONU
            result = await adapter.register_onu(registration_data)
            
            logger.info(f"ONU registration result for device {device.name}: {result['status']}")
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            
            return ONURegistrationResponse(**result)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering ONU for device {request.device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register ONU: {str(e)}"
        )


@router.delete("/onu/offline", response_model=UnregisterOfflineONUResponse)
async def unregister_offline_onus(
    request: UnregisterOfflineONURequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Unregister ONUs matching a specific state from an OLT port.
    
    This endpoint performs:
    1. Checks the specified port for ONUs with the given state
    2. Identifies all ONU IDs that match the state (e.g., 'offline', 'LOS', 'DyingGasp')
    3. Unregisters each matching ONU using 'no onu X' command
    
    This is useful for cleaning up ports with failed/disconnected ONUs
    that need to be removed from the configuration.
    
    Args:
        request: UnregisterOfflineONURequest with device_id, port location, and state filter
        db: Database session
        
    Returns:
        UnregisterOfflineONUResponse: Result with count of unregistered ONUs
        
    Raises:
        HTTPException: 404 if device not found, 400 if not an OLT, 500 if unregister fails
        
    Example:
        ```json
        DELETE /api/v1/olt/onu/offline
        {
            "device_id": 9,
            "board": 1,
            "card": 1,
            "port": 1,
            "state": "offline"
        }
        
        Response:
        {
            "status": "success",
            "message": "Successfully unregistered 3 ONU(s) with state 'offline' from gpon-olt_1/1/1",
            "interface": "gpon-olt_1/1/1",
            "offline_onus_found": 3,
            "onus_unregistered": [1, 2, 3],
            "command_outputs": {...}
        }
        ```
    """
    try:
        # Get device from database
        result = await db.execute(
            select(Device).where(Device.id == request.device_id)
        )
        device = result.scalar_one_or_none()
        
        if not device:
            logger.error(f"Device with ID {request.device_id} not found")
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Verify device is an OLT
        if device.device_type.lower() != 'olt':
            logger.error(f"Device {request.device_id} is not an OLT")
            raise HTTPException(
                status_code=400,
                detail=f"Device is not an OLT (type: {device.device_type})"
            )
        
        logger.info(f"Unregistering ONUs with state '{request.state}' on device {device.name} (ID: {request.device_id}), port {request.board}/{request.card}/{request.port}")
        
        # Create device adapter using factory
        adapter = DeviceFactory.get_adapter(device)
        
        try:
            # Connect to device
            await adapter.connect()
            
            # Build port configuration
            port_config = {
                'board': request.board,
                'card': request.card,
                'port': request.port,
                'state': request.state
            }
            
            # Unregister offline ONUs
            result = await adapter.unregister_offline_onus(port_config)
            
            logger.info(f"Offline ONU unregister result for device {device.name}: {result['status']}")
            
            if result['status'] == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=result['message']
                )
            
            return UnregisterOfflineONUResponse(**result)
            
        finally:
            # Always disconnect
            if hasattr(adapter, 'disconnect'):
                await adapter.disconnect()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unregistering offline ONUs for device {request.device_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unregister offline ONUs: {str(e)}"
        )


@router.post("/check-unconfigured-onus")
async def check_unconfigured_onus(
    device_id: int,
    olt_ip: str = "10.42.3.24",
    snmp_community: str = "devCommunity",
    publish_to_queue: bool = True
):
    """
    Check for unconfigured ONUs via SNMP and optionally publish to Kafka
    
    This endpoint:
    1. Performs SNMP walk on the OLT to discover unconfigured ONUs
    2. Decodes serial numbers, OLT ports, and model information
    3. Publishes each ONU to Kafka topic 'olt_ont_registration' for auto-provisioning
    
    Args:
        device_id: Device ID from database
        olt_ip: OLT IP address (default: 10.42.3.24)
        snmp_community: SNMP community string (default: devCommunity)
        publish_to_queue: Whether to publish ONUs to Kafka (default: True)
    
    Returns:
        Dictionary with unconfigured ONUs list and Kafka publish status
    """
    try:
        logger.info(f"Checking unconfigured ONUs on OLT {olt_ip}")
        
        # Create SNMP checker instance
        checker = SNMPONUChecker(target_ip=olt_ip, community=snmp_community)
        
        # Get unconfigured ONUs
        unconfigured_onus = checker.get_unconfigured_onus()
        
        if not unconfigured_onus:
            logger.info("No unconfigured ONUs found")
            return {
                "success": True,
                "device_id": device_id,
                "olt_ip": olt_ip,
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "unconfigured_count": 0,
                "unconfigured_onus": [],
                "published_count": 0,
                "kafka_published": False
            }
        
        logger.info(f"Found {len(unconfigured_onus)} unconfigured ONUs")
        
        # Publish to Kafka if requested
        published_count = 0
        kafka_errors = []
        
        if publish_to_queue:
            kafka_topic = "olt_ont_registration"
            
            for onu in unconfigured_onus:
                # Prepare Kafka message (same format as snmp-to-kafka-app)
                kafka_message = {
                    "timestamp": datetime.utcnow().isoformat() + 'Z',
                    "source_ip": olt_ip,
                    "event_type": "ont_registration",
                    "ont_data": {
                        "event_type": "ont_registration",
                        "ont_model": onu.get('ont_model'),
                        "ont_serial": onu.get('ont_serial'),
                        "ont_firmware": onu.get('ont_firmware'),
                        "ont_index": onu.get('ont_index'),
                        "olt_port": onu.get('olt_port'),
                        "vendor_id": onu.get('vendor_id'),
                        "device_serial": onu.get('device_serial'),
                        "registration_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "api_check_uncfg"
                    },
                    "trap_oid": "api.manual.check"
                }
                
                # Publish to Kafka
                success = publish_to_kafka(kafka_topic, kafka_message)
                
                if success:
                    published_count += 1
                    logger.info(f"✅ Published ONU {onu['ont_serial']} to Kafka")
                else:
                    error_msg = f"Failed to publish ONU {onu['ont_serial']}"
                    kafka_errors.append(error_msg)
                    logger.error(f"❌ {error_msg}")
        
        # Prepare response
        response = {
            "success": True,
            "device_id": device_id,
            "olt_ip": olt_ip,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "unconfigured_count": len(unconfigured_onus),
            "unconfigured_onus": unconfigured_onus,
            "published_count": published_count,
            "kafka_published": published_count > 0,
            "kafka_topic": "olt_ont_registration" if publish_to_queue else None
        }
        
        if kafka_errors:
            response["kafka_errors"] = kafka_errors
        
        logger.info(
            f"Check complete: {len(unconfigured_onus)} found, "
            f"{published_count} published to Kafka"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error checking unconfigured ONUs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check unconfigured ONUs: {str(e)}"
        )


@router.get("/devices", response_model=OltDeviceListResponse)
async def list_olt_devices(
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    manufacturer: Optional[str] = Query(None, description="Filter by Manufacturer"),
    host: Optional[str] = Query(None, description="Filter by IP address"),
    port: Optional[int] = Query(None, description="Filter by port"),
    protocol: Optional[str] = Query(None, description="Filter by protocol"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    verify_ssl: Optional[bool] = Query(None, description="Filter by ssl status"),
    description: Optional[str] = Query(None, description="Filter by description (partial match)"),
    location: Optional[str] = Query(None, description="Filter by location (partial match)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db)
):
    """
    List OLT devices with optional filters.
    
    **Search filters:**
    - **name**: Partial match (case-insensitive)
    - **manufacturer**: Exact match
    - **host**: Exact match
    - **port**: Exact match
    - **protocol**: Exact match
    - **is_active**: Filter by active/inactive status
    - **verify_ssl**: Filter by ssl status
    - **description**: Partial match (case-insensitive)
    - **location**: Exact match
    
    **Pagination:**
    - **limit**: Maximum results per page (1-1000, default 100)
    - **offset**: Number of results to skip
    """
    try:
        # Build query with filters
        query = select(Device)
        query = query.where(Device.device_type == "olt") # get olt devices
        
        if name:
            query = query.where(Device.name.ilike(f"%{name}%"))
        
        if manufacturer:
            query = query.where(Device.manufacturer == manufacturer)
        
        if host:
            query = query.where(Device.host == host)
        
        if port:
            query = query.where(Device.port == port)
        
        if protocol:
            query = query.where(Device.protocol == protocol)
        
        if is_active is not None:
            query = query.where(Device.is_active == is_active)
        
        if verify_ssl is not None:
            query = query.where(Device.verify_ssl == verify_ssl)
        
        if description:
            query = query.where(Device.description.ilike(f"%{description}%"))
        
        if location:
            query = query.where(Device.location.ilike(f"%{location}%"))
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Get paginated results
        query = query.limit(limit).offset(offset).order_by(Device.id)
        result = await db.execute(query)
        devices = result.scalars().all()
        
        logger.info(f"Listed {len(devices)} OLT devices (total: {total})")
        return OltDeviceListResponse(total=total, devices=devices)
        
    except Exception as e:
        logger.error(f"Error listing PPPoE users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.get("/pppoe-mapping", response_model=List[OltResponse])
async def get_all_olt_mapping(
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all olt-pppoe mapping entries.
    """
    try:
        result = await db.execute(
            select(Olt).order_by(Olt.id)
        )
        olts = result.scalars().all()

        return olts

    except Exception as e:
        logger.error(f"Error fetching OLT mappings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch IP pools: {str(e)}"
        )
    

@router.get(
    "/pppoe-mapping/olt/{olt_id}",
    response_model=List[OltResponse]
)
async def get_olt_mapping_by_id(
    olt_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all Mikrotik mappings for an OLT.
    """

    try:
        result = await db.execute(
            select(Olt)
            .where(Olt.olt_id == olt_id)
            .order_by(Olt.id)
        )

        mappings = result.scalars().all()

        if not mappings:
            raise HTTPException(
                status_code=404,
                detail="No mappings found for this OLT"
            )

        return mappings

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Error fetching OLT mapping {olt_id}: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to fetch OLT mappings"
        )


@router.get(
    "/pppoe-mapping/olt/by-mikrotik/{mikrotik_id}",
    response_model=List[OltDeviceListResponse]
)
async def get_mikrotik_olt_devices(
    mikrotik_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Return all OLT devices mapped to the specified Mikrotik.
    """
    try:
        # Verify Mikrotik exists
        result = await db.execute(
            select(Device).where(
                Device.id == mikrotik_id,
                Device.manufacturer == "mikrotik"
            )
        )
        mikrotik = result.scalar_one_or_none()

        if not mikrotik:
            raise HTTPException(
                status_code=404,
                detail="Mikrotik device not found"
            )

        result = await db.execute(
            select(Device)
            .join(Olt, Olt.olt_id == Device.id)
            .where(
                Olt.mikrotik_id == mikrotik_id,
                Device.device_type == "olt"
            )
            .order_by(Device.id)
        )

        return result.scalars().all()

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Error fetching OLT devices for Mikrotik {mikrotik_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch OLT devices"
        )
    

@router.post(
    "/pppoe-mapping",
    response_model=OltResponse,
    status_code=status.HTTP_201_CREATED
)


async def create_olt_mapping(
    mapping: OltMappingCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create OLT to Mikrotik mapping.
    """

    try:
        # Check OLT exists and is actually an OLT
        olt = await db.execute(
            select(Device).where(
                Device.id == mapping.olt_id,
                Device.device_type == "olt"
            )
        )
        olt = olt.scalar_one_or_none()

        if not olt:
            raise HTTPException(
                status_code=404,
                detail="OLT device not found"
            )

        # Check Mikrotik exists
        mikrotik = await db.execute(
            select(Device).where(
                Device.id == mapping.mikrotik_id,
                Device.manufacturer == "mikrotik"
            )
        )
        mikrotik = mikrotik.scalar_one_or_none()

        if not mikrotik:
            raise HTTPException(
                status_code=404,
                detail="Mikrotik device not found"
            )

        # Check duplicate mapping
        existing = await db.execute(
            select(Olt).where(
                Olt.olt_id == mapping.olt_id,
                Olt.mikrotik_id == mapping.mikrotik_id
            )
        )

        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="OLT mapping already exists"
            )

        new_mapping = Olt(
            olt_id=mapping.olt_id,
            mikrotik_id=mapping.mikrotik_id
        )

        db.add(new_mapping)
        await db.commit()
        await db.refresh(new_mapping)

        return new_mapping

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating OLT mapping: {str(e)}")

        raise HTTPException(
            status_code=500,
            detail="Failed to create OLT mapping"
        )

