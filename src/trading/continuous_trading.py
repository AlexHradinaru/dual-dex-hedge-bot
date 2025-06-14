import asyncio
import logging
import os
import time
from decimal import Decimal
import aiohttp
from typing import Dict, List, Optional

from ..shared.api_config import ApiConfig
from ..shared.paradex_api_utils import Order, OrderSide, OrderType
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

# ============= CONFIGURATION =============
# Trading parameters
MARKET = "ETH-USD-PERP"  # Market to trade
ORDER_SIZE = Decimal("0.1")  # Size in ETH
TAKE_PROFIT_PERCENTAGE = Decimal("0.5")  # Take profit percentage (e.g., 0.5 for 0.5%)
STOP_LOSS_PERCENTAGE = Decimal("0.5")  # Stop loss percentage (e.g., 0.5 for 0.5%)

# Timing parameters
LOOP_INTERVAL_MINUTES = 2  # How often to check and update orders (in minutes)
ERROR_RETRY_MINUTES = 5  # How long to wait after an error before retrying (in minutes)

# API configuration
paradex_http_url = "https://api.prod.paradex.trade/v1"
# ========================================

async def get_open_orders(jwt_token: str) -> List[Dict]:
    """Get all open orders for the account."""
    url = f"{paradex_http_url}/orders"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                orders = data.get("results", [])
                logging.info(f"All open orders: {orders}")
                return orders
            else:
                logging.error(f"Failed to get open orders: {response.status}")
                return []

async def cancel_order(order_id: str, jwt_token: str) -> bool:
    """Cancel a specific order by ID."""
    url = f"{paradex_http_url}/orders/{order_id}"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as response:
            if response.status in [200, 204]:  # Both 200 and 204 indicate success
                logging.info(f"Successfully cancelled order {order_id}")
                return True
            else:
                logging.error(f"Failed to cancel order {order_id}: {response.status}")
                return False

async def cancel_all_orders(jwt_token: str) -> None:
    """Cancel all open orders."""
    orders = await get_open_orders(jwt_token)
    for order in orders:
        await cancel_order(order["id"], jwt_token)

async def get_current_price(market: str, jwt_token: str) -> Optional[Decimal]:
    """Get the current price for a market."""
    url = f"{paradex_http_url}/orderbook/{market}"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                best_bid = Decimal(str(data["bids"][0][0])) if data["bids"] else None
                best_ask = Decimal(str(data["asks"][0][0])) if data["asks"] else None
                
                if best_bid and best_ask:
                    mid_price = (best_bid + best_ask) / Decimal("2")
                    logging.info(f"Current mid price for {market}: {mid_price}")
                    return mid_price
                else:
                    logging.error("No bids or asks in orderbook")
                    return None
            else:
                logging.error(f"Failed to get price: {response.status}")
                return None

def build_order(
    config: ApiConfig,
    order_type: OrderType,
    order_side: OrderSide,
    size: Decimal,
    market: str,
    client_id: str,
    limit_price: Optional[Decimal] = None,
    trigger_price: Optional[Decimal] = None,
) -> Order:
    """Build an order with the given parameters."""
    timestamp_ms = int(time.time() * 1000)
    
    # Ensure all numeric values are Decimal
    if limit_price is not None:
        limit_price = Decimal(str(round(float(limit_price), 2)))
    
    if trigger_price is not None:
        trigger_price = Decimal(str(round(float(trigger_price), 2)))
    
    # Ensure size is Decimal
    size = Decimal(str(size))
    
    order = Order(
        market=market,
        order_type=order_type,
        order_side=order_side,
        size=size,
        client_id=client_id,
        signature_timestamp=timestamp_ms,
        limit_price=limit_price,
        trigger_price=trigger_price,
    )
    sig = sign_order(config, order)
    order.signature = sig
    return order

async def place_orders_with_tp_sl(
    config: ApiConfig,
    market: str,
    size: Decimal,
    jwt_token: str,
    paradex_config: Dict,
    paradex_http_url: str,
    paradex_account_address: str,
    paradex_account_private_key_hex: str,
) -> None:
    """Place a market order with take profit and stop loss orders."""
    try:
        # Get current price
        current_price = await get_current_price(market, jwt_token)
        if not current_price:
            raise Exception("Failed to get current price")

        # Calculate take profit and stop loss prices
        take_profit_price = current_price * (Decimal("1") + TAKE_PROFIT_PERCENTAGE / Decimal("100"))
        stop_loss_price = current_price * (Decimal("1") - STOP_LOSS_PERCENTAGE / Decimal("100"))

        # Round prices to 2 decimal places
        take_profit_price = Decimal(str(round(float(take_profit_price), 2)))
        stop_loss_price = Decimal(str(round(float(stop_loss_price), 2)))

        # Ensure size is Decimal
        size = Decimal(str(size))

        # Place market order
        market_order = build_order(
            config,
            OrderType.Market,
            OrderSide.Buy,
            size,
            market,
            f"market_{int(time.time())}",
        )
        await post_order_payload(paradex_http_url, jwt_token, market_order.dump_to_dict())
        logging.info(f"Placed market order at {current_price}")

        # Refresh JWT before placing TP order
        jwt_token = await get_jwt_token(
            paradex_config,
            paradex_http_url,
            paradex_account_address,
            paradex_account_private_key_hex,
        )

        # Place take profit order
        tp_order = build_order(
            config,
            OrderType.TakeProfitLimit,
            OrderSide.Sell,
            size,
            market,
            f"tp_{int(time.time())}",
            limit_price=take_profit_price,
            trigger_price=take_profit_price,
        )
        tp_order_dict = tp_order.dump_to_dict()
        tp_order_dict["flags"] = ["REDUCE_ONLY"]
        await post_order_payload(paradex_http_url, jwt_token, tp_order_dict)
        logging.info(f"Placed take profit order at {take_profit_price}")

        # Refresh JWT before placing SL order
        jwt_token = await get_jwt_token(
            paradex_config,
            paradex_http_url,
            paradex_account_address,
            paradex_account_private_key_hex,
        )

        # Place stop loss order
        sl_order = build_order(
            config,
            OrderType.StopLossLimit,
            OrderSide.Sell,
            size,
            market,
            f"sl_{int(time.time())}",
            limit_price=stop_loss_price,
            trigger_price=stop_loss_price,
        )
        sl_order_dict = sl_order.dump_to_dict()
        sl_order_dict["flags"] = ["REDUCE_ONLY"]
        await post_order_payload(paradex_http_url, jwt_token, sl_order_dict)
        logging.info(f"Placed stop loss order at {stop_loss_price}")

    except Exception as e:
        logging.error(f"Error in place_orders_with_tp_sl: {str(e)}")
        raise

