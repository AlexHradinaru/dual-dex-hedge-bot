from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

@dataclass
class Position:
    """Represents a trading position."""
    symbol: str
    net_quantity: str
    entry_price: Optional[str] = None
    mark_price: Optional[str] = None
    unrealized_pnl: Optional[str] = None
    liquidation_price: Optional[str] = None

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return float(self.net_quantity) > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return float(self.net_quantity) < 0

    @property
    def is_open(self) -> bool:
        """Check if position is open."""
        return float(self.net_quantity) != 0

    def get_close_side(self) -> str:
        """Get the side needed to close this position."""
        return "Ask" if self.is_long else "Bid"

    @classmethod
    def from_api_response(cls, data: dict) -> 'Position':
        """Create a Position instance from API response."""
        return cls(
            symbol=data.get('symbol', ''),
            net_quantity=data.get('netQuantity', '0'),
            entry_price=data.get('entryPrice'),
            mark_price=data.get('markPrice'),
            unrealized_pnl=data.get('unrealizedPnl'),
            liquidation_price=data.get('liquidationPrice')
        ) 