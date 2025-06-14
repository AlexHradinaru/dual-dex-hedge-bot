import logging
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional
import aiohttp
import json

from config.settings import (
    BACKPACK_API_URL, MARKET, ORDER_SIZE,
    TAKE_PROFIT_PERCENTAGE, STOP_LOSS_PERCENTAGE,
    LOOP_INTERVAL_MINUTES, ERROR_RETRY_MINUTES
)
from core.auth import BackpackAuth
from core.market import Market
from models.order import Order
from models.position import Position

class BackpackTrader:
    def __init__(self, api_key: str, api_secret: str):
        """Initialize the Backpack trader with API credentials."""
        self.auth = BackpackAuth(api_key, api_secret)
        self.session = aiohttp.ClientSession()
        self.market = Market(self.auth)
        self.position_entry_time = None

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders for the account."""
        path = "/orders"
        params = {
            "symbol": MARKET,
            "marketType": "PERP"
        }
        headers = self.auth.get_auth_headers("orderQueryAll", params)
        
        async with self.session.get(f"{BACKPACK_API_URL}{path}", params=params, headers=headers) as response:
            response_text = await response.text()
            if response.status == 200:
                data = json.loads(response_text)
                return data if isinstance(data, list) else []
            else:
                logging.error(f"Failed to get open orders: {response.status}")
                logging.error(f"Error response: {response_text}")
                return []

    async def cancel_orders_by_type(self, order_type: str) -> bool:
        """Cancel all orders of a specific type."""
        path = "/orders"
        payload = {
            "symbol": MARKET,
            "orderType": order_type
        }
        headers = self.auth.get_auth_headers("orderCancelAll", payload)
        
        async with self.session.delete(f"{BACKPACK_API_URL}{path}", headers=headers, json=payload) as response:
            response_text = await response.text()
            if response.status in [200, 202]:
                logging.info(f"Successfully cancelled {order_type} orders")
                return True
            else:
                logging.error(f"Failed to cancel {order_type} orders: {response.status}")
                logging.error(f"Error response: {response_text}")
                return False

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders and close any open position."""
        position = await self.get_position()
        if position and position.is_open:
            await self.close_position(position)
        
        orders = await self.get_open_orders()
        for order in orders:
            await self.cancel_order(order["id"])

    async def place_order(self, order: Order) -> bool:
        """Place an order."""
        try:
            # Get headers using the signature payload
            headers = self.auth.get_auth_headers("orderExecute", order.to_sign_dict())
            
            # Send request with the request payload
            async with self.session.post(
                f"{BACKPACK_API_URL}/order",
                headers=headers,
                json=order.to_dict()
            ) as response:
                response_text = await response.text()
                logging.debug(f"Response status: {response.status}")
                logging.debug(f"Response headers: {dict(response.headers)}")
                logging.debug(f"Response body: {response_text}")
                
                if response.status in [200, 201, 202]:
                    logging.info(f"Successfully placed {order.order_type} {order.side} order")
                    return True
                else:
                    logging.error(f"Failed to place order: {response.status}")
                    logging.error(f"Error response: {response_text}")
                    return False
                    
        except Exception as e:
            logging.error(f"Error placing order: {str(e)}")
            return False

    async def place_market_order(self, side: str, size: Decimal) -> bool:
        """Place a market order with take profit and stop loss."""
        current_price = await self.market.get_current_price(MARKET)
        if current_price is None:
            return False
            
        # Convert side to API format (BUY -> Bid, SELL -> Ask)
        side_map = {"BUY": "Bid", "SELL": "Ask"}
        api_side = side_map.get(side.upper())
        if not api_side:
            logging.error(f"Invalid side: {side}. Must be one of {list(side_map.keys())}")
            return False
            
        # Calculate take profit and stop loss prices
        if side == "BUY":
            take_profit_price = current_price * (1 + TAKE_PROFIT_PERCENTAGE / 100)
            stop_loss_price = current_price * (1 - STOP_LOSS_PERCENTAGE / 100)
        else:  # SELL
            take_profit_price = current_price * (1 - TAKE_PROFIT_PERCENTAGE / 100)
            stop_loss_price = current_price * (1 + STOP_LOSS_PERCENTAGE / 100)
            
        order = Order(
            order_type="Market",
            side=api_side,  # Use the API-specific side
            symbol=MARKET,
            quote_quantity=str(round(size * current_price, 2)),
            take_profit_trigger_price=str(round(take_profit_price, 2)),
            stop_loss_trigger_price=str(round(stop_loss_price, 2))
        )
        
        return await self.place_order(order)

    async def get_position(self) -> Optional[Position]:
        """Get current position for the market."""
        path = "/position"
        headers = self.auth.get_auth_headers("positionQuery")
        
        async with self.session.get(f"{BACKPACK_API_URL}{path}", headers=headers) as response:
            response_text = await response.text()
            if response.status == 200:
                positions = json.loads(response_text)
                for position_data in positions:
                    if position_data.get("symbol") == MARKET and float(position_data.get("netQuantity", "0")) != 0:
                        return Position.from_api_response(position_data)
                return None
            else:
                logging.error(f"Failed to get positions: {response.status}")
                logging.error(f"Error response: {response_text}")
                return None

    async def close_position(self, position: Position) -> bool:
        """Close an open position with a market order."""
        try:
            order = Order(
                order_type="Market",
                side=position.get_close_side(),
                symbol=MARKET,
                quantity=position.net_quantity,
                reduce_only=True
            )
            
            return await self.place_order(order)
                    
        except Exception as e:
            logging.error(f"Error closing position: {str(e)}")
            return False

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        path = "/order"
        params = {
            "symbol": MARKET,
            "orderId": order_id
        }
        headers = self.auth.get_auth_headers("orderCancel", params)
        
        async with self.session.delete(f"{BACKPACK_API_URL}{path}", params=params, headers=headers) as response:
            response_text = await response.text()
            if response.status == 200:
                logging.info(f"Successfully cancelled order {order_id}")
                return True
            else:
                logging.error(f"Failed to cancel order {order_id}: {response.status}")
                logging.error(f"Error response: {response_text}")
                return False

    async def trading_loop(self) -> None:
        """Main trading loop."""
        while True:
            try:
                # First close any open position
                position = await self.get_position()
                if position and position.is_open:
                    if not await self.close_position(position):
                        logging.error("Failed to close position, skipping this iteration")
                        await asyncio.sleep(ERROR_RETRY_MINUTES * 60)
                        continue
                
                # Cancel any existing orders
                await self.cancel_all_orders()
                
                # Place new orders
                logging.info("Placing new orders...")
                await self.place_market_order("BUY", ORDER_SIZE)
                
                logging.info(f"Waiting for {LOOP_INTERVAL_MINUTES} minutes before next iteration...")
                await asyncio.sleep(LOOP_INTERVAL_MINUTES * 60)
                
            except Exception as e:
                logging.error(f"Error in trading loop: {str(e)}")
                logging.info(f"Waiting {ERROR_RETRY_MINUTES} minutes before retrying...")
                await asyncio.sleep(ERROR_RETRY_MINUTES * 60)

    async def close(self):
        """Close all sessions."""
        await self.session.close()
        await self.market.close() 