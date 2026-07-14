"""
PPPoE User API Endpoints

CRUD operations for PPPoE user management with RADIUS authentication.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from app.api.v1.mikrotik import cidr_to_netmask, framed_ip_from_index
from app.models import PPPoEUser, Device, IPPool, Olt
from app.schemas.pppoe_schemas import (
    PPPoEUserCreate,
    PPPoEUserUpdate,
    PPPoEUserUpdateONU,
    PPPoEUserResponse,
    PPPoEUserListResponse,
    PPPoEUserWiFiConfig,
    PPPoEUserWiFiConfigResponse,
    PPPoEUserAdminPasswordChange,
    PPPoEUserAdminPasswordChangeResponse
)
from app.database import get_db
from app.utils.kafka import publish_to_kafka
from app.services.radius_coa import RadiusCoA
from app.config import settings
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pppoe",
    tags=["PPPoE Users"]
)


@router.post("/users", response_model=PPPoEUserResponse, status_code=201)
async def create_pppoe_user(
    user_data: PPPoEUserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new PPPoE user.
    
    - **user_name**: Unique username (required)
    - **user_password**: Password for authentication (required)
    - **nas_ip_address**: Network Access Server IP address
    - **service_type**: RADIUS service type (default: Framed-User)
    - **framed_protocol**: Frame protocol (default: PPP)
    - **mikrotik_rate_limit**: Bandwidth limit (default: 5M/5M)
    - **mikrotik_group**: User group (e.g., Residential, Business)
    - **onu_serial_number**: Link to specific ONU
    """
    try:
        # Check if username already exists
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == user_data.user_name)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail=f"Username '{user_data.user_name}' already exists"
            )
        
        # Create new user
        new_user = PPPoEUser(**user_data.model_dump())
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        logger.info(f"Created PPPoE user: {new_user.user_name}")
        return new_user
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating PPPoE user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")


