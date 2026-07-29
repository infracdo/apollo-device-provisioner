"""
Mikrotik API Endpoints

RESTful API endpoints for Mikrotik router operations.
"""
import asyncio
from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.database import get_db
from app.models import IPPool
from app.schemas.mikrotik_schemas import (
    IPPoolResponse,
    IPPoolCreate,
    IPPoolUpdate,
    QueueCreateRequest,
    QueueUpdateRequest,
    QueueResponse,
    HotspotUserRequest,
    HotspotUserResponse
)
from app.utils.logging import logger

lock = asyncio.Lock()
router = APIRouter(prefix="/mikrotik")


@router.post("/queues", response_model=QueueResponse)
async def create_queue(request: QueueCreateRequest):
    """Create bandwidth queue on Mikrotik"""
    try:
        # Implementation would use MikrotikAdapter
        return QueueResponse(
            status='success',
            queue_id='*1',
            message='Queue created successfully'
        )
    except Exception as e:
        logger.error(f"Error creating queue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/queues/{queue_id}", response_model=QueueResponse)
async def update_queue(queue_id: str, request: QueueUpdateRequest):
    """Update existing queue"""
    try:
        # Implementation
        return QueueResponse(
            status='success',
            queue_id=queue_id,
            message='Queue updated successfully'
        )
    except Exception as e:
        logger.error(f"Error updating queue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/queues/{queue_id}")
async def delete_queue(queue_id: str):
    """Delete queue"""
    try:
        # Implementation
        return {
            'status': 'success',
            'message': 'Queue deleted successfully'
        }
    except Exception as e:
        logger.error(f"Error deleting queue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queues")
async def list_queues(device_id: int):
    """List all queues on device"""
    # Implementation
    return []


@router.post("/hotspot/users", response_model=HotspotUserResponse)
async def create_hotspot_user(request: HotspotUserRequest):
    """Create hotspot user"""
    try:
        # Implementation
        return HotspotUserResponse(
            status='success',
            user_id='*1',
            message='Hotspot user created successfully'
        )
    except Exception as e:
        logger.error(f"Error creating hotspot user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hotspot/users/{username}/disconnect")
async def disconnect_user(username: str):
    """Disconnect active hotspot user"""
    try:
        # Implementation
        return {
            'status': 'success',
            'message': f'User {username} disconnected successfully'
        }
    except Exception as e:
        logger.error(f"Error disconnecting user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ip-pool", response_model=List[IPPoolResponse]) # ok
async def get_all_ip_pools(
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all IP pool entries.
    """
    try:
        result = await db.execute(
            select(IPPool).order_by(IPPool.id)
        )
        ip_pools = result.scalars().all()

        return [
            {
                "id": pool.id,
                "mikrotik_id": pool.mikrotik_id,
                "start_ip": pool.start_ip,
                "subnet": str(pool.subnet),
                "counter": pool.counter,
                "current_ip": framed_ip_from_index(
                    pool.start_ip,
                    pool.subnet,
                    pool.counter
                ),
                "next_ip": framed_ip_from_index(
                    pool.start_ip,
                    pool.subnet,
                    pool.counter + 1
                ),
                "subnet_mask": cidr_to_netmask(pool.subnet),
                "updated_at": pool.updated_at,
            }
            for pool in ip_pools
        ]

    except Exception as e:
        logger.error(f"Error fetching IP pools: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch IP pools: {str(e)}"
        )


@router.get("/ip-pool/next", response_model=IPPoolResponse) # ok
async def get_ip_pool_next(
    mikrotik_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Preview current and next IP (no counter increment).
    """
    try:
        logger.info(f"Fetching IP pool for mikrotik_id: {mikrotik_id}")
        result = await db.execute( 
            select(IPPool).where(IPPool.mikrotik_id == mikrotik_id) # 1 mikrotik id == 1 ip pool entry
        )
        ip_pool = result.scalar_one_or_none() # returned row is [id, mikrotik_id, counter, subnet, updated_at]
        
        if not ip_pool:
            logger.warning(f"IP pool with mikrotik_id {mikrotik_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with mikrotik_id {mikrotik_id} not found"
            )
        logger.info(f"Fetched IP pool: {ip_pool}")
        
        current_counter = ip_pool.counter
        next_counter = current_counter + 1
        current_ip  = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, current_counter)
        
        try:
            next_ip = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, next_counter)
        except HTTPException:
            next_ip = None
        
        logger.info(f"Fetched IP pool: {ip_pool.id} (Counter: {ip_pool.counter}, Current IP: {current_ip}, Next IP: {next_ip})")
        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "start_ip": ip_pool.start_ip,
            "subnet": str(ip_pool.subnet),
            "counter": ip_pool.counter,
            "current_ip": current_ip,
            "next_ip": next_ip,
            "subnet_mask": cidr_to_netmask(ip_pool.subnet),
            "updated_at": ip_pool.updated_at 
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting IP pool: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get IP pool: {str(e)}"
        )


