import asyncio
import logging
import os
import time
from decimal import Decimal
import aiohttp
from typing import Dict, Optional, Tuple

from shared.api_config import ApiConfig
from shared.paradex_api_utils import Order, OrderSide, OrderType
from shared.api_client import (
    get_jwt_token,
    get_paradex_config,
    post_order_payload,
    sign_order,
)
from utils import (
    generate_paradex_account,
    get_l1_eth_account,
)

paradex_http_url = "https://api.prod.paradex.trade/v1"

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
                # Get the mid price from the orderbook
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
                response_text = await response.text()
                logging.error(f"Response: {response_text}")
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
    # Convert timestamp to milliseconds
    timestamp_ms = int(time.time() * 1000)
    
    # Round limit price to 2 decimal places if provided
    if limit_price is not None:
        limit_price = Decimal(str(round(float(limit_price), 2)))
    
    # Round trigger price to 2 decimal places if provided
    if trigger_price is not None:
        trigger_price = Decimal(str(round(float(trigger_price), 2)))
    
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

async def get_fresh_jwt(
    paradex_config: Dict,
    paradex_http_url: str,
    paradex_account_address: str,
    paradex_account_private_key_hex: str,
) -> str:
    """Get a fresh JWT token."""
    logging.info("Getting fresh JWT token...")
    return await get_jwt_token(
        paradex_config,
        paradex_http_url,
        paradex_account_address,
        paradex_account_private_key_hex,
    )

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
            # Try refreshing JWT and getting price again
            jwt_token = await get_fresh_jwt(
                paradex_config,
                paradex_http_url,
                paradex_account_address,
                paradex_account_private_key_hex,
            )
            current_price = await get_current_price(market, jwt_token)
            if not current_price:
                raise Exception("Failed to get current price even after JWT refresh")

        # Calculate take profit and stop loss prices
        take_profit_price = current_price * Decimal("1.01")  # +1%
        stop_loss_price = current_price * Decimal("0.99")  # -1%

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
        jwt_token = await get_fresh_jwt(
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
        jwt_token = await get_fresh_jwt(
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

async def main(eth_private_key_hex: str) -> None:
    # Initialize Ethereum account
    _, eth_account = get_l1_eth_account(eth_private_key_hex)

    # Load Paradex config
    paradex_config = await get_paradex_config(paradex_http_url)

    # Generate Paradex account
    paradex_account_address, paradex_account_private_key_hex = generate_paradex_account(
        paradex_config, eth_account.key.hex()
    )

    # Get initial JWT token
    logging.info("Getting initial JWT...")
    paradex_jwt = await get_jwt_token(
        paradex_config,
        paradex_http_url,
        paradex_account_address,
        paradex_account_private_key_hex,
    )

    # Initialize config
    config = ApiConfig()
    config.paradex_http_url = paradex_http_url
    config.paradex_config = paradex_config
    config.paradex_account = paradex_account_address
    config.paradex_account_private_key = paradex_account_private_key_hex

    # Place orders with take profit
    await place_orders_with_tp_sl(
        config,
        "ETH-USD-PERP",
        Decimal("0.1"),  # Size in ETH
        paradex_jwt,
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
    except Exception as e:
        logging.error("Error occurred:")
        logging.error(e) 