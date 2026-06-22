"""
ONT Response Mapper

Utility functions to map manufacturer-specific ONT data to standardized format.
"""
from typing import Dict, Any
from app.schemas.olt_schemas import StandardONTInfo, StandardUnconfiguredONU


def normalize_richerlink_ont(ont_data: Dict[str, Any]) -> StandardONTInfo:
    """
    Map RicherLink ONT data to standardized format.
    
    RicherLink format:
    {
        "port": 1,
        "ont_id": 0,
        "serial_no": "RLGM-FE1CB160",
        "interface": "gpon1/0",
        "register_time": "Thu Jan 1 00:00:00 1970",
        "tx_power": "N/A",
        "rx_power": "N/A",
        "status": "offline",
        "register_status": "offline config"
    }
    """
    return StandardONTInfo(
        # Location
        port=ont_data.get("port"),
        ont_id=ont_data.get("ont_id"),
        
        # Identity
        serial_number=ont_data.get("serial_no"),
        interface=ont_data.get("interface"),
        
        # Status
        status=ont_data.get("status", "unknown"),
        operational_state=ont_data.get("register_status"),  # Map register_status to operational_state
        
        # Signal levels
        tx_power=ont_data.get("tx_power"),
        rx_power=ont_data.get("rx_power"),
        
        # Additional info
        register_time=ont_data.get("register_time"),
        
        # Store original data for backward compatibility
        vendor_data={
            "register_status": ont_data.get("register_status")
        }
    )


def normalize_zte_ont(ont_data: Dict[str, Any]) -> StandardONTInfo:
    """
    Map ZTE ONT data to standardized format.
    
    ZTE format:
    {
        "rack": 1,
        "shelf": 1,
        "slot": 1,
        "port": 1,
        "ont_id": 1,
        "onu_index": "1/1/1:1",
        "admin_state": "enable",
        "omcc_state": "disable",
        "phase_state": "OffLine",
        "channel": "1(GPON)",
        "status": "offline"
    }
    """
    return StandardONTInfo(
        # Location
        rack=ont_data.get("rack"),
        shelf=ont_data.get("shelf"),
        slot=ont_data.get("slot"),
        port=ont_data.get("port"),
        ont_id=ont_data.get("ont_id"),
        
        # Identity
        interface=ont_data.get("onu_index"),
        
        # Status
        status=ont_data.get("status", "unknown"),
        admin_state=ont_data.get("admin_state"),
        phase_state=ont_data.get("phase_state"),
        operational_state=ont_data.get("omcc_state"),
        
        # Store original data for backward compatibility
        vendor_data={
            "omcc_state": ont_data.get("omcc_state"),
            "channel": ont_data.get("channel")
        }
    )


def normalize_huawei_ont(ont_data: Dict[str, Any]) -> StandardONTInfo:
    """
    Map Huawei ONT data to standardized format.
    
    Expected Huawei format (to be confirmed when tested):
    {
        "frame": 0,
        "slot": 1,
        "port": 0,
        "ont_id": 1,
        "serial_number": "HWTC12345678",
        "control_flag": "active",
        "run_state": "online",
        "config_state": "normal",
        "match_state": "match",
        "distance": "1234m",
        "rx_ont_optical_power": "-21.02",
        "rx_olt_optical_power": "-21.50",
        "description": "Customer ONT"
    }
    """
    return StandardONTInfo(
        # Location
        frame=ont_data.get("frame"),
        slot=ont_data.get("slot"),
        port=ont_data.get("port"),
        ont_id=ont_data.get("ont_id"),
        
        # Identity
        serial_number=ont_data.get("serial_number"),
        interface=f"{ont_data.get('frame', 0)}/{ont_data.get('slot', 0)}/{ont_data.get('port', 0)}:{ont_data.get('ont_id', 0)}",
        
        # Status
        status=ont_data.get("run_state", "unknown"),
        admin_state=ont_data.get("control_flag"),
        operational_state=ont_data.get("config_state"),
        phase_state=ont_data.get("match_state"),
        
        # Signal levels
        rx_power=ont_data.get("rx_ont_optical_power"),
        olt_rx_power=ont_data.get("rx_olt_optical_power"),
        distance=ont_data.get("distance"),
        
        # Additional info
        description=ont_data.get("description"),
        last_down_cause=ont_data.get("last_down_cause"),
        
        # Store original data
        vendor_data={
            "control_flag": ont_data.get("control_flag"),
            "match_state": ont_data.get("match_state")
        }
    )


def normalize_bdcom_ont(ont_data: Dict[str, Any]) -> StandardONTInfo:
    """
    Map BDCOM ONT data to standardized format.
    
    Expected BDCOM format (to be confirmed when tested):
    Similar to RicherLink but may have variations.
    """
    # For now, use RicherLink format as baseline
    return normalize_richerlink_ont(ont_data)


