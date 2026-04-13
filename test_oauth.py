"""
Test script for OAuth token authentication
Run this to verify OAuth configuration and token retrieval
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.oauth_handler import OAuthTokenManager
from src.config_loader import ConfigLoader
from src.utils.logger import get_logger
import os
from dotenv import load_dotenv

logger = get_logger()


def test_oauth_token():
    """Test OAuth token retrieval and validation"""
    
    print("\n" + "="*80)
    print("OAuth Token Authentication Test")
    print("="*80 + "\n")
    
    # Load environment variables
    load_dotenv()
    
    # Check if OAuth is configured
    auth_type = os.getenv("AUTH_TYPE", "").lower()
    if auth_type != "oauth":
        print("❌ AUTH_TYPE is not set to 'oauth' in .env file")
        print(f"   Current value: {auth_type}")
        print("\nPlease update your .env file:")
        print("   AUTH_TYPE=oauth")
        return False
    
    print("✓ AUTH_TYPE is set to 'oauth'\n")
    
    # Check required OAuth variables
    required_vars = {
        "OAUTH_TOKEN_URL": os.getenv("OAUTH_TOKEN_URL"),
        "OAUTH_CLIENT_ID": os.getenv("OAUTH_CLIENT_ID"),
        "OAUTH_CLIENT_SECRET": os.getenv("OAUTH_CLIENT_SECRET"),
        "OAUTH_USERNAME": os.getenv("OAUTH_USERNAME"),
        "OAUTH_PASSWORD": os.getenv("OAUTH_PASSWORD")
    }
    
    print("Checking OAuth configuration:")
    missing_vars = []
    for var_name, var_value in required_vars.items():
        if var_value:
            # Mask sensitive values
            if "PASSWORD" in var_name or "SECRET" in var_name:
                display_value = "*" * len(var_value) if len(var_value) > 0 else "(empty)"
            else:
                display_value = var_value
            print(f"  ✓ {var_name}: {display_value}")
        else:
            print(f"  ✗ {var_name}: NOT SET")
            missing_vars.append(var_name)
    
    if missing_vars:
        print(f"\n❌ Missing required variables: {', '.join(missing_vars)}")
        print("\nPlease update your .env file with the missing values.")
        return False
    
    print("\n✓ All OAuth variables are configured\n")
    print("-"*80)
    
    # Create OAuth configuration
    oauth_config = {
        "token_url": os.getenv("OAUTH_TOKEN_URL"),
        "client_id": os.getenv("OAUTH_CLIENT_ID"),
        "client_secret": os.getenv("OAUTH_CLIENT_SECRET"),
        "username": os.getenv("OAUTH_USERNAME"),
        "password": os.getenv("OAUTH_PASSWORD"),
        "grant_type": os.getenv("OAUTH_GRANT_TYPE", "password")
    }
    
    try:
        # Initialize OAuth manager
        print("\n[1] Initializing OAuth Token Manager...")
        oauth_manager = OAuthTokenManager(oauth_config)
        print("    ✓ OAuth manager initialized\n")
        
        # Obtain token
        print("[2] Requesting OAuth token...")
        print(f"    Token URL: {oauth_config['token_url']}")
        print(f"    Grant Type: {oauth_config['grant_type']}")
        print(f"    Client ID: {oauth_config['client_id']}")
        print(f"    Username: {oauth_config['username']}\n")
        
        token = oauth_manager.get_token()
        
        if token:
            print("    ✓ Token obtained successfully!\n")
            
            # Display token details (masked)
            print("[3] Token Details:")
            print(f"    Access Token: {token[:20]}...{token[-10:]} (masked)")
            print(f"    Token Type: {oauth_manager.token_type}")
            
            if oauth_manager.token_expiry:
                import time
                remaining = int(oauth_manager.token_expiry - time.time())
                print(f"    Expires In: {remaining} seconds ({remaining // 60} minutes)")
            else:
                print(f"    Expires In: Not specified")
            
            if oauth_manager.refresh_token:
                print(f"    Refresh Token: Available")
            else:
                print(f"    Refresh Token: Not provided")
            
            # Test authorization header
            print("\n[4] Testing Authorization Header:")
            auth_header = oauth_manager.get_authorization_header()
            print(f"    {auth_header[:30]}...{auth_header[-20:]} (masked)\n")
            
            # Test token validation
            print("[5] Testing Token Validation:")
            is_valid = oauth_manager._is_token_valid()
            print(f"    Token Valid: {'✓ Yes' if is_valid else '✗ No'}\n")
            
            print("="*80)
            print("✅ OAuth Token Test PASSED")
            print("="*80)
            print("\nYou can now use the automation tool with OAuth authentication.")
            print("Try running: python main.py --action create --env dev --dry-run\n")
            return True
            
        else:
            print("    ✗ Failed to obtain token (no token returned)\n")
            return False
            
    except Exception as e:
        print(f"\n❌ OAuth Token Test FAILED")
        print(f"Error: {str(e)}\n")
        
        # Provide troubleshooting tips
        print("-"*80)
        print("Troubleshooting Tips:")
        print("1. Verify your credentials are correct in .env file")
        print("2. Check that the OAuth token URL is accessible")
        print("3. Ensure client ID and secret are valid")
        print("4. Verify username and password are correct")
        print("5. Check network connectivity to OAuth server")
        print("-"*80 + "\n")
        
        return False


if __name__ == "__main__":
    try:
        success = test_oauth_token()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        logger.exception("Test failed with unexpected error")
        sys.exit(1)
