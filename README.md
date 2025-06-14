# Delta-Neutral Trading Bot

A sophisticated trading bot that implements delta-neutral trading strategies across two decentralized exchanges (DEXs): Backpack and Paradex. The bot maintains market neutrality by simultaneously placing opposite orders on both exchanges.

## Features

- 🔐 **Dual Exchange Authentication**
  - Secure API authentication for both Backpack and Paradex
  - Environment-based configuration for API keys and secrets

- 📊 **Delta-Neutral Trading**
  - Simultaneous market orders on both exchanges
  - Opposite order placement (e.g., buy on Backpack, sell on Paradex)
  - Automated position management

- 🎯 **Risk Management**
  - Take-profit orders automatically placed after execution
  - Stop-loss orders for risk mitigation
  - Configurable profit and loss thresholds

- 🔄 **Automated Maintenance**
  - 5-minute interval checks for open orders
  - Automatic cancellation of stale orders
  - Continuous rebalancing of positions

## Project Structure

```
combined-dex/
├── src/
│   ├── trading/
│   │   └── unified_trader.py    # Main trading logic
│   └── shared/
│       ├── api_config.py        # API configuration
│       └── api_client.py        # API client utilities
├── core/
│   ├── auth.py                 # Authentication handlers
│   └── market.py              # Market data handlers
├── models/
│   ├── order.py               # Order models
│   └── position.py            # Position models
├── requirements.txt           # Project dependencies
└── .env                      # Environment configuration
```

## Setup

1. **Environment Setup**
   ```bash
   # Create and activate virtual environment
   python3.9 -m venv .venv
   source .venv/bin/activate  # On Unix/macOS
   # or
   .venv\Scripts\activate     # On Windows

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configuration**
   Create a `.env` file with your credentials:
   ```env
   # Paradex Configuration
   ETHEREUM_PRIVATE_KEY=your_ethereum_private_key_here

   # Backpack Configuration
   BACKPACK_API_KEY=your_backpack_api_key_here
   BACKPACK_API_SECRET=your_backpack_api_secret_here

   # Trading Parameters
   ORDER_SIZE=0.1
   LOOP_INTERVAL_MINUTES=5
   TAKE_PROFIT_PERCENTAGE=0.5
   STOP_LOSS_PERCENTAGE=0.5

   # Logging
   LOGGING_LEVEL=INFO
   ```

## Running the Bot

```bash
# Make sure you're in the combined-dex directory
cd combined-dex

# Activate virtual environment
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate     # On Windows

# Run the bot
python -m src.trading.unified_trader
```

## Trading Strategy

The bot implements a delta-neutral strategy:

1. **Order Placement**
   - Places market orders on both exchanges simultaneously
   - Maintains opposite positions (long on one exchange, short on the other)

2. **Risk Management**
   - Automatically places take-profit orders after execution
   - Sets stop-loss orders to limit potential losses
   - Configurable profit and loss thresholds

3. **Position Management**
   - Checks positions every 5 minutes
   - Cancels stale orders
   - Replaces orders to maintain target position size

## Dependencies

- `aiohttp==3.9.3`: Async HTTP client
- `python-dotenv==1.0.1`: Environment variable management
- `ed25519==1.5`: Cryptographic operations
- `pydantic==2.6.1`: Data validation
- `starknet.py==0.22.0`: StarkNet integration
- `web3==6.11.3`: Ethereum interaction

## Security Notes

- Never commit your `.env` file or expose API keys
- Use secure methods to store private keys
- Regularly rotate API keys and secrets
- Monitor API usage and rate limits
- Keep your Ethereum private key secure and never share it
- Use environment variables for all sensitive data
- Consider using a hardware wallet for additional security
- Regularly audit your API key permissions

### Security Best Practices

1. **API Key Management**
   - Store API keys in environment variables
   - Use different API keys for development and production
   - Set appropriate permissions for API keys
   - Regularly rotate API keys

2. **Private Key Security**
   - Never commit private keys to the repository
   - Use hardware wallets when possible
   - Consider using a key management service
   - Keep private keys encrypted when stored

3. **Environment Security**
   - Use separate environments for testing and production
   - Regularly update dependencies
   - Monitor for suspicious activity
   - Implement rate limiting

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details. 