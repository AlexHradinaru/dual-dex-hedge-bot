import asyncio
import logging
import os
import time
from decimal import Decimal
import aiohttp
from typing import Dict, List, Optional, Union
from enum import Enum
from dotenv import load_dotenv

# Import Paradex specific modules
from ..shared.api_config import ApiConfig
from ..shared.paradex_api_utils import Order as ParadexOrder, OrderSide as ParadexOrderSide, OrderType as ParadexOrderType
from ..shared.api_client import (
    get_jwt_token,
    get_paradex_config,
    post_order_payload,
    sign_order,
)
from utils import (
    generate_paradex_account,
    get_l1_eth_account,
)

# Import Backpack specific modules
from core.auth import BackpackAuth
from core.market import Market
from models.order import Order as BackpackOrder
from models.position import Position

class ExchangeType(Enum):
    PARADEX = "paradex"
    BACKPACK = "backpack"

class UnifiedTrader:
    def __init__(
        self,
        paradex_config: Optional[Dict] = None,
        backpack_api_key: Optional[str] = None,
        backpack_api_secret: Optional[str] = None,
        eth_private_key_hex: Optional[str] = None
    ):
        """Initialize the unified trader with both exchange configurations."""
        self.session = aiohttp.ClientSession()
        
        # Initialize Paradex
        if paradex_config and eth_private_key_hex:
            self.paradex_http_url = "https://api.prod.paradex.trade/v1"
            self.paradex_config = paradex_config
            self.eth_private_key_hex = eth_private_key_hex
            
            # Initialize Paradex account
            _, eth_account = get_l1_eth_account(eth_private_key_hex)
            self.paradex_account_address, self.paradex_account_private_key_hex = generate_paradex_account(
                paradex_config, eth_account.key.hex()
            )
            
            # Initialize Paradex config
            self.paradex_api_config = ApiConfig()
            self.paradex_api_config.paradex_http_url = self.paradex_http_url
            self.paradex_api_config.paradex_config = paradex_config
            self.paradex_api_config.paradex_account = self.paradex_account_address
            self.paradex_api_config.paradex_account_private_key = self.paradex_account_private_key_hex
            self.has_paradex = True
        else:
            self.has_paradex = False
            
        # Initialize Backpack
        if backpack_api_key and backpack_api_secret:
            self.auth = BackpackAuth(backpack_api_key, backpack_api_secret)
            self.market = Market(self.auth)
            self.has_backpack = True
        else:
            self.has_backpack = False
            
        if not self.has_paradex and not self.has_backpack:
            raise ValueError("At least one exchange configuration is required")

    async def get_open_orders(self) -> Dict[str, List[Dict]]:
        """Get all open orders for both exchanges."""
        orders = {"paradex": [], "backpack": []}
        
        if self.has_paradex:
            jwt_token = await self._get_paradex_jwt()
            url = f"{self.paradex_http_url}/orders"
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/json"
            }
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    orders["paradex"] = data.get("results", [])
                    
        if self.has_backpack:
            path = "/orders"
            params = {"symbol": "ETH_USDC_PERP", "marketType": "PERP"}
            headers = self.auth.get_auth_headers("orderQueryAll", params)
            async with self.session.get(f"{self.auth.api_url}{path}", params=params, headers=headers) as response:
                if response.status == 200:
                    orders["backpack"] = await response.json()
                    
        return orders

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders on both exchanges."""
        if self.has_paradex:
            jwt_token = await self._get_paradex_jwt()
            orders = await self.get_open_orders()
            for order in orders["paradex"]:
                await self.cancel_order(order["id"], "paradex")
                
        if self.has_backpack:
            await self.cancel_orders_by_type("Market", "backpack")
            await self.cancel_orders_by_type("Limit", "backpack")

    async def get_positions(self) -> Dict[str, Optional[Union[Dict, Position]]]:
        """Get current positions for both exchanges."""
        positions = {"paradex": None, "backpack": None}
        
        if self.has_paradex:
            jwt_token = await self._get_paradex_jwt()
            url = f"{self.paradex_http_url}/positions"
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/json"
            }
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    for position in data.get("results", []):
                        if position.get("market") == "ETH-USD-PERP" and position.get("status") == "OPEN":
                            positions["paradex"] = position
                            break
                            
        if self.has_backpack:
            path = "/position"
            headers = self.auth.get_auth_headers("positionQuery")
            async with self.session.get(f"{self.auth.api_url}{path}", headers=headers) as response:
                if response.status == 200:
                    positions_data = await response.json()
                    for position_data in positions_data:
                        if position_data.get("symbol") == "ETH_USDC_PERP" and float(position_data.get("netQuantity", "0")) != 0:
                            positions["backpack"] = Position.from_api_response(position_data)
                            break
                            
        return positions

    async def place_market_orders(self, side: str, size: Decimal) -> Dict[str, bool]:
        """Place market orders on both exchanges."""
        results = {"paradex": False, "backpack": False}
        
        if self.has_paradex:
            results["paradex"] = await self._place_paradex_market_order(side, size)
            
        if self.has_backpack:
            results["backpack"] = await self._place_backpack_market_order(side, size)
            
        return results

    async def trading_loop(self, size: Decimal, loop_interval_minutes: int = 2) -> None:
        """Main trading loop that runs at configured intervals."""
        while True:
            try:
                # First close any open positions
                positions = await self.get_positions()
                
                if self.has_paradex and positions["paradex"]:
                    if positions["paradex"].get("status") == "OPEN":
                        await self._close_paradex_position(positions["paradex"])
                        
                if self.has_backpack and positions["backpack"]:
                    if positions["backpack"].is_open:
                        await self._close_backpack_position(positions["backpack"])

                # Cancel any existing orders
                await self.cancel_all_orders()

                # Place new orders
                logging.info("Placing new orders...")
                results = await self.place_market_orders("BUY", size)
                
                # Log results
                for exchange, success in results.items():
                    if self.has_paradex and exchange == "paradex":
                        logging.info(f"Paradex order placement: {'Success' if success else 'Failed'}")
                    if self.has_backpack and exchange == "backpack":
                        logging.info(f"Backpack order placement: {'Success' if success else 'Failed'}")

                logging.info(f"Waiting for {loop_interval_minutes} minutes before next iteration...")
                await asyncio.sleep(loop_interval_minutes * 60)

            except Exception as e:
                logging.error(f"Error in trading loop: {str(e)}")
                logging.info("Waiting 5 minutes before retrying...")
                await asyncio.sleep(5 * 60)

    async def _place_paradex_market_order(self, side: str, size: Decimal) -> bool:
        """Place a Paradex market order with take profit and stop loss."""
        try:
            jwt_token = await self._get_paradex_jwt()
            current_price = await self._get_paradex_current_price(jwt_token)
            if not current_price:
                return False

            # Calculate take profit and stop loss prices
            take_profit_price = current_price * (Decimal("1") + Decimal("0.5") / Decimal("100"))
            stop_loss_price = current_price * (Decimal("1") - Decimal("0.5") / Decimal("100"))

            # Place market order
            market_order = self._build_paradex_order(
                ParadexOrderType.Market,
                ParadexOrderSide.Buy if side == "BUY" else ParadexOrderSide.Sell,
                size,
                "ETH-USD-PERP",
                f"market_{int(time.time())}",
            )
            await post_order_payload(self.paradex_http_url, jwt_token, market_order.dump_to_dict())

            # Place take profit and stop loss orders
            await self._place_paradex_tp_sl_orders(jwt_token, size, take_profit_price, stop_loss_price)
            return True
        except Exception as e:
            logging.error(f"Error placing Paradex market order: {str(e)}")
            return False

    async def _place_backpack_market_order(self, side: str, size: Decimal) -> bool:
        """Place a Backpack market order with take profit and stop loss."""
        try:
            current_price = await self.market.get_current_price("ETH_USDC_PERP")
            if current_price is None:
                return False

            # Calculate take profit and stop loss prices
            if side == "BUY":
                take_profit_price = current_price * (1 + Decimal("0.5") / 100)
                stop_loss_price = current_price * (1 - Decimal("0.5") / 100)
            else:
                take_profit_price = current_price * (1 - Decimal("0.5") / 100)
                stop_loss_price = current_price * (1 + Decimal("0.5") / 100)

            # Create and place order
            order = BackpackOrder(
                order_type="Market",
                side="Bid" if side == "BUY" else "Ask",
                symbol="ETH_USDC_PERP",
                quote_quantity=str(round(size * current_price, 2)),
                take_profit_trigger_price=str(round(take_profit_price, 2)),
                stop_loss_trigger_price=str(round(stop_loss_price, 2))
            )
            
            headers = self.auth.get_auth_headers("orderExecute", order.to_sign_dict())
            async with self.session.post(
                f"{self.auth.api_url}/order",
                headers=headers,
                json=order.to_dict()
            ) as response:
                return response.status in [200, 201, 202]
        except Exception as e:
            logging.error(f"Error placing Backpack market order: {str(e)}")
            return False

    async def _get_paradex_jwt(self) -> str:
        """Get a fresh JWT token for Paradex."""
        return await get_jwt_token(
            self.paradex_config,
            self.paradex_http_url,
            self.paradex_account_address,
            self.paradex_account_private_key_hex,
        )

    async def _get_paradex_current_price(self, jwt_token: str) -> Optional[Decimal]:
        """Get current price from Paradex."""
        url = f"{self.paradex_http_url}/orderbook/ETH-USD-PERP"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/json"
        }
        async with self.session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                best_bid = Decimal(str(data["bids"][0][0])) if data["bids"] else None
                best_ask = Decimal(str(data["asks"][0][0])) if data["asks"] else None
                if best_bid and best_ask:
                    return (best_bid + best_ask) / Decimal("2")
            return None

    def _build_paradex_order(
        self,
        order_type: ParadexOrderType,
        order_side: ParadexOrderSide,
        size: Decimal,
        market: str,
        client_id: str,
        limit_price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
    ) -> ParadexOrder:
        """Build a Paradex order."""
        timestamp_ms = int(time.time() * 1000)
        order = ParadexOrder(
            market=market,
            order_type=order_type,
            order_side=order_side,
            size=size,
            client_id=client_id,
            signature_timestamp=timestamp_ms,
            limit_price=limit_price,
            trigger_price=trigger_price,
        )
        sig = sign_order(self.paradex_api_config, order)
        order.signature = sig
        return order

    async def _place_paradex_tp_sl_orders(
        self,
        jwt_token: str,
        size: Decimal,
        take_profit_price: Decimal,
        stop_loss_price: Decimal,
    ) -> None:
        """Place take profit and stop loss orders for Paradex."""
        # Place take profit order
        tp_order = self._build_paradex_order(
            ParadexOrderType.TakeProfitLimit,
            ParadexOrderSide.Sell,
            size,
            "ETH-USD-PERP",
            f"tp_{int(time.time())}",
            limit_price=take_profit_price,
            trigger_price=take_profit_price,
        )
        tp_order_dict = tp_order.dump_to_dict()
        tp_order_dict["flags"] = ["REDUCE_ONLY"]
        await post_order_payload(self.paradex_http_url, jwt_token, tp_order_dict)

        # Place stop loss order
        sl_order = self._build_paradex_order(
            ParadexOrderType.StopLossLimit,
            ParadexOrderSide.Sell,
            size,
            "ETH-USD-PERP",
            f"sl_{int(time.time())}",
            limit_price=stop_loss_price,
            trigger_price=stop_loss_price,
        )
        sl_order_dict = sl_order.dump_to_dict()
        sl_order_dict["flags"] = ["REDUCE_ONLY"]
        await post_order_payload(self.paradex_http_url, jwt_token, sl_order_dict)

    async def _close_paradex_position(self, position: Dict) -> None:
        """Close a Paradex position."""
        jwt_token = await self._get_paradex_jwt()
        size = Decimal(str(position.get("size", "0")))
        if size != 0:
            market_order = self._build_paradex_order(
                ParadexOrderType.Market,
                ParadexOrderSide.Sell if size > 0 else ParadexOrderSide.Buy,
                abs(size),
                "ETH-USD-PERP",
                f"close_{int(time.time())}",
            )
            market_order_dict = market_order.dump_to_dict()
            market_order_dict["flags"] = ["REDUCE_ONLY"]
            await post_order_payload(self.paradex_http_url, jwt_token, market_order_dict)

    async def _close_backpack_position(self, position: Position) -> None:
        """Close a Backpack position."""
        order = BackpackOrder(
            order_type="Market",
            side=position.get_close_side(),
            symbol="ETH_USDC_PERP",
            quantity=position.net_quantity,
            reduce_only=True
        )
        headers = self.auth.get_auth_headers("orderExecute", order.to_sign_dict())
        async with self.session.post(
            f"{self.auth.api_url}/order",
            headers=headers,
            json=order.to_dict()
        ) as response:
            if response.status not in [200, 201, 202]:
                logging.error(f"Failed to close Backpack position: {response.status}")

    async def close(self):
        """Close all sessions."""
        await self.session.close()
        if self.has_backpack:
            await self.market.close()

async def main():
    # Load environment variables from .env file
    load_dotenv()

    # Logging setup
    logging.basicConfig(
        level=os.getenv("LOGGING_LEVEL", "INFO"),
        format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load environment variables
    eth_private_key_hex = os.getenv("ETHEREUM_PRIVATE_KEY", "")
    backpack_api_key = os.getenv("BACKPACK_API_KEY", "")
    backpack_api_secret = os.getenv("BACKPACK_API_SECRET", "")

    # Load trading parameters
    order_size = Decimal(os.getenv("ORDER_SIZE", "0.1"))
    loop_interval_minutes = int(os.getenv("LOOP_INTERVAL_MINUTES", "2"))
    take_profit_percentage = Decimal(os.getenv("TAKE_PROFIT_PERCENTAGE", "0.5"))
    stop_loss_percentage = Decimal(os.getenv("STOP_LOSS_PERCENTAGE", "0.5"))

    try:
        # Initialize Paradex config if credentials are available
        paradex_config = None
        if eth_private_key_hex:
            paradex_config = await get_paradex_config("https://api.prod.paradex.trade/v1")

        # Initialize trader with both exchange configurations
        trader = UnifiedTrader(
            paradex_config=paradex_config,
            backpack_api_key=backpack_api_key,
            backpack_api_secret=backpack_api_secret,
            eth_private_key_hex=eth_private_key_hex
        )

        # Start trading loop
        await trader.trading_loop(
            size=order_size,
            loop_interval_minutes=loop_interval_minutes
        )

    except KeyboardInterrupt:
        logging.info("Trading loop stopped by user")
    except Exception as e:
        logging.error("Error occurred:")
        logging.error(e)
    finally:
        if 'trader' in locals():
            await trader.close()

if __name__ == "__main__":
    asyncio.run(main()) 