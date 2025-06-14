import os
import logging
import asyncio
from dotenv import load_dotenv

from config.settings import LOG_FORMAT, LOG_DATE_FORMAT
from core.trader import BackpackTrader

async def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        raise ValueError("BACKPACK_API_KEY and BACKPACK_API_SECRET must be set in environment variables")
    
    logging.info("Starting Backpack trading bot...")
    
    trader = BackpackTrader(api_key, api_secret)
    try:
        await trader.trading_loop()
    except KeyboardInterrupt:
        logging.info("Operation stopped by user")
    except Exception as e:
        logging.error("Error occurred:")
        logging.error(e)
    finally:
        await trader.close()

if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOGGING_LEVEL", "INFO"),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )
    asyncio.run(main()) 