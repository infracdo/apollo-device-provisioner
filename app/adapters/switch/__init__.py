"""
Switch Adapters Package

Device adapters for network switches.
"""
from app.adapters.switch.base_switch import BaseSwitchAdapter
from app.adapters.switch.ruijie import RuijieSwitch
from app.adapters.switch.nexus import NexusSwitch

__all__ = [
    'BaseSwitchAdapter',
    'RuijieSwitch',
    'NexusSwitch'
]
