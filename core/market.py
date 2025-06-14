import logging
from decimal import Decimal
from typing import Dict, List, Optional
import aiohttp
import json

from config.settings import BACKPACK_API_URL
from core.auth import BackpackAuth

class Market:
    def __init__(self, auth: BackpackAuth):
        """Initialize market operations with authentication."""
        self.auth = auth
        self.session = aiohttp.ClientSession()

    async def get_current_price(self, market: str) -> Optional[Decimal]:
        """Get the current price for a market."""
        url = f"{BACKPACK_API_URL}/ticker"
        params = {"symbol": market}
        headers = self.auth.get_auth_headers("tickerQuery", params)
        
        logging.info(f"Getting current price from: {BACKPACK_API_URL}/ticker")
        
        async with self.session.get(url, params=params, headers=headers) as response:
            response_text = await response.text()
            logging.debug(f"Response status: {response.status}")
            logging.debug(f"Response headers: {dict(response.headers)}")
            logging.debug(f"Response body: {response_text}")
            
            if response.status == 200:
                data = json.loads(response_text)
                # Check for price in different possible fields
                price = None
                if "lastPrice" in data:
                    price = data["lastPrice"]
                elif "price" in data:
                    price = data["price"]
                elif "markPrice" in data:
                    price = data["markPrice"]
                
                if price is not None:
                    price_decimal = Decimal(str(price))
                    logging.info(f"Current price for {market}: {price_decimal}")
                    return price_decimal
                else:
                    logging.error(f"No price data found in ticker response. Full response: {data}")
                    return None
            else:
                logging.error(f"Failed to get price: {response.status}")
                logging.error(f"Error response: {response_text}")
                return None

    async def get_market_info(self, market: str) -> Optional[Dict]:
        """Get detailed information about a specific market."""
        url = f"{BACKPACK_API_URL}/market"
        params = {"symbol": market}
        headers = self.auth.get_auth_headers("marketQuery", params)
        
        async with self.session.get(url, params=params, headers=headers) as response:
            response_text = await response.text()
            logging.debug(f"Response status: {response.status}")
            logging.debug(f"Response headers: {dict(response.headers)}")
            logging.debug(f"Response body: {response_text}")
            
            if response.status == 200:
                return json.loads(response_text)
            else:
                logging.error(f"Failed to get market info for {market}: {response.status}")
                logging.error(f"Error response: {response_text}")
                return None

    async def get_all_markets(self) -> List[Dict]:
        """Get all markets from Backpack."""
        url = f"{BACKPACK_API_URL}/markets"
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                logging.info(f"Successfully fetched {len(data)} markets")
                return data
            else:
                logging.error(f"Failed to get markets: {response.status}")
                return []

    async def close(self):
        """Close the aiohttp session."""
        await self.session.close() 