@router.put("/ip-pool/next", response_model=IPPoolResponse)
async def update_ip_pool_next(
    mikrotik_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Allocate current IP and increment counter.
    Counter may point beyond the last usable IP after final allocation.
    The following request will return IP pool exhausted.
    """
    try:
        result = await db.execute( 
            select(IPPool)
            .where(IPPool.mikrotik_id == mikrotik_id)
            .with_for_update()
        )
        ip_pool = result.scalar_one_or_none()
        
        if not ip_pool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with mikrotik_id {mikrotik_id} not found"
            )
        # NOTE - let api return error if current ip returns any error 
        current_ip = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, ip_pool.counter)
        try:
            next_ip = framed_ip_from_index(
                ip_pool.start_ip,
                ip_pool.subnet,
                ip_pool.counter + 1
            )
        except HTTPException:
            next_ip = None
        
        ip_pool.counter += 1

        await db.commit()
        await db.refresh(ip_pool)

        logger.info(f"Updated IP pool: {ip_pool.id} (Counter: {ip_pool.counter}, Next IP: {next_ip})")
        
        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "start_ip": ip_pool.start_ip,
            "subnet": str(ip_pool.subnet),
            "counter": ip_pool.counter,
            "current_ip": current_ip,
            "next_ip": next_ip,
            "subnet_mask": cidr_to_netmask(ip_pool.subnet),
            "updated_at": ip_pool.updated_at
        }
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating IP pool: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update IP pool: {str(e)}"
        )


# create new entry in ip pool
@router.post("/ip-pool", response_model=IPPoolResponse, status_code=status.HTTP_201_CREATED) 
async def create_ip_pool(
    payload: IPPoolCreate,
    db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(
        select(IPPool).where(IPPool.mikrotik_id == payload.mikrotik_id)
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="IP pool already exists."
        )

    subnet = ip_network(payload.subnet, strict=False)
    current_ip = framed_ip_from_index(payload.start_ip, subnet, payload.counter)

    try:
        next_ip = framed_ip_from_index(payload.start_ip, subnet, payload.counter + 1)
    except HTTPException:
        next_ip = None

    new_pool = IPPool(
        mikrotik_id=payload.mikrotik_id,
        start_ip=payload.start_ip,
        subnet=subnet,
        counter=payload.counter,
    )

    db.add(new_pool)
    await db.commit()
    await db.refresh(new_pool)
        
    return {
        "id": new_pool.id,
        "mikrotik_id": new_pool.mikrotik_id,
        "start_ip": new_pool.start_ip,
        "subnet": str(new_pool.subnet),
        "counter": new_pool.counter,
        "current_ip": current_ip,
        "next_ip": next_ip,
        "subnet_mask": cidr_to_netmask(new_pool.subnet),
        "updated_at": new_pool.updated_at,
    }


@router.put("/ip-pool/{mikrotik_id}", response_model=IPPoolResponse)
async def update_ip_pool(
    mikrotik_id: int,
    payload: IPPoolUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing IP pool.
    """
    try:
        result = await db.execute(
            select(IPPool)
            .where(IPPool.mikrotik_id == mikrotik_id)
            .with_for_update()
        )
        ip_pool = result.scalar_one_or_none()

        if not ip_pool:
            logger.warning(f"IP pool with mikrotik_id {mikrotik_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with mikrotik_id {mikrotik_id} not found"
            )

        new_subnet = ip_network(
            payload.subnet,
            strict=False
        )
        new_counter = (
            payload.counter
            if payload.counter is not None
            else ip_pool.counter
        )
        current_ip = framed_ip_from_index(
            payload.start_ip,
            new_subnet,
            new_counter
        )

        try:
            next_ip = framed_ip_from_index(
                payload.start_ip,
                new_subnet,
                new_counter + 1
            )

        except HTTPException:
            next_ip = None

        # Update fields
        ip_pool.start_ip = payload.start_ip
        ip_pool.subnet = new_subnet
        ip_pool.counter = new_counter

        await db.commit()
        await db.refresh(ip_pool)

        logger.info(
            f"Updated IP pool: {ip_pool.id} "
            f"(Counter: {ip_pool.counter}, Current IP: {current_ip}, Next IP: {next_ip})"
        )

        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "start_ip": ip_pool.start_ip,
            "subnet": str(ip_pool.subnet),
            "counter": ip_pool.counter,
            "current_ip": current_ip,
            "next_ip": next_ip,
            "subnet_mask": cidr_to_netmask(ip_pool.subnet),
            "updated_at": ip_pool.updated_at,
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating IP pool: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update IP pool: {str(e)}"
        )

    
