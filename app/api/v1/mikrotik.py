"""
Mikrotik API Endpoints

RESTful API endpoints for Mikrotik router operations.
"""
from ipaddress import ip_address, IPv4Address, IPv4Network

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.database import get_db
from app.models import IPPool
from app.schemas.mikrotik_schemas import (
    IPPoolResponse,
    QueueCreateRequest,
    QueueUpdateRequest,
    QueueResponse,
    HotspotUserRequest,
    HotspotUserResponse
)
from app.utils.logging import logger

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


def framed_ip(start_ip: str, subnet: str, counter: int) -> str:
    net = IPv4Network(subnet, strict=False)
    hosts = list(net.hosts())
    start = IPv4Address(start_ip)
    if start not in net:
        raise ValueError("start_ip is not inside subnet")

    try:
        start_index = hosts.index(start)
    except ValueError:
        raise ValueError("start_ip is not a usable host address")

    target_index = start_index + counter
    if target_index >= len(hosts):
        raise ValueError("IP pool exhausted")

    return str(hosts[target_index])


@router.get("/ip-pool/next", response_model=IPPoolResponse)
async def get_ip_pool(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get IP pool details.
    - automate framed ip address to auto increment
    """
    try:
        result = await db.execute(
            select(IPPool).where(IPPool.id == 1) # there's only one IP pool for now
        )
        ip_pool = result.scalar_one_or_none() # returned row is [id, mikrotik_id, counter, subnet, updated_at]
        
        if not ip_pool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with ID 1 not found" # update this to use mikrotik_id if needed
            )
        
        next_ip = framed_ip(ip_pool.start_ip, ip_pool.subnet, ip_pool.counter)
        
        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "subnet": ip_pool.subnet,
            "counter": ip_pool.counter,
            "next_ip": next_ip,
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
async def update_ip_pool(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Increment the current counter for IP pool and return the next IP.
    """
    try:
        result = await db.execute(
            select(IPPool)
            .where(IPPool.id == 1)
            .with_for_update()
        )
        ip_pool = result.scalar_one_or_none()
        
        if not ip_pool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"IP pool with ID 1 not found"
            )
        
        ip_pool.counter += 1
        next_ip = framed_ip(ip_pool.start_ip, ip_pool.subnet, ip_pool.counter)

        await db.commit()
        await db.refresh(ip_pool)

        logger.info(f"Updated IP pool: {ip_pool.id} (Counter: {ip_pool.counter}, Next IP: {next_ip})")
        
        return {
            "id": ip_pool.id,
            "mikrotik_id": ip_pool.mikrotik_id,
            "subnet": ip_pool.subnet,
            "counter": ip_pool.counter,
            "next_ip": next_ip,
            "updated_at": ip_pool.updated_at
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating IP pool: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update IP pool: {str(e)}"
        )

