"""
PPPoE Accounting Request Schemas

Pydantic schemas for RADIUS accounting validation and serialization.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PPPoEAccountingRequestBase(BaseModel):
    """Base schema for PPPoE accounting request"""
    service_type: Optional[str] = Field(None, example="Framed-User")
    framed_protocol: Optional[str] = Field(None, example="PPP")
    nas_port: Optional[int] = Field(None, example=15730339)
    nas_port_type: Optional[str] = Field(None, example="Ethernet")
    user_name: str = Field(..., example="user002")
    calling_station_id: Optional[str] = Field(None, example="E0:07:C2:CE:D2:86")
    called_station_id: Optional[str] = Field(None, example="service1")
    nas_port_id: Optional[str] = Field(None, example="vlan100-OLT-PPPoE")
    acct_session_id: str = Field(..., example="812006a2")
    framed_ip_address: Optional[str] = Field(None, example="10.88.0.2")
    acct_authentic: Optional[str] = Field(None, example="RADIUS")
    event_timestamp: Optional[int] = Field(None, example=1762503027)
    acct_status_type: Optional[str] = Field(None, example="Start")
    nas_identifier: Optional[str] = Field(None, example="MikroTik")
    acct_delay_time: Optional[int] = Field(0, example=0)
    nas_ip_address: str = Field(..., example="10.42.3.28")


class PPPoEAccountingRequestCreate(PPPoEAccountingRequestBase):
    """Schema for creating PPPoE accounting request"""
    pass


class PPPoEAccountingRequestResponse(PPPoEAccountingRequestBase):
    """Schema for PPPoE accounting request response"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class PPPoEAccountingRequestList(BaseModel):
    """Paginated list of accounting requests"""
    total: int
    items: List[PPPoEAccountingRequestResponse]
    page: int
    page_size: int
    total_pages: int