@router.delete("/ip-pool/{mikrotik_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ip_pool(
    mikrotik_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete IP pool entry by mikrotik_id.
    """
    try:
        result = await db.execute(
            select(IPPool).where(IPPool.mikrotik_id == mikrotik_id)
        )
        ip_pool = result.scalar_one_or_none()

        if not ip_pool:
            logger.warning(f"IP pool with mikrotik_id {mikrotik_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with mikrotik_id {mikrotik_id} not found"
            )

        await db.delete(ip_pool)
        await db.commit()

        logger.info(f"Deleted IP pool: {ip_pool.id} (mikrotik_id: {mikrotik_id})")

        return None

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting IP pool: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete IP pool: {str(e)}"
        )
    

@router.get("/{id}/netmask")
async def get_subnet_mask(
    id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(IPPool).where(IPPool.id == id)
    )
    pool = result.scalar_one_or_none()

    if not pool:
        raise HTTPException(status_code=404, detail="IP Pool not found")

    if not pool.subnet:
        raise HTTPException(status_code=400, detail="Subnet not set")

    netmask = cidr_to_netmask(pool.subnet)
    return {
        "pool_id": pool.id,
        "subnet": str(pool.subnet),
        "netmask": netmask
    }
 

def framed_ip_from_index(start_ip: str, subnet: str | IPv4Network, index: int) -> str:
    if index < 0:
        raise HTTPException(
            status_code=400,
            detail="index cannot be negative"
        )
    try:
        net = IPv4Network(
            subnet,
            strict=False
        )
        start = IPv4Address(start_ip)

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid IP or subnet"
        )

    if start not in net:
        raise HTTPException(
            status_code=400,
            detail="start_ip is not inside subnet"
        )

    if start == net.network_address:
        raise HTTPException(
            status_code=400,
            detail="Cannot start from network address"
        )


    if start == net.broadcast_address:
        raise HTTPException(
            status_code=400,
            detail="Cannot start from broadcast address"
        )

    target_int = int(start) + index
    if target_int >= int(net.broadcast_address):
        raise HTTPException(status_code=409, detail="IP pool exhausted")

    return str(IPv4Address(target_int))


def cidr_to_netmask(cidr: str) -> str:
    network = IPv4Network(cidr, strict=False)
    return str(network.netmask)