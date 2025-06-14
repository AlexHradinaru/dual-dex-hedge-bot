"""
Backpack Exchange Trading Bot
A Python package for automated trading on Backpack Exchange.
"""

__version__ = "1.0.0"

from .core.trader import BackpackTrader
from .models.order import Order
from .models.position import Position
from .auth_utils import BackpackAuth

__all__ = [
    'BackpackTrader',
    'Order',
    'Position',
    'BackpackAuth',
]