def normalize_ont_response(manufacturer: str, ont_data: Dict[str, Any]) -> StandardONTInfo:
    """
    Normalize ONT data from any manufacturer to standardized format.
    
    Args:
        manufacturer: OLT manufacturer name (lowercase)
        ont_data: Raw ONT data from manufacturer adapter
        
    Returns:
        StandardONTInfo: Normalized ONT information
    """
    manufacturer = manufacturer.lower()
    
    # Route to appropriate mapper
    if manufacturer == "richerlink":
        return normalize_richerlink_ont(ont_data)
    elif manufacturer == "zte":
        return normalize_zte_ont(ont_data)
    elif manufacturer == "huawei":
        return normalize_huawei_ont(ont_data)
    elif manufacturer == "bdcom":
        return normalize_bdcom_ont(ont_data)
    else:
        # Unknown manufacturer - do best effort mapping
        return StandardONTInfo(
            port=ont_data.get("port", 0),
            ont_id=ont_data.get("ont_id", 0),
            serial_number=ont_data.get("serial_number") or ont_data.get("serial_no"),
            interface=ont_data.get("interface") or ont_data.get("onu_index"),
            status=ont_data.get("status", "unknown"),
            vendor_data=ont_data  # Store all original data
        )


# ============================================================================
# Unconfigured ONU Mappers
# ============================================================================

def normalize_zte_unconfigured_ont(ont_data: Dict[str, Any]) -> StandardUnconfiguredONU:
    """
    Map ZTE unconfigured ONU data to standardized format.
    
    ZTE format from 'show pon onu uncfg':
    {
        "olt_index": "gpon-olt_1/1/2",
        "rack": 1,
        "shelf": 1,
        "slot": 1,
        "port": 2,
        "model": "MH80",
        "serial_number": "MHAR08DF4BD9",
        "password": None
    }
    """
    return StandardUnconfiguredONU(
        # Location
        port=ont_data.get("port"),
        rack=ont_data.get("rack"),
        shelf=ont_data.get("shelf"),
        slot=ont_data.get("slot"),
        
        # Identity
        serial_number=ont_data.get("serial_number"),
        model=ont_data.get("model"),
        interface=ont_data.get("olt_index"),
        
        # Authentication
        password=ont_data.get("password"),
        
        # Store original data
        vendor_data={
            "olt_index": ont_data.get("olt_index")
        }
    )


def normalize_richerlink_unconfigured_ont(ont_data: Dict[str, Any]) -> StandardUnconfiguredONU:
    """
    Map RicherLink unconfigured ONU data to standardized format.
    
    Expected RicherLink format (to be confirmed):
    {
        "port": 1,
        "serial_number": "RLGM-FE1CB160",
        "model": "F612WV6.0",
        "interface": "gpon1/0"
    }
    """
    return StandardUnconfiguredONU(
        # Location
        port=ont_data.get("port"),
        
        # Identity
        serial_number=ont_data.get("serial_number") or ont_data.get("serial_no"),
        model=ont_data.get("model"),
        interface=ont_data.get("interface"),
        
        # Authentication
        password=ont_data.get("password"),
        
        # Store original data
        vendor_data=ont_data
    )


def normalize_huawei_unconfigured_ont(ont_data: Dict[str, Any]) -> StandardUnconfiguredONU:
    """
    Map Huawei unconfigured ONU data to standardized format.
    
    Expected Huawei format (to be confirmed):
    {
        "frame": 0,
        "slot": 1,
        "port": 0,
        "serial_number": "HWTC12345678",
        "equipment_id": "245H"
    }
    """
    return StandardUnconfiguredONU(
        # Location
        frame=ont_data.get("frame"),
        slot=ont_data.get("slot"),
        port=ont_data.get("port"),
        
        # Identity
        serial_number=ont_data.get("serial_number"),
        model=ont_data.get("equipment_id") or ont_data.get("model"),
        interface=f"{ont_data.get('frame', 0)}/{ont_data.get('slot', 0)}/{ont_data.get('port', 0)}",
        
        # Authentication
        password=ont_data.get("password"),
        
        # Store original data
        vendor_data=ont_data
    )


def normalize_bdcom_unconfigured_ont(ont_data: Dict[str, Any]) -> StandardUnconfiguredONU:
    """
    Map BDCOM unconfigured ONU data to standardized format.
    
    Expected BDCOM format (similar to RicherLink):
    """
    # For now, use RicherLink format as baseline
    return normalize_richerlink_unconfigured_ont(ont_data)


def normalize_unconfigured_ont_response(manufacturer: str, ont_data: Dict[str, Any]) -> StandardUnconfiguredONU:
    """
    Normalize unconfigured ONU data from any manufacturer to standardized format.
    
    Args:
        manufacturer: OLT manufacturer name (lowercase)
        ont_data: Raw unconfigured ONU data from manufacturer adapter
        
    Returns:
        StandardUnconfiguredONU: Normalized unconfigured ONU information
    """
    manufacturer = manufacturer.lower()
    
    # Route to appropriate mapper
    if manufacturer == "richerlink":
        return normalize_richerlink_unconfigured_ont(ont_data)
    elif manufacturer == "zte":
        return normalize_zte_unconfigured_ont(ont_data)
    elif manufacturer == "huawei":
        return normalize_huawei_unconfigured_ont(ont_data)
    elif manufacturer == "bdcom":
        return normalize_bdcom_unconfigured_ont(ont_data)
    else:
        # Unknown manufacturer - do best effort mapping
        return StandardUnconfiguredONU(
            port=ont_data.get("port", 0),
            serial_number=ont_data.get("serial_number") or ont_data.get("serial_no", "unknown"),
            model=ont_data.get("model"),
            interface=ont_data.get("interface") or ont_data.get("olt_index"),
            password=ont_data.get("password"),
            vendor_data=ont_data  # Store all original data
        )