@router.get("/users", response_model=PPPoEUserListResponse)
async def list_pppoe_users(
    username: Optional[str] = Query(None, description="Filter by username (partial match)"),
    nas_ip_address: Optional[str] = Query(None, description="Filter by NAS IP address"),
    address_list: Optional[str] = Query(None, description="Filter by Mikrotik address list"),
    group: Optional[str] = Query(None, description="Filter by Mikrotik group"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db)
):
    """
    List PPPoE users with optional filters.
    
    **Search filters:**
    - **username**: Partial match (case-insensitive)
    - **nas_ip_address**: Exact match
    - **address_list**: Exact match on Mikrotik address list
    - **group**: Exact match on Mikrotik group
    - **is_active**: Filter by active/inactive status
    
    **Pagination:**
    - **limit**: Maximum results per page (1-1000, default 100)
    - **offset**: Number of results to skip
    """
    try:
        # Build query with filters
        query = select(PPPoEUser)
        
        if username:
            query = query.where(PPPoEUser.user_name.ilike(f"%{username}%"))
        
        if nas_ip_address:
            query = query.where(PPPoEUser.nas_ip_address == nas_ip_address)
        
        if address_list:
            query = query.where(PPPoEUser.mikrotik_address_list == address_list)
        
        if group:
            query = query.where(PPPoEUser.mikrotik_group == group)
        
        if is_active is not None:
            query = query.where(PPPoEUser.is_active == is_active)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Get paginated results
        query = query.limit(limit).offset(offset).order_by(PPPoEUser.id)
        result = await db.execute(query)
        users = result.scalars().all()
        
        logger.info(f"Listed {len(users)} PPPoE users (total: {total})")
        return PPPoEUserListResponse(total=total, users=users)
        
    except Exception as e:
        logger.error(f"Error listing PPPoE users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.get("/users/datatable")
async def list_pppoe_users_datatable(
    start: int = Query(0, ge=0, description="DataTables start offset"),
    length: int = Query(25, ge=1, le=1000, description="DataTables page length"),
    search: Optional[str] = Query(None, description="Search term for username and ONU serial"),
    draw: int = Query(1, description="DataTables draw counter"),
    db: AsyncSession = Depends(get_db)
):
    """
    List PPPoE users in DataTables server-side format.
    
    **DataTables Parameters:**
    - **start**: Record offset for pagination
    - **length**: Number of records per page
    - **search**: Search term (filters by username OR ONU serial number, minimum 4 characters)
    - **draw**: Draw counter for DataTables synchronization
    
    **Returns DataTables format:**
    ```json
    {
        "draw": 1,
        "recordsTotal": 100,
        "recordsFiltered": 10,
        "data": [...]
    }
    ```
    """
    try:
        # Build base query
        query = select(PPPoEUser)
        count_query = select(func.count(PPPoEUser.id))
        
        # Get total records (unfiltered)
        total_result = await db.execute(count_query)
        records_total = total_result.scalar()
        
        # Apply search filter if provided (minimum 4 characters)
        # Search in both username and ONU serial number
        if search and len(search.strip()) >= 4:
            search_term = search.strip()
            search_filter = (
                PPPoEUser.user_name.ilike(f"%{search_term}%") |
                PPPoEUser.onu_serial_number.ilike(f"%{search_term}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)
        
        # Get filtered count
        filtered_result = await db.execute(count_query)
        records_filtered = filtered_result.scalar()
        
        # Apply pagination and ordering
        query = query.order_by(PPPoEUser.id).limit(length).offset(start)
        result = await db.execute(query)
        users = result.scalars().all()
        
        # Convert to dict for DataTables
        users_data = [
            {
                "id": user.id,
                "user_name": user.user_name,
                "user_password": user.user_password,
                "nas_ip_address": user.nas_ip_address,
                "service_type": user.service_type,
                "framed_protocol": user.framed_protocol,
                "framed_ip_address": user.framed_ip_address,
                "framed_ip_netmask": user.framed_ip_netmask,
                "framed_pool": user.framed_pool,
                "mikrotik_rate_limit": user.mikrotik_rate_limit,
                "mikrotik_address_list": user.mikrotik_address_list,
                "mikrotik_group": user.mikrotik_group,
                "mikrotik_recv_limit_gigawords": user.mikrotik_recv_limit_gigawords,
                "mikrotik_xmit_limit_gigawords": user.mikrotik_xmit_limit_gigawords,
                "onu_serial_number": user.onu_serial_number,
                "onu_secondary_serial_number": user.onu_secondary_serial_number,
                "onu_mac_address": user.onu_mac_address,
                "onu_olt_ip": user.onu_olt_ip,
                "onu_olt_interface": user.onu_olt_interface,
                "onu_olt_deviceid": user.onu_olt_deviceid,
                "acs_device_id": user.acs_device_id,
                "is_active": user.is_active,
                "is_overdue": user.is_overdue,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None
            }
            for user in users
        ]
        
        logger.info(f"DataTables: returned {len(users_data)} users (filtered: {records_filtered}, total: {records_total})")
        
        return {
            "draw": draw,
            "recordsTotal": records_total,
            "recordsFiltered": records_filtered,
            "data": users_data
        }
        
    except Exception as e:
        logger.error(f"Error fetching DataTables PPPoE users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")


@router.get("/users/{user_id}", response_model=PPPoEUserResponse)
async def get_pppoe_user(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific PPPoE user by ID.
    
    - **user_id**: Database ID of the user
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PPPoE user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.get("/users/by-username/{username}", response_model=PPPoEUserResponse)
async def get_pppoe_user_by_username(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific PPPoE user by username.
    
    - **username**: PPPoE username (e.g., user001@isp.com)
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PPPoE user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.get("/users/by-onu-serial-number/{onu_serial_number}", response_model=PPPoEUserResponse)
async def get_pppoe_user_by_onu_serial(
    onu_serial_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific PPPoE user by ONU serial number.
    
    - **onu_serial_number**: ONU serial number (e.g., MHAR08DF4BD9)
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.onu_serial_number == onu_serial_number)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ONU serial number '{onu_serial_number}' not found")
        
        logger.info(f"Retrieved PPPoE user for ONU serial: {onu_serial_number}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PPPoE user by ONU serial '{onu_serial_number}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.get("/users/by-onu-secondary-serial-number/{onu_secondary_serial_number}", response_model=PPPoEUserResponse)
async def get_pppoe_user_by_onu_secondary_serial(
    onu_secondary_serial_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific PPPoE user by ONU secondary serial number.
    
    - **onu_secondary_serial_number**: ONU secondary serial number (e.g., MHAR08DF4BD9)
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.onu_secondary_serial_number == onu_secondary_serial_number)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ONU secondary serial number '{onu_secondary_serial_number}' not found")
        
        logger.info(f"Retrieved PPPoE user for ONU secondary serial: {onu_secondary_serial_number}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PPPoE user by ONU secondary serial '{onu_secondary_serial_number}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.put("/users/{user_id}", response_model=PPPoEUserResponse)
async def update_pppoe_user(
    user_id: int,
    user_data: PPPoEUserUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a PPPoE user (full update).
    
    - **user_id**: Database ID of the user
    - All fields are optional; only provided fields will be updated
    - If Mikrotik attributes are changed, CoA is automatically triggered
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
        # Store original values for CoA comparison
        original_rate_limit = user.mikrotik_rate_limit
        original_address_list = user.mikrotik_address_list
        original_group = user.mikrotik_group
        
        # Update only provided fields
        update_data = user_data.model_dump(exclude_unset=True)
        
        # Check username uniqueness if changing
        if "user_name" in update_data and update_data["user_name"] != user.user_name:
            username_result = await db.execute(
                select(PPPoEUser).where(PPPoEUser.user_name == update_data["user_name"])
            )
            if username_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"Username '{update_data['user_name']}' already exists"
                )
        
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Updated PPPoE user: {user.user_name}")
        
        # Trigger CoA if Mikrotik attributes changed and CoA is enabled
        coa_result = None
        if settings.RADIUS_COA_ENABLED and user.nas_ip_address:
            # Check if any Mikrotik attributes changed
            mikrotik_changed = (
                (user.mikrotik_rate_limit != original_rate_limit and user.mikrotik_rate_limit is not None) or
                (user.mikrotik_address_list != original_address_list and user.mikrotik_address_list is not None) or
                (user.mikrotik_group != original_group and user.mikrotik_group is not None)
            )
            
            if mikrotik_changed:
                try:
                    # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
                    if ":" in user.nas_ip_address:
                        target_ip, target_port_str = user.nas_ip_address.split(":", 1)
                        target_port = int(target_port_str)
                    else:
                        target_ip = user.nas_ip_address
                        target_port = 3799  # Default CoA port
                    
                    # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
                    nas_ip = "10.99.99.3"
                    
                    logger.info(f"[CoA] Triggering CoA for user {user.user_name}")
                    logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")

                    # Create CoA client with separate target and NAS IPs
                    coa_client = RadiusCoA(
                        nas_ip=nas_ip,
                        nas_port=3799,
                        secret=settings.RADIUS_SECRET,
                        target_ip=target_ip,
                        target_port=target_port
                    )
                    
                    # Send CoA request with changed attributes
                    coa_result = coa_client.change_attributes(
                        username=user.user_name,
                        nas_ip=nas_ip,
                        rate_limit=user.mikrotik_rate_limit if user.mikrotik_rate_limit != original_rate_limit else None,
                        address_list=user.mikrotik_address_list if user.mikrotik_address_list != original_address_list else None,
                        group=user.mikrotik_group if user.mikrotik_group != original_group else None
                    )
                    
                    if coa_result['success']:
                        logger.info(f"[CoA] Successfully applied changes for {user.user_name}")
                    else:
                        logger.warning(f"[CoA] Failed for {user.user_name}: {coa_result['message']}")
                        
                except Exception as coa_error:
                    logger.error(f"[CoA] Error triggering CoA for {user.user_name}: {coa_error}")
                    # Don't fail the entire request if CoA fails
                    coa_result = {'success': False, 'message': str(coa_error)}
        
        # Return user data with CoA result
        response_data = PPPoEUserResponse.model_validate(user)
        response_dict = response_data.model_dump()
        
        # Add CoA information to response
        if coa_result:
            response_dict['coa_applied'] = coa_result['success']
            response_dict['coa_message'] = coa_result['message']
        
        return response_dict
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating PPPoE user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


@router.put("/users/by-username/{username}", response_model=PPPoEUserResponse)
async def update_pppoe_user_by_username(
    username: str,
    user_data: PPPoEUserUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a PPPoE user by username (full update).
    
    - **username**: PPPoE username
    - All fields are optional; only provided fields will be updated
    - If Mikrotik attributes are changed, CoA is automatically triggered
    - If olt device id is present, allow autofill/autogenerate for specific fields
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Store original values for CoA comparison
        original_rate_limit = user.mikrotik_rate_limit
        original_address_list = user.mikrotik_address_list
        original_group = user.mikrotik_group
        original_olt_deviceid = user.onu_olt_deviceid
        
        # Update only provided fields
        update_data = user_data.model_dump(exclude_unset=True)
        
        # Check username uniqueness if changing
        if "user_name" in update_data and update_data["user_name"] != user.user_name:
            username_result = await db.execute(
                select(PPPoEUser).where(PPPoEUser.user_name == update_data["user_name"])
            )
            if username_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"Username '{update_data['user_name']}' already exists"
                )
        
        for field, value in update_data.items():
            setattr(user, field, value)

        olt_changed = (
            "onu_olt_deviceid" in update_data
            and update_data["onu_olt_deviceid"] != original_olt_deviceid
        )

        # if onu_olt_deviceid exists in db and nas_ip_address/framed_ip_address/framed_ip_netmask are null, set nas_ip_address/framed_ip_address/framed_ip_netmask/onu_olt_ip according to onu_olt_deviceid 
        olt_device_id = user.onu_olt_deviceid
        if olt_device_id: 
            # check if olt device exists in db
            device_result = await db.execute(
                select(Device).where(Device.id == olt_device_id)
            )
            olt_device = device_result.scalar_one_or_none()
            if olt_device: # if olt device exists check which fields can be autofilled
                if olt_device.device_type != "olt": #  raise error if device is not an olt
                    raise HTTPException(
                        status_code=400,
                        detail=f"Device {olt_device_id} is not an OLT"
                    )
                # fill onu olt ip if missing or if olt changed
                if olt_changed or not user.onu_olt_ip:
                    user.onu_olt_ip = olt_device.host

                # find pppoe server mapped to the olt
                mapping_result = await db.execute(
                    select(Olt).where(Olt.olt_id == olt_device_id)
                )
                new_mapping = mapping_result.scalar_one_or_none()
                if new_mapping: # if mapping exists, continue
                    mapped_mikrotik_changed = False
                    if olt_changed: # if olt changed, check if mikrotik changed
                        old_mapping_result = await db.execute(
                            select(Olt).where(Olt.olt_id == original_olt_deviceid)
                        )
                        old_mapping = old_mapping_result.scalar_one_or_none()

                        if old_mapping is None:
                            mapped_mikrotik_changed = True
                        else:
                            mapped_mikrotik_changed = (
                                old_mapping.mikrotik_id != new_mapping.mikrotik_id
                            )
                    if mapped_mikrotik_changed or not user.nas_ip_address: # fill nas ip if missing or mikrotik changed
                        mikrotik_result = await db.execute(
                            select(Device).where(Device.id == new_mapping.mikrotik_id)
                        )
                        mikrotik = mikrotik_result.scalar_one_or_none()
                        if not mikrotik: # raise error if mikrotik doesnt exist in device table 
                            raise HTTPException(
                                status_code=400,
                                detail=f"MikroTik device {new_mapping.mikrotik_id} not found"
                            )

                        if mikrotik.manufacturer != "mikrotik": # raise error if device found isnt mikrotik
                            raise HTTPException(
                                status_code=400,
                                detail=f"Device {new_mapping.mikrotik_id} is not a MikroTik device"
                            )

                        port = mikrotik.port or 3799
                        user.nas_ip_address = f"{mikrotik.host}:{port}" # eg. 10.50.1.1:3799

                    pool = None
                    if mapped_mikrotik_changed or not user.framed_ip_address or not user.framed_ip_netmask: # fill framed ip or netmask if missing or if mikrotik changed
                        pool_result = await db.execute(
                            select(IPPool)
                            .where(IPPool.mikrotik_id == new_mapping.mikrotik_id)
                            .with_for_update()
                        )
                        pool = pool_result.scalar_one_or_none()
                        if pool:
                            if mapped_mikrotik_changed or not user.framed_ip_address: # fill framed ip if missing or mikrotik changed
                                current_ip = framed_ip_from_index(
                                    pool.start_ip,
                                    pool.subnet,
                                    pool.counter
                                )

                                pool.counter += 1

                                user.framed_ip_address = current_ip

                            if mapped_mikrotik_changed or not user.framed_ip_netmask: # fill framed netmask if missing or mikrotik changed
                                user.framed_ip_netmask = cidr_to_netmask(pool.subnet)

                            await db.flush()
                        else: # raise error if mikrotik doesnt have ip pool mapping
                            raise HTTPException(
                                status_code=400,
                                detail=f"No IP pool configured for MikroTik {new_mapping.mikrotik_id}"
                            )
                else: # raise error if olt doesnt have pppoe server mapping 
                    raise HTTPException(
                        status_code=400,
                        detail=f"No PPPoE server mapping found for OLT device {olt_device_id}"
                    )
            else: # raise error if olt doesnt exist in devices table
                raise HTTPException(
                    status_code=400,
                    detail=f"OLT device {olt_device_id} not found"
                )
            
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Updated PPPoE user: {user.user_name}")
        
        # Trigger CoA if Mikrotik attributes changed and CoA is enabled
        coa_result = None
        if settings.RADIUS_COA_ENABLED and user.nas_ip_address:
            # Check if any Mikrotik attributes changed
            mikrotik_attr_changed = (
                (user.mikrotik_rate_limit != original_rate_limit and user.mikrotik_rate_limit is not None) or
                (user.mikrotik_address_list != original_address_list and user.mikrotik_address_list is not None) or
                (user.mikrotik_group != original_group and user.mikrotik_group is not None)
            )
            
            if mikrotik_attr_changed:
                try:
                    # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
                    if ":" in user.nas_ip_address:
                        target_ip, target_port_str = user.nas_ip_address.split(":", 1)
                        target_port = int(target_port_str)
                    else:
                        target_ip = user.nas_ip_address
                        target_port = 3799  # Default CoA port
                    
                    # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
                    nas_ip = "10.99.99.3"
                    
                    logger.info(f"[CoA] Triggering CoA for user {user.user_name}")
                    logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")

                    # Create CoA client with separate target and NAS IPs
                    coa_client = RadiusCoA(
                        nas_ip=nas_ip,
                        nas_port=3799,
                        secret=settings.RADIUS_SECRET,
                        target_ip=target_ip,
                        target_port=target_port
                    )
                    
                    # Send CoA request with changed attributes
                    coa_result = coa_client.change_attributes(
                        username=user.user_name,
                        nas_ip=nas_ip,
                        rate_limit=user.mikrotik_rate_limit if user.mikrotik_rate_limit != original_rate_limit else None,
                        address_list=user.mikrotik_address_list if user.mikrotik_address_list != original_address_list else None,
                        group=user.mikrotik_group if user.mikrotik_group != original_group else None
                    )
                    
                    if coa_result['success']:
                        logger.info(f"[CoA] Successfully applied changes for {user.user_name}")
                    else:
                        logger.warning(f"[CoA] Failed for {user.user_name}: {coa_result['message']}")
                        
                except Exception as coa_error:
                    logger.error(f"[CoA] Error triggering CoA for {user.user_name}: {coa_error}")
                    # Don't fail the entire request if CoA fails
                    coa_result = {'success': False, 'message': str(coa_error)}
        
        # Return user data with CoA result
        response_data = PPPoEUserResponse.model_validate(user)
        response_dict = response_data.model_dump()
        
        # Add CoA information to response
        if coa_result:
            response_dict['coa_applied'] = coa_result['success']
            response_dict['coa_message'] = coa_result['message']
        
        return response_dict
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating PPPoE user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


@router.patch("/users/{username}/onu", response_model=PPPoEUserResponse)
async def update_pppoe_user_onu(
    username: str,
    onu_data: PPPoEUserUpdateONU,
    db: AsyncSession = Depends(get_db)
):
    """
    Update ONU-related attributes for a PPPoE user by username.
    
    This endpoint is specifically for updating ONU equipment information
    as part of the provisioning workflow.
    
    - **username**: PPPoE username
    - **onu_serial_number**: ONU serial number
    - **onu_mac_address**: ONU MAC address
    - **onu_olt_ip**: OLT IP address
    - **onu_olt_interface**: OLT interface (e.g., gpon-onu_1/1/2:1)
    - **onu_olt_deviceid**: OLT device identifier from SNMP trap (optional)
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Update only ONU fields
        update_data = onu_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Updated ONU info for PPPoE user: {username}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating ONU info for user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update ONU info: {str(e)}")


@router.delete("/users/{user_id}", status_code=204)
async def delete_pppoe_user(
    user_id: int,
    soft_delete: bool = Query(False, description="Use soft delete (set is_active=False)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a PPPoE user.
    
    - **user_id**: Database ID of the user
    - **soft_delete**: If True, sets is_active=False instead of deleting from database
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
        if soft_delete:
            user.is_active = False
            await db.commit()
            logger.info(f"Soft deleted PPPoE user: {user.user_name}")
        else:
            await db.delete(user)
            await db.commit()
            logger.info(f"Hard deleted PPPoE user: {user.user_name}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting PPPoE user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.delete("/users/by-username/{username}", status_code=204)
async def delete_pppoe_user_by_username(
    username: str,
    soft_delete: bool = Query(False, description="Use soft delete (set is_active=False)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a PPPoE user by username.
    
    - **username**: PPPoE username
    - **soft_delete**: If True, sets is_active=False instead of deleting from database
    """
    try:
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        if soft_delete:
            user.is_active = False
            await db.commit()
            logger.info(f"Soft deleted PPPoE user: {user.user_name}")
        else:
            await db.delete(user)
            await db.commit()
            logger.info(f"Hard deleted PPPoE user: {user.user_name}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting PPPoE user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.post("/users/{username}/configwifi", response_model=PPPoEUserWiFiConfigResponse)
async def configure_wifi(
    username: str,
    wifi_config: PPPoEUserWiFiConfig,
    db: AsyncSession = Depends(get_db)
):
    """
    Configure WiFi settings for a PPPoE user's ONU.
    
    This endpoint publishes a WiFi configuration request to Kafka topic 'genieacs_config'
    which will be processed by the WiFi configuration worker to apply settings via GenieACS.
    
    - **username**: PPPoE username
    - **wifi_ssid**: WiFi SSID to configure (1-32 characters)
    - **wifi_password**: WiFi password (8-63 characters)
    
    Returns:
        Configuration request status and details
    """
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        if not user.acs_device_id:
            raise HTTPException(
                status_code=400, 
                detail=f"User '{username}' does not have an ACS device ID. Please ensure the ONU is registered with GenieACS."
            )
        
        # Prepare Kafka message
        kafka_message = {
            "event": "wifi_config",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "acs_device_id": user.acs_device_id,
            "username": username,
            "serial_number": user.onu_serial_number,
            "wifi_ssid": wifi_config.wifi_ssid,
            "wifi_password": wifi_config.wifi_password,
            "nas_ip_address": user.nas_ip_address,
            "mikrotik_group": user.mikrotik_group
        }
        
        # Publish to Kafka
        kafka_topic = "genieacs_config"
        kafka_published = publish_to_kafka(kafka_topic, kafka_message)
        
        if not kafka_published:
            logger.error(f"Failed to publish WiFi config to Kafka for user: {username}")
            raise HTTPException(
                status_code=500,
                detail="Failed to publish WiFi configuration request to Kafka"
            )
        
        logger.info(f"✅ WiFi configuration request published for user: {username}, SSID: {wifi_config.wifi_ssid}")
        
        return PPPoEUserWiFiConfigResponse(
            status="success",
            message=f"WiFi configuration request sent successfully. SSID: {wifi_config.wifi_ssid}",
            username=username,
            acs_device_id=user.acs_device_id,
            wifi_ssid=wifi_config.wifi_ssid,
            kafka_published=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error configuring WiFi for user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to configure WiFi: {str(e)}")


@router.post("/users/{username}/changeadminpassword", response_model=PPPoEUserAdminPasswordChangeResponse)
async def change_admin_password(
    username: str,
    password_data: PPPoEUserAdminPasswordChange,
    db: AsyncSession = Depends(get_db)
):
    """
    Change admin password on a PPPoE user's ONU.
    
    This endpoint publishes an admin password change request to Kafka topic 'genieacs_config'
    which will be processed by the configuration worker to apply settings via GenieACS.
    
    - **username**: PPPoE username
    - **password**: New admin password (8-63 characters)
    
    Returns:
        Configuration request status and details
    """
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        if not user.acs_device_id:
            raise HTTPException(
                status_code=400, 
                detail=f"User '{username}' does not have an ACS device ID. Please ensure the ONU is registered with GenieACS."
            )
        
        # Prepare Kafka message
        kafka_message = {
            "event": "change_admin_password",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "acs_device_id": user.acs_device_id,
            "username": username,
            "serial_number": user.onu_serial_number,
            "admin_password": password_data.password,
            "nas_ip_address": user.nas_ip_address,
            "mikrotik_group": user.mikrotik_group
        }
        
        # Publish to Kafka
        kafka_topic = "genieacs_config"
        kafka_published = publish_to_kafka(kafka_topic, kafka_message)
        
        if not kafka_published:
            logger.error(f"Failed to publish admin password change to Kafka for user: {username}")
            raise HTTPException(
                status_code=500,
                detail="Failed to publish admin password change request to Kafka"
            )
        
        logger.info(f"✅ Admin password change request published for user: {username}")
        
        return PPPoEUserAdminPasswordChangeResponse(
            status="success",
            message="Admin password change request sent successfully",
            username=username,
            acs_device_id=user.acs_device_id,
            kafka_published=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing admin password for user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to change admin password: {str(e)}")


@router.post("/users/{username}/coa", response_model=Dict[str, Any])
async def trigger_coa(
    username: str,
    rate_limit: Optional[str] = None,
    address_list: Optional[str] = None,
    group: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger RADIUS CoA (Change of Authorization) for a PPPoE user.
    
    This endpoint sends a CoA-Request to the NAS (MikroTik) to update session
    parameters without requiring the user to disconnect and reconnect.
    
    - **username**: PPPoE username
    - **rate_limit**: New bandwidth limit (e.g., "50M/50M") - optional
    - **address_list**: New address list - optional
    - **group**: New user group - optional
    
    At least one attribute must be provided to change.
    
    Returns:
        CoA request status and details
    """
    if not settings.RADIUS_COA_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="RADIUS CoA is disabled in configuration"
        )
    
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        if not user.nas_ip_address:
            raise HTTPException(
                status_code=400,
                detail=f"User '{username}' has no NAS IP address configured"
            )
        
        # Check if at least one attribute is provided
        if not any([rate_limit, address_list, group]):
            raise HTTPException(
                status_code=400,
                detail="At least one attribute (rate_limit, address_list, group) must be provided"
            )
        
        # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
        if ":" in user.nas_ip_address:
            target_ip, target_port_str = user.nas_ip_address.split(":", 1)
            target_port = int(target_port_str)
        else:
            target_ip = user.nas_ip_address
            target_port = 3799  # Default CoA port
        
        # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
        nas_ip = "10.99.99.3"
        
        logger.info(f"[CoA] Manual CoA trigger for user {username}")
        logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")
        
        # Create CoA client
        coa_client = RadiusCoA(
            nas_ip=nas_ip,
            nas_port=3799,
            secret=settings.RADIUS_SECRET,
            target_ip=target_ip,
            target_port=target_port
        )
        
        # Send CoA request
        coa_result = coa_client.change_attributes(
            username=username,
            nas_ip=nas_ip,
            rate_limit=rate_limit,
            address_list=address_list,
            group=group
        )
        
        if coa_result['success']:
            logger.info(f"[CoA] Successfully sent CoA for {username}")
            return {
                "status": "success",
                "message": "CoA request accepted by NAS",
                "username": username,
                "nas_ip": user.nas_ip_address,
                "changes": {
                    "rate_limit": rate_limit,
                    "address_list": address_list,
                    "group": group
                },
                "coa_result": coa_result
            }
        else:
            logger.warning(f"[CoA] CoA rejected for {username}: {coa_result['message']}")
            return {
                "status": "failed",
                "message": coa_result['message'],
                "username": username,
                "nas_ip": user.nas_ip_address,
                "coa_result": coa_result
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering CoA for user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger CoA: {str(e)}")


@router.post("/users/{username}/disconnect", response_model=Dict[str, Any])
async def disconnect_user(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Disconnect a PPPoE user via RADIUS Disconnect-Request.
    
    This endpoint sends a Disconnect-Request to the NAS (MikroTik) to immediately
    terminate the user's active session.
    
    - **username**: PPPoE username
    
    Returns:
        Disconnect request status and details
    """
    if not settings.RADIUS_COA_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="RADIUS CoA is disabled in configuration"
        )
    
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        if not user.nas_ip_address:
            raise HTTPException(
                status_code=400,
                detail=f"User '{username}' has no NAS IP address configured"
            )
        
        # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
        if ":" in user.nas_ip_address:
            target_ip, target_port_str = user.nas_ip_address.split(":", 1)
            target_port = int(target_port_str)
        else:
            target_ip = user.nas_ip_address
            target_port = 3799  # Default CoA port
        
        # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
        nas_ip = "10.99.99.3"
        
        logger.info(f"[CoA] Disconnect request for user {username}")
        logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")
        
        # Create CoA client
        coa_client = RadiusCoA(
            nas_ip=nas_ip,
            nas_port=3799,
            secret=settings.RADIUS_SECRET,
            target_ip=target_ip,
            target_port=target_port
        )
        
        # Send Disconnect request
        disconnect_result = coa_client.disconnect_user(
            username=username,
            nas_ip=nas_ip
        )
        
        if disconnect_result['success']:
            logger.info(f"[CoA] Successfully disconnected {username}")
            return {
                "status": "success",
                "message": "User disconnected successfully",
                "username": username,
                "nas_ip": user.nas_ip_address,
                "disconnect_result": disconnect_result
            }
        else:
            logger.warning(f"[CoA] Disconnect failed for {username}: {disconnect_result['message']}")
            return {
                "status": "failed",
                "message": disconnect_result['message'],
                "username": username,
                "nas_ip": user.nas_ip_address,
                "disconnect_result": disconnect_result
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect user: {str(e)}")


@router.post("/users/{username}/reconnect", response_model=Dict[str, Any])
async def reconnect_user(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Force a PPPoE user to reconnect via RADIUS Disconnect-Request.
    
    This endpoint sends a Disconnect-Request to force the user to disconnect
    and reconnect, which will cause them to pick up any new RADIUS attributes
    (bandwidth limits, address lists, etc.) from the database.
    
    Use this when:
    - CoA is not available or failed
    - You want to ensure fresh authentication
    - Need to apply changes that require reconnection
    
    - **username**: PPPoE username
    
    Returns:
        Reconnect request status and details
    """
    if not settings.RADIUS_COA_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="RADIUS CoA is disabled in configuration"
        )
    
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        if not user.nas_ip_address:
            raise HTTPException(
                status_code=400,
                detail=f"User '{username}' has no NAS IP address configured"
            )
        
        # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
        if ":" in user.nas_ip_address:
            target_ip, target_port_str = user.nas_ip_address.split(":", 1)
            target_port = int(target_port_str)
        else:
            target_ip = user.nas_ip_address
            target_port = 3799  # Default CoA port
        
        # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
        nas_ip = "10.99.99.3"
        
        logger.info(f"[CoA] Reconnect request for user {username}")
        logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")
        
        # Create CoA client
        coa_client = RadiusCoA(
            nas_ip=nas_ip,
            nas_port=3799,
            secret=settings.RADIUS_SECRET,
            target_ip=target_ip,
            target_port=target_port
        )
        
        # Send Disconnect request (user will auto-reconnect)
        disconnect_result = coa_client.disconnect_user(
            username=username,
            nas_ip=nas_ip
        )
        
        if disconnect_result['success']:
            logger.info(f"[CoA] Successfully triggered reconnect for {username}")
            return {
                "status": "success",
                "message": "User will reconnect with updated settings",
                "username": username,
                "nas_ip": user.nas_ip_address,
                "action": "disconnect_for_reconnect",
                "disconnect_result": disconnect_result,
                "note": "User will automatically reconnect and pick up new RADIUS attributes"
            }
        else:
            logger.warning(f"[CoA] Reconnect failed for {username}: {disconnect_result['message']}")
            return {
                "status": "failed",
                "message": disconnect_result['message'],
                "username": username,
                "nas_ip": user.nas_ip_address,
                "action": "disconnect_for_reconnect",
                "disconnect_result": disconnect_result
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reconnecting user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reconnect user: {str(e)}")


@router.post("/users/{username}/activate", response_model=Dict[str, Any])
async def activate_user(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Activate a PPPoE user account.
    
    Sets is_active=True in the database, allowing the user to authenticate.
    The user can immediately connect and will be authenticated by RADIUS.
    
    - **username**: PPPoE username
    
    Returns:
        Activation status and user details
    """
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Check if already active
        if user.is_active:
            logger.info(f"User {username} is already active")
            return {
                "status": "success",
                "message": "User is already active",
                "username": username,
                "is_active": True,
                "was_changed": False
            }
        
        # Activate user
        user.is_active = True
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"✅ Activated user: {username}")
        
        return {
            "status": "success",
            "message": "User activated successfully",
            "username": username,
            "is_active": True,
            "was_changed": True,
            "note": "User can now authenticate and connect"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error activating user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to activate user: {str(e)}")


@router.post("/users/{username}/deactivate", response_model=Dict[str, Any])
async def deactivate_user(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Deactivate a PPPoE user account.
    
    Sets is_active=False in the database and disconnects any active session.
    The user will be immediately disconnected and cannot reconnect until activated.
    
    Use this for:
    - Account suspension (non-payment, violation, etc.)
    - Temporary service hold
    - Before account deletion
    
    - **username**: PPPoE username
    
    Returns:
        Deactivation status, disconnect result, and user details
    """
    try:
        # Get user from database
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Check if already inactive
        was_active = user.is_active
        
        # Deactivate user
        user.is_active = False
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"⏸️  Deactivated user: {username}")
        
        # Attempt to disconnect if user was active and CoA is enabled
        disconnect_result = None
        if was_active and settings.RADIUS_COA_ENABLED and user.nas_ip_address:
            try:
                # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
                if ":" in user.nas_ip_address:
                    target_ip, target_port_str = user.nas_ip_address.split(":", 1)
                    target_port = int(target_port_str)
                else:
                    target_ip = user.nas_ip_address
                    target_port = 3799  # Default CoA port
                
                # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
                nas_ip = "10.99.99.3"
                
                logger.info(f"[CoA] Disconnecting deactivated user {username}")
                logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")
                
                coa_client = RadiusCoA(
                    nas_ip=nas_ip,
                    nas_port=3799,
                    secret=settings.RADIUS_SECRET,
                    target_ip=target_ip,
                    target_port=target_port
                )
                disconnect_result = coa_client.disconnect_user(
                    username=username,
                    nas_ip=nas_ip
                )
                
                if disconnect_result['success']:
                    logger.info(f"[CoA] Successfully disconnected {username}")
                else:
                    logger.warning(f"[CoA] Failed to disconnect {username}: {disconnect_result['message']}")
                    
            except Exception as coa_error:
                logger.error(f"[CoA] Error disconnecting {username}: {coa_error}")
                disconnect_result = {'success': False, 'message': str(coa_error)}
        
        response = {
            "status": "success",
            "message": "User deactivated successfully",
            "username": username,
            "is_active": False,
            "was_active": was_active,
            "was_changed": was_active,
            "note": "User cannot authenticate until reactivated"
        }
        
        # Add disconnect result if attempted
        if disconnect_result:
            response["disconnect_attempted"] = True
            response["disconnect_result"] = disconnect_result
            if disconnect_result['success']:
                response["message"] = "User deactivated and disconnected successfully"
        else:
            response["disconnect_attempted"] = False
            if not settings.RADIUS_COA_ENABLED:
                response["disconnect_reason"] = "CoA disabled"
            elif not user.nas_ip_address:
                response["disconnect_reason"] = "No NAS IP configured"
            elif not was_active:
                response["disconnect_reason"] = "User was already inactive"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deactivating user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to deactivate user: {str(e)}")


@router.post("/users/{username}/mark-overdue")
async def mark_user_overdue(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a PPPoE user as overdue for payment.
    
    This will:
    1. Set is_overdue = True in database
    2. Trigger CoA reconnect to apply captive portal redirect
    3. RADIUS will return Mikrotik-Group="overdue" on next auth
    4. User will be redirected to payment page via captive portal
    
    **Use cases:**
    - User has overdue payment
    - Automatic billing system marks accounts past due
    - Manual suspension for non-payment
    """
    try:
        # Find user
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Check if already overdue
        was_overdue = user.is_overdue
        
        if was_overdue:
            return {
                "status": "success",
                "message": "User is already marked as overdue",
                "username": username,
                "is_overdue": True,
                "was_changed": False,
                "note": "No changes made"
            }
        
        # Mark as overdue
        user.is_overdue = True
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"[Overdue] Marked user '{username}' as overdue")
        
        # Trigger CoA reconnect to apply captive portal
        reconnect_result = None
        if settings.RADIUS_COA_ENABLED and user.nas_ip_address:
            try:
                # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
                if ":" in user.nas_ip_address:
                    target_ip, target_port_str = user.nas_ip_address.split(":", 1)
                    target_port = int(target_port_str)
                else:
                    target_ip = user.nas_ip_address
                    target_port = 3799  # Default CoA port
                
                # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
                nas_ip = "10.99.99.3"
                
                logger.info(f"[CoA] Reconnecting overdue user {username} to apply captive portal")
                logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")
                
                coa_client = RadiusCoA(
                    nas_ip=nas_ip,
                    nas_port=3799,
                    secret=settings.RADIUS_SECRET,
                    target_ip=target_ip,
                    target_port=target_port
                )
                reconnect_result = coa_client.disconnect_user(
                    username=username,
                    nas_ip=nas_ip
                )
                
                if reconnect_result['success']:
                    logger.info(f"[CoA] Successfully triggered reconnect for {username}")
                else:
                    logger.warning(f"[CoA] Failed to reconnect {username}: {reconnect_result['message']}")
                    
            except Exception as coa_error:
                logger.error(f"[CoA] Error reconnecting {username}: {coa_error}")
                reconnect_result = {'success': False, 'message': str(coa_error)}
        
        response = {
            "status": "success",
            "message": "User marked as overdue and will be redirected to captive portal",
            "username": username,
            "is_overdue": True,
            "was_changed": True,
            "note": "User will be redirected to payment page on next authentication"
        }
        
        # Add reconnect result if attempted
        if reconnect_result:
            response["reconnect_attempted"] = True
            response["reconnect_result"] = reconnect_result
            if reconnect_result['success']:
                response["message"] = "User marked as overdue and reconnected to captive portal"
        else:
            response["reconnect_attempted"] = False
            if not settings.RADIUS_COA_ENABLED:
                response["reconnect_reason"] = "CoA disabled - user will get captive portal on next manual reconnect"
            elif not user.nas_ip_address:
                response["reconnect_reason"] = "No NAS IP configured"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error marking user '{username}' as overdue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to mark user as overdue: {str(e)}")


@router.post("/users/{username}/clear-overdue")
async def clear_user_overdue(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Clear overdue status for a PPPoE user (after payment).
    
    This will:
    1. Set is_overdue = False in database
    2. Trigger CoA reconnect to restore normal service
    3. RADIUS will return normal Mikrotik-Group on next auth
    4. User will have normal internet access restored
    
    **Use cases:**
    - Payment received
    - Manual restoration of service
    - Billing system clears overdue flag
    """
    try:
        # Find user
        result = await db.execute(
            select(PPPoEUser).where(PPPoEUser.user_name == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # Check if was overdue
        was_overdue = user.is_overdue
        
        if not was_overdue:
            return {
                "status": "success",
                "message": "User is not marked as overdue",
                "username": username,
                "is_overdue": False,
                "was_changed": False,
                "note": "No changes made"
            }
        
        # Clear overdue status
        user.is_overdue = False
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"[Overdue] Cleared overdue status for user '{username}'")
        
        # Trigger CoA reconnect to restore normal service
        reconnect_result = None
        if settings.RADIUS_COA_ENABLED and user.nas_ip_address:
            try:
                # Parse target IP and port from nas_ip_address (format: "ip:port" or just "ip")
                if ":" in user.nas_ip_address:
                    target_ip, target_port_str = user.nas_ip_address.split(":", 1)
                    target_port = int(target_port_str)
                else:
                    target_ip = user.nas_ip_address
                    target_port = 3799  # Default CoA port
                
                # NAS-IP-Address attribute - actual MikroTik AC Router RADIUS server IP
                nas_ip = "10.99.99.3"
                
                logger.info(f"[CoA] Reconnecting user {username} to restore normal service")
                logger.info(f"[CoA] Target: {target_ip}:{target_port}, NAS-IP-Address: {nas_ip}")
                
                coa_client = RadiusCoA(
                    nas_ip=nas_ip,
                    nas_port=3799,
                    secret=settings.RADIUS_SECRET,
                    target_ip=target_ip,
                    target_port=target_port
                )
                reconnect_result = coa_client.disconnect_user(
                    username=username,
                    nas_ip=nas_ip
                )
                
                if reconnect_result['success']:
                    logger.info(f"[CoA] Successfully triggered reconnect for {username}")
                else:
                    logger.warning(f"[CoA] Failed to reconnect {username}: {reconnect_result['message']}")
                    
            except Exception as coa_error:
                logger.error(f"[CoA] Error reconnecting {username}: {coa_error}")
                reconnect_result = {'success': False, 'message': str(coa_error)}
        
        response = {
            "status": "success",
            "message": "Overdue status cleared and normal service restored",
            "username": username,
            "is_overdue": False,
            "was_changed": True,
            "note": "User will have normal internet access on next authentication"
        }
        
        # Add reconnect result if attempted
        if reconnect_result:
            response["reconnect_attempted"] = True
            response["reconnect_result"] = reconnect_result
            if reconnect_result['success']:
                response["message"] = "Overdue cleared and user reconnected to normal service"
        else:
            response["reconnect_attempted"] = False
            if not settings.RADIUS_COA_ENABLED:
                response["reconnect_reason"] = "CoA disabled - user will get normal service on next manual reconnect"
            elif not user.nas_ip_address:
                response["reconnect_reason"] = "No NAS IP configured"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error clearing overdue status for user '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear overdue status: {str(e)}")

