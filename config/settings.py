from decimal import Decimal

# API configuration
BACKPACK_API_URL = "https://api.backpack.exchange/api/v1"

# Trading parameters
MARKET = "ETH_USDC_PERP"  # Market to trade (ETH/USDC Perpetual Futures)
ORDER_SIZE = Decimal("0.1")  # Size in ETH
TAKE_PROFIT_PERCENTAGE = Decimal("1.0")  # Take profit percentage (1%)
STOP_LOSS_PERCENTAGE = Decimal("1.0")  # Stop loss percentage (1%)

# Timing parameters
LOOP_INTERVAL_MINUTES = 1  # How often to check and update orders (in minutes)
ERROR_RETRY_MINUTES = 5  # How long to wait after an error before retrying (in minutes)

# Logging configuration
LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S" 