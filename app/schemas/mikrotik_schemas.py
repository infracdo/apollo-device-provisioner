"""
Mikrotik Pydantic Schemas

Request and response models for Mikrotik API endpoints.
"""
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Literal


class QueueCreateRequest(BaseModel):
    """Queue create request model"""
    device_id: int = Field(..., description="Mikrotik device ID")
    name: str = Field(..., max_length=255, description="Queue name")
    target_ip: str = Field(..., description="Target IP or subnet")
    upload_kbps: int = Field(..., gt=0, description="Upload speed in Kbps")
    download_kbps: int = Field(..., gt=0, description="Download speed in Kbps")
    min_upload_kbps: Optional[int] = Field(None, description="Guaranteed upload")
    min_download_kbps: Optional[int] = Field(None, description="Guaranteed download")
    parent_queue: Optional[str] = Field(None, description="Parent queue name")
    priority: Optional[int] = Field(None, ge=1, le=8, description="Queue priority")
    comment: Optional[str] = None


class QueueUpdateRequest(BaseModel):
    """Queue update request model"""
    upload_kbps: Optional[int] = Field(None, gt=0, description="Upload speed in Kbps")
    download_kbps: Optional[int] = Field(None, gt=0, description="Download speed in Kbps")
    min_upload_kbps: Optional[int] = Field(None, description="Guaranteed upload")
    min_download_kbps: Optional[int] = Field(None, description="Guaranteed download")
    priority: Optional[int] = Field(None, ge=1, le=8, description="Queue priority")
    disabled: Optional[bool] = None


class QueueResponse(BaseModel):
    """Queue response model"""
    status: Literal['success', 'error']
    queue_id: Optional[str] = None
    message: str


class HotspotUserRequest(BaseModel):
    """Hotspot user request model"""
    device_id: int = Field(..., description="Mikrotik device ID")
    username: str = Field(..., max_length=100, description="Username")
    password: str = Field(..., max_length=100, description="Password")
    profile: Optional[str] = Field(None, description="User profile")
    mac_address: Optional[str] = Field(None, description="MAC address binding")
    upload_kbps: Optional[int] = Field(None, description="Upload limit")
    download_kbps: Optional[int] = Field(None, description="Download limit")
    comment: Optional[str] = None


class HotspotUserResponse(BaseModel):
    """Hotspot user response model"""
    status: Literal['success', 'error']
    user_id: Optional[str] = None
    message: str


class IPPoolResponse(BaseModel):
    id: int
    mikrotik_id: int
    subnet: str
    counter: int
    next_ip: str
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class IPPoolCreate(BaseModel):
    mikrotik_id: int
    start_ip: str
    subnet: str
    counter: int = 0