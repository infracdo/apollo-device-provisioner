"""
PPPoE Accounting Models

RADIUS accounting records for PPPoE sessions.
"""
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class PPPoEAccountingRequest(Base):
    """PPPoE RADIUS Accounting Request Model"""
    __tablename__ = "pppoe_accounting_requests"
    __table_args__ = (
        UniqueConstraint(
            "acct_session_id",
            "acct_status_type",
            name="uq_pppoe_accounting_session_status"
        ),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    
    # RADIUS Accounting Attributes
    service_type = Column(String(50), nullable=True)  # e.g., "Framed-User"
    framed_protocol = Column(String(50), nullable=True)  # e.g., "PPP"
    nas_port = Column(BigInteger, nullable=True)
    nas_port_type = Column(String(50), nullable=True)  # e.g., "Ethernet"
    user_name = Column(String(255), nullable=False, index=True)
    calling_station_id = Column(String(100), nullable=True, index=True)  # MAC address
    called_station_id = Column(String(255), nullable=True)  # Service name
    nas_port_id = Column(String(255), nullable=True)  # Port identifier
    acct_session_id = Column(String(255), nullable=False, index=True)
    framed_ip_address = Column(String(45), nullable=True, index=True)  # IPv4/IPv6
    acct_authentic = Column(String(50), nullable=True)  # e.g., "RADIUS"
    event_timestamp = Column(BigInteger, nullable=True)  # Unix timestamp
    acct_status_type = Column(String(50), nullable=True)  # Start, Stop, Interim-Update
    nas_identifier = Column(String(255), nullable=True)
    acct_delay_time = Column(Integer, nullable=True, default=0)
    nas_ip_address = Column(String(45), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "service_type": self.service_type,
            "framed_protocol": self.framed_protocol,
            "nas_port": self.nas_port,
            "nas_port_type": self.nas_port_type,
            "user_name": self.user_name,
            "calling_station_id": self.calling_station_id,
            "called_station_id": self.called_station_id,
            "nas_port_id": self.nas_port_id,
            "acct_session_id": self.acct_session_id,
            "framed_ip_address": self.framed_ip_address,
            "acct_authentic": self.acct_authentic,
            "event_timestamp": self.event_timestamp,
            "acct_status_type": self.acct_status_type,
            "nas_identifier": self.nas_identifier,
            "acct_delay_time": self.acct_delay_time,
            "nas_ip_address": self.nas_ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