async def get_position(jwt_token: str) -> Optional[Dict]:
    """Get the current position for the market."""
    url = f"{paradex_http_url}/positions"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                positions = data.get("results", [])
                logging.info(f"All positions: {positions}")
                for position in positions:
                    if position.get("market") == MARKET and position.get("status") == "OPEN":
                        logging.info(f"Found open position for {MARKET}: {position}")
                        return position
                logging.info(f"No open position found for {MARKET}")
                return None
            else:
                logging.error(f"Failed to get positions: {response.status}")
                return None

async def trading_loop(
    config: ApiConfig,
    market: str,
    size: Decimal,
    paradex_config: Dict,
    paradex_http_url: str,
    paradex_account_address: str,
    paradex_account_private_key_hex: str,
) -> None:
    """Main trading loop that runs at configured intervals."""
    while True:
        try:
            # Get fresh JWT token
            jwt_token = await get_jwt_token(
                paradex_config,
                paradex_http_url,
                paradex_account_address,
                paradex_account_private_key_hex,
            )

            # First get current position
            logging.info("Checking current position...")
            position = await get_position(jwt_token)
            if position and position.get("status") == "OPEN":
                size = float(position.get("size", "0"))
                side = "SELL" if size > 0 else "BUY"
                logging.info(f"Found open position: {position}")
                
                # Create market order to close position
                market_order = build_order(
                    config,
                    OrderType.Market,
                    OrderSide.Sell if size > 0 else OrderSide.Buy,
                    Decimal(str(abs(size))),
                    market,
                    f"close_{int(time.time())}",
                )
                market_order_dict = market_order.dump_to_dict()
                market_order_dict["flags"] = ["REDUCE_ONLY"]
                
                logging.info(f"Closing position with {side} order of size {abs(size)}")
                await post_order_payload(paradex_http_url, jwt_token, market_order_dict)
                
                # Wait for order to process
                logging.info("Waiting for position close order to process...")
                await asyncio.sleep(2)
                
                # Verify position is closed
                new_position = await get_position(jwt_token)
                if new_position and new_position.get("status") == "OPEN":
                    logging.error(f"Position not closed. Current size: {new_position.get('size', '0')}")
                    continue
                logging.info("Position successfully closed")

            # Then cancel any remaining orders
            logging.info("Checking for open orders...")
            orders = await get_open_orders(jwt_token)
            if orders:
                logging.info(f"Found {len(orders)} open orders to cancel")
                for order in orders:
                    if order.get("status") in ["NEW", "UNTRIGGERED"]:
                        await cancel_order(order["id"], jwt_token)
            else:
                logging.info("No open orders found")

            # Place new orders
            logging.info("Placing new orders...")
            await place_orders_with_tp_sl(
                config,
                market,
                size,
                jwt_token,
                paradex_config,
                paradex_http_url,
                paradex_account_address,
                paradex_account_private_key_hex,
            )

            # Wait for configured interval
            logging.info(f"Waiting for {LOOP_INTERVAL_MINUTES} minutes before next iteration...")
            await asyncio.sleep(LOOP_INTERVAL_MINUTES * 60)  # Convert minutes to seconds

        except Exception as e:
            logging.error(f"Error in trading loop: {str(e)}")
            # Wait for configured retry interval if there's an error
            logging.info(f"Waiting {ERROR_RETRY_MINUTES} minutes before retrying...")
            await asyncio.sleep(ERROR_RETRY_MINUTES * 60)

async def main(eth_private_key_hex: str) -> None:
    # Initialize Ethereum account
    _, eth_account = get_l1_eth_account(eth_private_key_hex)

    # Load Paradex config
    paradex_config = await get_paradex_config(paradex_http_url)

    # Generate Paradex account
    paradex_account_address, paradex_account_private_key_hex = generate_paradex_account(
        paradex_config, eth_account.key.hex()
    )

    # Initialize config
    config = ApiConfig()
    config.paradex_http_url = paradex_http_url
    config.paradex_config = paradex_config
    config.paradex_account = paradex_account_address
    config.paradex_account_private_key = paradex_account_private_key_hex

    # Start the trading loop
    await trading_loop(
        config,
        MARKET,
        ORDER_SIZE,
        paradex_config,
        paradex_http_url,
        paradex_account_address,
        paradex_account_private_key_hex,
    )

if __name__ == "__main__":
    # Logging
    logging.basicConfig(
        level=os.getenv("LOGGING_LEVEL", "INFO"),
        format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load environment variables
    eth_private_key_hex = os.getenv("ETHEREUM_PRIVATE_KEY", "")

    # Run main
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main(eth_private_key_hex))
    except KeyboardInterrupt:
        logging.info("Trading loop stopped by user")
    except Exception as e:
        logging.error("Error occurred:")
        logging.error(e) 