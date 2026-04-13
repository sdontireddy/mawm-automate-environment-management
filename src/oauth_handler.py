"""
OAuth 2.0 Authentication Handler for MAWM
"""
import base64
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from src.utils.logger import get_logger

logger = get_logger()

# Token cache directory
TOKEN_CACHE_DIR = Path(".cache/oauth_tokens")


class OAuthTokenManager:
    """Manage OAuth 2.0 token lifecycle for MAWM authentication"""
    
    def __init__(self, oauth_config: Dict[str, Any]):
        """
        Initialize OAuth token manager
        
        Args:
            oauth_config: OAuth configuration containing:
                - token_url: OAuth token endpoint
                - client_id: OAuth client ID
                - client_secret: OAuth client secret
                - username: User username
                - password: User password
                - grant_type: OAuth grant type (default: password)
        """
        self.token_url = oauth_config.get("token_url")
        self.client_id = oauth_config.get("client_id")
        self.client_secret = oauth_config.get("client_secret")
        self.username = oauth_config.get("username")
        self.password = oauth_config.get("password")
        self.grant_type = oauth_config.get("grant_type", "password")
        
        # Generate cache key based on client and username
        self.cache_key = f"{self.client_id}_{self.username}"
        
        # Token state
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[float] = None
        self.token_type: str = "Bearer"
        
        # Validate configuration
        self._validate_config()
        
        # Try to load cached token
        self._load_cached_token()
    
    def _validate_config(self):
        """Validate OAuth configuration"""
        required_fields = ["token_url", "client_id", "client_secret", "username", "password"]
        missing = [f for f in required_fields if not getattr(self, f, None)]
        
        if missing:
            raise ValueError(
                f"Missing required OAuth configuration: {', '.join(missing)}"
            )
    
    def _create_basic_auth_header(self) -> str:
        """Create Basic Authorization header for client credentials"""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def get_token(self, force_refresh: bool = False) -> str:
        """
        Get valid access token, refreshing if necessary
        
        Args:
            force_refresh: Force token refresh even if current token is valid
            
        Returns:
            Valid access token
        """
        if force_refresh or not self._is_token_valid():
            logger.info("Obtaining new OAuth access token...")
            self._obtain_token()
        
        return self.access_token
    
    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired"""
        if not self.access_token:
            return False
        
        if not self.token_expiry:
            return True  # No expiry info, assume valid
        
        # Add 60 second buffer before expiry
        return time.time() < (self.token_expiry - 60)
    
    def _obtain_token(self):
        """Obtain OAuth token using password grant flow"""
        try:
            logger.debug(f"Token request to: {self.token_url}")
            
            # Prepare request headers
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": self._create_basic_auth_header()
            }
            
            # Prepare form data (URL encoded, not JSON)
            data = {
                "grant_type": self.grant_type,
                "username": self.username,
                "password": self.password
            }
            
            # Make token request
            response = requests.post(
                self.token_url,
                headers=headers,
                data=data,  # Use 'data' for form-encoded, not 'json'
                timeout=30
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # Extract token information
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token")
            self.token_type = token_data.get("token_type", "Bearer")
            
            # Calculate token expiry
            expires_in = token_data.get("expires_in")
            if expires_in:
                self.token_expiry = time.time() + int(expires_in)
            
            logger.info("✓ OAuth token obtained successfully")
            if expires_in:
                logger.debug(f"Token expires in {expires_in} seconds")
            
            # Save token to cache
            self._save_cached_token()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"OAuth token request failed: {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to obtain OAuth token: {e.response.text}")
        except Exception as e:
            logger.error(f"OAuth token error: {str(e)}")
            raise
    
    def refresh_access_token(self):
        """Refresh access token using refresh token"""
        if not self.refresh_token:
            logger.warning("No refresh token available, obtaining new token")
            self._obtain_token()
            return
        
        try:
            logger.info("Refreshing OAuth access token...")
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": self._create_basic_auth_header()
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token", self.refresh_token)
            
            expires_in = token_data.get("expires_in")
            if expires_in:
                self.token_expiry = time.time() + int(expires_in)
            
            logger.info("✓ OAuth token refreshed successfully")
            
            # Save refreshed token to cache
            self._save_cached_token()
            
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            logger.info("Obtaining new token instead...")
            self._obtain_token()
    
    def get_authorization_header(self) -> str:
        """Get Authorization header value with current token"""
        token = self.get_token()
        return f"{self.token_type} {token}"
    
    def revoke_token(self):
        """Revoke current token (if revocation endpoint is available)"""
        logger.info("Revoking OAuth token...")
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        self._delete_cached_token()
    
    def _get_cache_file(self) -> Path:
        """Get path to token cache file"""
        return TOKEN_CACHE_DIR / f"{self.cache_key}.json"
    
    def _load_cached_token(self):
        """Load cached token if it exists and is valid"""
        try:
            cache_file = self._get_cache_file()
            if not cache_file.exists():
                return
            
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
            
            self.access_token = cached_data.get("access_token")
            self.refresh_token = cached_data.get("refresh_token")
            self.token_type = cached_data.get("token_type", "Bearer")
            self.token_expiry = cached_data.get("token_expiry")
            
            if self._is_token_valid():
                logger.info(f"Loaded cached OAuth token for {self.username}")
            else:
                logger.info("Cached token expired, will obtain new one")
                self.access_token = None
        except Exception as e:
            logger.debug(f"Failed to load cached token: {str(e)}")
    
    def _save_cached_token(self):
        """Save current token to cache"""
        try:
            TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file = self._get_cache_file()
            
            cached_data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": self.token_type,
                "token_expiry": self.token_expiry
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cached_data, f)
            
            logger.debug(f"Cached OAuth token for {self.username}")
        except Exception as e:
            logger.warning(f"Failed to cache token: {str(e)}")
    
    def _delete_cached_token(self):
        """Delete cached token file"""
        try:
            cache_file = self._get_cache_file()
            if cache_file.exists():
                cache_file.unlink()
        except Exception as e:
            logger.debug(f"Failed to delete cached token: {str(e)}")
