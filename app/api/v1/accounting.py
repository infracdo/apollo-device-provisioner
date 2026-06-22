"""
PPPoE Accounting API Endpoints

CRUD operations for PPPoE RADIUS accounting records.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import Optional

from app.database import get_db
from app.models.accounting import PPPoEAccountingRequest
from app.schemas.accounting import (
    PPPoEAccountingRequestCreate,
    PPPoEAccountingRequestResponse,
    PPPoEAccountingRequestList
)

router = APIRouter(prefix="/accounting", tags=["PPPoE Accounting"])


@router.post("/requests", response_model=PPPoEAccountingRequestResponse, status_code=201)
async def create_accounting_request(
    request: PPPoEAccountingRequestCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new PPPoE accounting request record.
    
    This endpoint is typically called by RADIUS server to log accounting events.
    """
    # Create new accounting request
    db_request = PPPoEAccountingRequest(**request.model_dump())
    
    db.add(db_request)
    await db.commit()
    await db.refresh(db_request)
    
    return db_request


@router.get("/requests", response_model=PPPoEAccountingRequestList)
async def list_accounting_requests(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    user_name: Optional[str] = Query(None, description="Filter by username"),
    nas_ip_address: Optional[str] = Query(None, description="Filter by NAS IP address"),
    framed_ip_address: Optional[str] = Query(None, description="Filter by framed IP address"),
    acct_status_type: Optional[str] = Query(None, description="Filter by status type (Start, Stop, Interim-Update)"),
    acct_session_id: Optional[str] = Query(None, description="Filter by session ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of PPPoE accounting requests with pagination and filtering.
    
    Supports filtering by:
    - user_name: PPPoE username
    - nas_ip_address: NAS (router) IP address
    - framed_ip_address: Client's assigned IP address
    - acct_status_type: Accounting status (Start, Stop, Interim-Update)
    - acct_session_id: RADIUS session ID
    """
    # Build query with filters
    query = select(PPPoEAccountingRequest)
    
    # Apply filters
    filters = []
    if user_name:
        filters.append(PPPoEAccountingRequest.user_name == user_name)
    if nas_ip_address:
        filters.append(PPPoEAccountingRequest.nas_ip_address == nas_ip_address)
    if framed_ip_address:
        filters.append(PPPoEAccountingRequest.framed_ip_address == framed_ip_address)
    if acct_status_type:
        filters.append(PPPoEAccountingRequest.acct_status_type == acct_status_type)
    if acct_session_id:
        filters.append(PPPoEAccountingRequest.acct_session_id == acct_session_id)
    
    if filters:
        query = query.where(and_(*filters))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar()
    
    # Apply pagination
    query = query.order_by(PPPoEAccountingRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    items = result.scalars().all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/requests/{request_id}", response_model=PPPoEAccountingRequestResponse)
async def get_accounting_request(
    request_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific accounting request by ID."""
    query = select(PPPoEAccountingRequest).where(PPPoEAccountingRequest.id == request_id)
    result = await db.execute(query)
    db_request = result.scalar_one_or_none()
    
    if not db_request:
        raise HTTPException(status_code=404, detail="Accounting request not found")
    
    return db_request


@router.get("/requests/by-user/{user_name}", response_model=PPPoEAccountingRequestList)
async def get_accounting_by_username(
    user_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all accounting requests for a specific username.
    
    Useful for tracking a user's session history.
    """
    # Build query
    query = select(PPPoEAccountingRequest).where(
        PPPoEAccountingRequest.user_name == user_name
    )
    
    # Get total count
    count_query = select(func.count()).where(
        PPPoEAccountingRequest.user_name == user_name
    )
    result = await db.execute(count_query)
    total = result.scalar()
    
    # Apply pagination
    query = query.order_by(PPPoEAccountingRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    items = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/requests/by-ip/framed/{framed_ip}", response_model=PPPoEAccountingRequestList)
async def get_accounting_by_framed_ip(
    framed_ip: str,
    acct_status_type: str = Query("Start", description="Accounting status type to filter by"),
    count: int = Query(1, ge=1, le=100, description="Number of latest records to return"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get latest accounting requests by framed IP address (client's assigned IP).
    
    Useful for identifying which user has a specific IP address.
    Returns the latest records ordered by updated_at/created_at.
    
    Parameters:
    - framed_ip: The IP address to search for
    - acct_status_type: Status type to filter (default: "Start")
    - count: Number of latest records to return (default: 1, max: 100)
    """
    query = select(PPPoEAccountingRequest).where(
        and_(
            PPPoEAccountingRequest.framed_ip_address == framed_ip,
            PPPoEAccountingRequest.acct_status_type == acct_status_type
        )
    )
    
    count_query = select(func.count()).where(
        and_(
            PPPoEAccountingRequest.framed_ip_address == framed_ip,
            PPPoEAccountingRequest.acct_status_type == acct_status_type
        )
    )
    result = await db.execute(count_query)
    total = result.scalar()
    
    # Order by updated_at first (if exists), then created_at, both descending to get latest
    query = query.order_by(
        PPPoEAccountingRequest.updated_at.desc().nulls_last(),
        PPPoEAccountingRequest.created_at.desc()
    )
    query = query.limit(count)
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    total_pages = (total + count - 1) // count
    
    return {
        "total": total,
        "items": items,
        "page": 1,
        "page_size": count,
        "total_pages": total_pages
    }


@router.get("/requests/by-ip/nas/{nas_ip}", response_model=PPPoEAccountingRequestList)
async def get_accounting_by_nas_ip(
    nas_ip: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """
    Get accounting requests by NAS IP address (router/access server).
    
    Useful for monitoring activity on a specific router.
    """
    query = select(PPPoEAccountingRequest).where(
        PPPoEAccountingRequest.nas_ip_address == nas_ip
    )
    
    count_query = select(func.count()).where(
        PPPoEAccountingRequest.nas_ip_address == nas_ip
    )
    result = await db.execute(count_query)
    total = result.scalar()
    
    query = query.order_by(PPPoEAccountingRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/sessions/active", response_model=PPPoEAccountingRequestList)
async def get_active_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user_name: Optional[str] = Query(None, description="Filter by username"),
    nas_ip_address: Optional[str] = Query(None, description="Filter by NAS IP"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get active PPPoE sessions (sessions with Start but no Stop).
    
    This finds sessions that have an Acct-Status-Type of 'Start' 
    but no corresponding 'Stop' record.
    """
    # Subquery to find session IDs that have Stop records
    stop_sessions_subquery = select(PPPoEAccountingRequest.acct_session_id).where(
        PPPoEAccountingRequest.acct_status_type == "Stop"
    )
    
    # Main query: find Start records without corresponding Stop
    query = select(PPPoEAccountingRequest).where(
        and_(
            PPPoEAccountingRequest.acct_status_type == "Start",
            PPPoEAccountingRequest.acct_session_id.not_in(stop_sessions_subquery)
        )
    )
    
    # Apply optional filters
    if user_name:
        query = query.where(PPPoEAccountingRequest.user_name == user_name)
    if nas_ip_address:
        query = query.where(PPPoEAccountingRequest.nas_ip_address == nas_ip_address)
    
    # Get count
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    total = result.scalar()
    
    # Apply pagination
    query = query.order_by(PPPoEAccountingRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }
