"""
Mikrotik API Endpoints

RESTful API endpoints for Mikrotik router operations.
"""
import asyncio
from ipaddress import IPv4Address, IPv4Network

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.database import get_db
from app.models import IPPool
from app.schemas.mikrotik_schemas import (
    IPPoolResponse,
    IPPoolCreate,
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


@router.get("/ip-pool", response_model=List[IPPoolResponse])
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
                "subnet": pool.subnet,
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


@router.get("/ip-pool/next", response_model=IPPoolResponse)
async def get_ip_pool_next(
    mikrotik_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Preview current and next IP (no counter increment).
    """
    try:
        result = await db.execute( 
            select(IPPool).where(IPPool.mikrotik_id == mikrotik_id) # there's only one IP pool for now
        )
        ip_pool = result.scalar_one_or_none() # returned row is [id, mikrotik_id, counter, subnet, updated_at]
        
        if not ip_pool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with mikrotik_id {mikrotik_id} not found"
            )
        current_counter = ip_pool.counter
        next_counter = current_counter + 1
        current_ip  = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, current_counter)
        next_ip = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, next_counter)
        
        
        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "subnet": ip_pool.subnet,
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
    Increment the current counter for IP pool and return the current and next IP.
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
        current_counter = ip_pool.counter
        current_ip = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, current_counter)
        next_counter = current_counter + 1
        next_ip = framed_ip_from_index(ip_pool.start_ip, ip_pool.subnet, next_counter)
        ip_pool.counter = next_counter

        await db.commit()
        await db.refresh(ip_pool)

        logger.info(f"Updated IP pool: {ip_pool.id} (Counter: {ip_pool.counter}, Next IP: {next_ip})")
        
        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "subnet": ip_pool.subnet,
            "counter": ip_pool.counter,
            "current_ip": current_ip,
            "next_ip": next_ip,
            "subnet_mask": cidr_to_netmask(ip_pool.subnet),
            "updated_at": ip_pool.updated_at
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating IP pool: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update IP pool: {str(e)}"
        )


# create new entry in ip pool
@router.post("/ip-pool", response_model=IPPoolResponse) 
async def create_ip_pool(
    payload: IPPoolCreate,
    db: AsyncSession = Depends(get_db)
):
    new_pool = IPPool(
        mikrotik_id=payload.mikrotik_id,
        start_ip=payload.start_ip,
        subnet=payload.subnet,
        counter=payload.counter,
    )

    db.add(new_pool)
    await db.commit()
    await db.refresh(new_pool)

    return new_pool.to_dict()


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
        "subnet": pool.subnet,
        "netmask": netmask
    }
 

def framed_ip_from_index(start_ip: str, subnet: str, index: int) -> str:
    net = IPv4Network(subnet, strict=False)
    start = IPv4Address(start_ip)

    if start not in net:
        raise ValueError("start_ip is not inside subnet")

    start_int = int(start)
    net_end = int(net.broadcast_address)

    target_int = start_int + index

    if target_int > net_end:
        raise HTTPException(status_code=409, detail="IP pool exhausted")

    return str(IPv4Address(target_int))


def cidr_to_netmask(cidr: str) -> str:
    network = IPv4Network(cidr, strict=False)
    return str(network.netmask)