import base64
import time
import urllib.parse
import json
from typing import Dict, Optional, Tuple
import ed25519
import logging

class BackpackAuth:
    def __init__(self, api_key: str, api_secret: str):
        """Initialize with base64 encoded ED25519 keypair."""
        self.api_key = api_key  # Store original base64 key
        self.api_secret = api_secret  # Store original base64 secret
        
        # Initialize signing key from base64 secret
        self.signing_key = ed25519.SigningKey(base64.b64decode(api_secret))
        self.verifying_key = self.signing_key.get_verifying_key()

    def generate_signature(self, instruction: str, params: Optional[Dict] = None) -> Tuple[str, str, str]:
        """
        Generate signature according to Backpack's requirements:
        1. Sort parameters alphabetically
        2. Convert to query string format
        3. Append timestamp and window
        4. Prefix with instruction
        5. Sign with ED25519
        """
        # Generate timestamp and window
        timestamp = str(int(time.time() * 1000))
        window = "5000"  # Default window in milliseconds
        
        # Start with instruction
        signing_string = f"instruction={instruction}"
        
        # Add sorted parameters if any
        if params:
            # Sort the dictionary by keys
            sorted_params = dict(sorted(params.items()))
            # Convert to query string format, handling boolean values
            param_string = "&".join(
                f"{k}={str(v).lower()}" if isinstance(v, bool) else f"{k}={v}"
                for k, v in sorted_params.items()
            )
            if param_string:
                signing_string += f"&{param_string}"
        
        # Append timestamp and window
        signing_string += f"&timestamp={timestamp}&window={window}"
        
        # Log the signing string
        logging.info(f"Full signing string: {signing_string}")
        
        # Sign the string
        signature = self.signing_key.sign(signing_string.encode())
        
        # Log the signature
        signature_b64 = base64.b64encode(signature).decode()
        logging.info(f"Generated signature: {signature_b64}")
        logging.info("=== End Signature Debug ===")
        
        return signature_b64, timestamp, window

    def get_auth_headers(self, instruction: str, params: Optional[Dict] = None) -> Dict[str, str]:
        """Generate authentication headers for API requests.
        
        Headers:
        - X-API-KEY: API key (required)
        - X-SIGNATURE: Signature of the request (required)
        - X-TIMESTAMP: Timestamp in milliseconds (required)
        - X-WINDOW: Time window in milliseconds (optional, default 5000)
        """
        # Generate signature and get timestamp/window
        signature, timestamp, window = self.generate_signature(instruction, params)
        
        return {
            "X-API-KEY": self.api_key,  # Use original base64 key
            "X-SIGNATURE": signature,
            "X-TIMESTAMP": timestamp,
            "X-WINDOW": window
        } 