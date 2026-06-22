"""
GPON Profile Mapper

Utility functions to map manufacturer-specific profile data to standardized format.
"""
from typing import Dict, Any, List


def normalize_tcont_profile(manufacturer: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize T-CONT profile data from any manufacturer to standardized format.
    
    Args:
        manufacturer: OLT manufacturer name (lowercase)
        profile_data: Raw profile data from manufacturer adapter
        
    Returns:
        dict: Normalized T-CONT profile information
    """
    manufacturer = manufacturer.lower()
    
    # Common format across manufacturers
    normalized = {
        'profile_name': profile_data.get('profile_name'),
        'profile_type': profile_data.get('profile_type'),
        'maximum_bandwidth': profile_data.get('maximum_bandwidth'),
        'assured_bandwidth': profile_data.get('assured_bandwidth'),
        'fixed_bandwidth': profile_data.get('fixed_bandwidth'),
        'manufacturer': manufacturer
    }
    
    # Manufacturer-specific mappings
    if manufacturer == "zte":
        # ZTE uses bytes, standard format
        pass
    elif manufacturer == "huawei":
        # Huawei might use different units or naming
        # Adjust if needed based on actual Huawei output
        pass
    elif manufacturer == "richerlink":
        # RicherLink format adjustments
        pass
    elif manufacturer == "bdcom":
        # BDCOM format adjustments
        pass
    
    return normalized


def normalize_vlan_profile(manufacturer: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize VLAN profile data from any manufacturer to standardized format.
    
    Args:
        manufacturer: OLT manufacturer name (lowercase)
        profile_data: Raw profile data from manufacturer adapter
        
    Returns:
        dict: Normalized VLAN profile information
    """
    manufacturer = manufacturer.lower()
    
    # Common format across manufacturers
    normalized = {
        'profile_name': profile_data.get('profile_name'),
        'tag_mode': profile_data.get('tag_mode'),
        'cvlan': profile_data.get('cvlan'),
        'svlan': profile_data.get('svlan'),
        'priority': profile_data.get('priority'),
        'manufacturer': manufacturer
    }
    
    # Manufacturer-specific mappings
    if manufacturer == "zte":
        # ZTE uses: tag, untag, translate
        pass
    elif manufacturer == "huawei":
        # Huawei might use: tag, untag, translation
        # Map to standard names if different
        pass
    elif manufacturer == "richerlink":
        # RicherLink format adjustments
        pass
    elif manufacturer == "bdcom":
        # BDCOM format adjustments
        pass
    
    return normalized


def normalize_profile_list(manufacturer: str, profile_type: str, profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize a list of profiles from any manufacturer.
    
    Args:
        manufacturer: OLT manufacturer name
        profile_type: 'tcont' or 'vlan'
        profiles: List of raw profile data
        
    Returns:
        list: List of normalized profiles
    """
    if profile_type == 'tcont':
        return [normalize_tcont_profile(manufacturer, p) for p in profiles]
    elif profile_type == 'vlan':
        return [normalize_vlan_profile(manufacturer, p) for p in profiles]
    else:
        return profiles
