import asyncio
import logging
import os
import time
import traceback
from decimal import Decimal
from typing import Dict

import aiohttp
from shared.api_client import get_jwt_token, get_paradex_config, sign_order
from shared.api_config import ApiConfig
from shared.paradex_api_utils import Order, OrderSide, OrderType
from utils import (
    generate_paradex_account,
    get_l1_eth_account,
)

paradex_http_url = "https://api.prod.paradex.trade/v1"

def validate_private_key(private_key: str) -> str:
    """
    Validate the Ethereum private key format.
    
    Args:
        private_key: The private key to validate
        
    Returns:
        The validated private key
        
    Raises:
        ValueError: If the private key is invalid
    """
    if not private_key:
        raise ValueError("ETHEREUM_PRIVATE_KEY environment variable is not set")
    
    # Remove '0x' prefix if present
    if private_key.startswith('0x'):
        private_key = private_key[2:]
    
    # Validate hex format
    try:
        int(private_key, 16)
    except ValueError:
        raise ValueError("ETHEREUM_PRIVATE_KEY must be a valid hexadecimal string")
    
    # Validate length (should be 64 characters for 32 bytes)
    if len(private_key) != 64:
        raise ValueError("ETHEREUM_PRIVATE_KEY must be 64 characters long (32 bytes)")
    
    return private_key

async def place_market_order(
    paradex_http_url: str,
    paradex_jwt: str,
    market: str,
    size: Decimal,
    side: OrderSide,
    client_id: str = None,
    config: ApiConfig = None
) -> Dict:
    """
    Place a market order on Paradex.
    
    Args:
        paradex_http_url: The Paradex API URL
        paradex_jwt: JWT token for authentication
        market: Market to trade on (e.g., "ETH-USD-PERP")
        size: Order size
        side: Order side (BUY/SELL)
        client_id: Optional client order ID
        config: ApiConfig instance with paradex_config already set
    
    Returns:
        Dict containing the order response
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {paradex_jwt}"
    }

    # Get current timestamp in milliseconds
    current_time_ms = int(time.time() * 1000)

    # Create order payload
    order = Order(
        market=market,
        order_type=OrderType.Market,
        order_side=side,
        size=size,
        client_id=client_id or f"market_{current_time_ms}",
        signature_timestamp=current_time_ms,
    )

    # Sign the order
    if not config:
        config = ApiConfig()
        config.paradex_config = await get_paradex_config(paradex_http_url)
    signature = sign_order(config, order)

    # Prepare request payload
    payload = {
        "market": market,
        "type": "MARKET",
        "side": side.value,
        "size": str(size),
        "client_id": order.client_id,
        "signature": signature,
        "signature_timestamp": order.signature_timestamp,
        "instruction": "GTC",  # Good Till Cancelled
        "stp": "EXPIRE_TAKER"  # Self Trade Prevention
    }

    url = f"{paradex_http_url}/orders"
    
    logging.info(f"POST {url}")
    logging.info(f"Headers: {headers}")
    logging.info(f"Payload: {payload}")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            status_code = response.status
            response_data = await response.json()
            
            if status_code == 201:
                logging.info(f"Success: {response_data}")
                logging.info("Market order placed successfully")
                return response_data
            else:
                logging.error(f"Status Code: {status_code}")
                logging.error(f"Response: {response_data}")
                raise Exception(f"Failed to place market order: {response_data}")

async def main(eth_private_key_hex: str) -> None:
    try:
        # Validate private key
        eth_private_key_hex = validate_private_key(eth_private_key_hex)
        
        # Initialize Ethereum account
        _, eth_account = get_l1_eth_account(eth_private_key_hex)

        # Load Paradex config
        config = ApiConfig()
        config.paradex_config = await get_paradex_config(paradex_http_url)

        # Generate Paradex account
        paradex_account_address, paradex_account_private_key_hex = generate_paradex_account(
            config.paradex_config, eth_account.key.hex()
        )

        # Set the Paradex account details in the config
        config.paradex_account = paradex_account_address
        config.paradex_account_private_key = paradex_account_private_key_hex

        # Get JWT token
        logging.info("Getting JWT...")
        paradex_jwt = await get_jwt_token(
            config.paradex_config,
            paradex_http_url,
            paradex_account_address,
            paradex_account_private_key_hex,
        )

        # Place market buy order for ETH
        market = "ETH-USD-PERP"
        size = Decimal("0.1")  # Buy 0.1 ETH
        
        order_response = await place_market_order(
            paradex_http_url=paradex_http_url,
            paradex_jwt=paradex_jwt,
            market=market,
            size=size,
            side=OrderSide.Buy,
            config=config  # Pass the config to avoid re-fetching
        )
        print(f"Order placed successfully: {order_response}")
        
    except ValueError as ve:
        logging.error(f"Validation error: {ve}")
        raise
    except Exception as e:
        logging.error(f"Failed to place order: {e}")
        raise

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOGGING_LEVEL", "INFO"),
        format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get Ethereum private key from environment
    eth_private_key_hex = os.getenv("ETHEREUM_PRIVATE_KEY", "")
    
    # Run main
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main(eth_private_key_hex))
    except Exception as e:
        logging.error("Error in main execution")
        logging.error(e)
        traceback.print_exc() 