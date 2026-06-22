"""
Device Factory

Factory pattern for creating device adapters.
"""
from typing import Dict, Any
from app.adapters.olt.huawei import HuaweiOLTAdapter
from app.adapters.olt.bdcom import BDCOMOLTAdapter
from app.adapters.olt.zte import ZTEOLTAdapter
from app.adapters.olt.smartolt import SmartOLTAdapter
from app.adapters.olt.richerlink import RicherLinkOLTAdapter
from app.adapters.router.mikrotik import MikrotikAdapter
from app.adapters.switch.ruijie import RuijieSwitch
from app.adapters.switch.nexus import NexusSwitch
from app.adapters.switch.arista import AristaAdapter
from app.utils.logging import logger


class DeviceFactory:
    """Factory for creating device adapters"""
    
    OLT_ADAPTERS = {
        'huawei': HuaweiOLTAdapter,
        'bdcom': BDCOMOLTAdapter,
        'zte': ZTEOLTAdapter,
        'smartolt': SmartOLTAdapter,
        'richerlink': RicherLinkOLTAdapter,
    }
    
    ROUTER_ADAPTERS = {
        'mikrotik': MikrotikAdapter,
    }
    
    SWITCH_ADAPTERS = {
        'ruijie': RuijieSwitch,
        'nexus': NexusSwitch,
        'cisco_nexus': NexusSwitch,  # Alias
        'arista': AristaAdapter,
    }
    
    @staticmethod
    def create_olt_adapter(manufacturer: str, device_config: Dict[str, Any]):
        """
        Create OLT adapter instance
        
        Args:
            manufacturer: Device manufacturer (huawei, bdcom, zte, smartolt)
            device_config: Device configuration dictionary
            
        Returns:
            BaseOLTAdapter: Adapter instance
            
        Raises:
            ValueError: If manufacturer is not supported
        """
        adapter_class = DeviceFactory.OLT_ADAPTERS.get(manufacturer.lower())
        if not adapter_class:
            raise ValueError(f"Unsupported OLT manufacturer: {manufacturer}")
        
        logger.info(f"Creating OLT adapter for {manufacturer}")
        return adapter_class(device_config)
    
    @staticmethod
    def create_router_adapter(manufacturer: str, device_config: Dict[str, Any]):
        """
        Create router adapter instance
        
        Args:
            manufacturer: Device manufacturer (mikrotik, etc.)
            device_config: Device configuration dictionary
            
        Returns:
            BaseRouterAdapter: Adapter instance
            
        Raises:
            ValueError: If manufacturer is not supported
        """
        adapter_class = DeviceFactory.ROUTER_ADAPTERS.get(manufacturer.lower())
        if not adapter_class:
            raise ValueError(f"Unsupported router manufacturer: {manufacturer}")
        
        logger.info(f"Creating router adapter for {manufacturer}")
        return adapter_class(device_config)
    
    @staticmethod
    def create_switch_adapter(manufacturer: str, device):
        """
        Create switch adapter instance
        
        Args:
            manufacturer: Device manufacturer (ruijie, nexus, etc.)
            device: Device model instance
            
        Returns:
            BaseSwitchAdapter: Adapter instance
            
        Raises:
            ValueError: If manufacturer is not supported
        """
        adapter_class = DeviceFactory.SWITCH_ADAPTERS.get(manufacturer.lower())
        if not adapter_class:
            raise ValueError(f"Unsupported switch manufacturer: {manufacturer}")
        
        logger.info(f"Creating switch adapter for {manufacturer}")
        return adapter_class(device)
    
    @staticmethod
    def get_adapter(device):
        """
        Get appropriate adapter for a device based on its type and manufacturer
        
        Args:
            device: Device model instance with manufacturer, device_type, and config
            
        Returns:
            Adapter instance (OLT or Router adapter)
            
        Raises:
            ValueError: If device type or manufacturer is not supported
        """
        # Build device config dict
        device_config = {
            'host': device.host,
            'port': device.port,
            'username': device.username,
            'password': device.password,
            'enable_password': device.enable_password,
            'protocol': device.protocol,
            'api_token': device.api_token,
            'verify_ssl': device.verify_ssl,
            'timeout': device.timeout,
        }
        
        # Get device type and manufacturer (they're already strings in DB)
        device_type = device.device_type
        manufacturer = device.manufacturer
        
        if device_type == 'olt':
            return DeviceFactory.create_olt_adapter(manufacturer, device_config)
        elif device_type == 'router':
            return DeviceFactory.create_router_adapter(manufacturer, device_config)
        elif device_type == 'switch':
            return DeviceFactory.create_switch_adapter(manufacturer, device)
        else:
            raise ValueError(f"Unsupported device type: {device_type}")
