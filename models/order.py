from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict

@dataclass
class Order:
    """Represents a trading order."""
    order_type: str
    side: str
    symbol: str
    quantity: Optional[str] = None
    quote_quantity: Optional[str] = None
    price: Optional[str] = None
    take_profit_trigger_price: Optional[str] = None
    stop_loss_trigger_price: Optional[str] = None
    reduce_only: bool = False
    self_trade_prevention: str = "RejectTaker"
    time_in_force: str = "GTC"

    def to_dict(self) -> Dict:
        """Convert order to dictionary format for API request."""
        order_dict = {
            "orderType": self.order_type,
            "side": self.side,
            "symbol": self.symbol,
            "selfTradePrevention": self.self_trade_prevention,
            "timeInForce": self.time_in_force
        }

        if self.quantity:
            order_dict["quantity"] = self.quantity
        if self.quote_quantity:
            order_dict["quoteQuantity"] = self.quote_quantity
        if self.price:
            order_dict["price"] = self.price
        if self.take_profit_trigger_price:
            order_dict["takeProfitTriggerPrice"] = self.take_profit_trigger_price
            order_dict["takeProfitTriggerBy"] = "MarkPrice"
        if self.stop_loss_trigger_price:
            order_dict["stopLossTriggerPrice"] = self.stop_loss_trigger_price
            order_dict["stopLossTriggerBy"] = "MarkPrice"
        if self.reduce_only:
            order_dict["reduceOnly"] = True  # Python boolean for request

        return order_dict

    def to_sign_dict(self) -> Dict:
        """Convert order to dictionary format for signature generation."""
        sign_dict = self.to_dict()
        if self.reduce_only:
            sign_dict["reduceOnly"] = "true"  # String boolean for signature
        return sign_dict

    @classmethod
    def create_market_order(cls, side: str, symbol: str, quote_quantity: str) -> 'Order':
        """Create a market order."""
        return cls(
            order_type="Market",
            side=side,
            symbol=symbol,
            quote_quantity=quote_quantity
        )

    @classmethod
    def create_limit_order(cls, side: str, symbol: str, quantity: str, price: str) -> 'Order':
        """Create a limit order."""
        return cls(
            order_type="Limit",
            side=side,
            symbol=symbol,
            quantity=quantity,
            price=price
        ) 