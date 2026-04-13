"""
API Client with retry logic for MAWM automation
"""
import time
import json
from typing import Dict, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from src.utils.logger import get_logger
from src.oauth_handler import OAuthTokenManager

logger = get_logger()


class MAWMAPIClient:
    """API Client for Manhattan WMS with retry and error handling"""
    
    def __init__(
        self,
        base_url: str,
        auth_config: Dict[str, Any],
        timeout_config: Dict[str, Any],
        retry_config: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None
    ):
        self.base_url = base_url.rstrip('/')
        self.auth_config = auth_config
        self.timeout = (timeout_config.get("connection", 10), timeout_config.get("read", 30))
        self.retry_config = retry_config
        self.custom_headers = custom_headers or {}
        self.oauth_manager = None
        
        # Initialize OAuth if configured
        if auth_config.get("type") == "oauth":
            self.oauth_manager = OAuthTokenManager(auth_config.get("oauth", {}))
        
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry configuration"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.retry_config.get("max_attempts", 3),
            backoff_factor=self.retry_config.get("backoff_factor", 2),
            status_forcelist=self.retry_config.get("retry_statuses", [408, 429, 500, 502, 503, 504]),
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set authentication
        if self.auth_config.get("type") == "basic":
            session.auth = (
                self.auth_config.get("username"),
                self.auth_config.get("password")
            )
        elif self.auth_config.get("type") == "bearer":
            session.headers.update({
                "Authorization": f"Bearer {self.auth_config.get('api_key')}"
            })
        elif self.auth_config.get("type") == "oauth":
            # OAuth token will be added per-request in _get_headers()
            logger.info("OAuth authentication configured - tokens will be managed automatically")
        elif self.auth_config.get("type") == "api_key":
            session.headers.update({
                "X-API-Key": self.auth_config.get("api_key")
            })
        
        # Set common headers
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
        return session
    
    def _build_url(self, endpoint: str, path_params: Dict[str, Any] = None) -> str:
        """Build full URL with path parameters"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        if path_params:
            for key, value in path_params.items():
                url = url.replace(f"{{{key}}}", str(value))
        
        return url
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including OAuth token if configured"""
        headers = {}
        
        # Add custom headers (e.g., Location, Organization)
        if self.custom_headers:
            headers.update(self.custom_headers)
            logger.debug(f"Custom headers: {self.custom_headers}")
        
        # Add OAuth token if using OAuth authentication
        if self.auth_config.get("type") == "oauth" and self.oauth_manager:
            headers["Authorization"] = self.oauth_manager.get_authorization_header()
        
        return headers
    
    def make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """Make HTTP request with dynamic headers and retry logic"""
        # Build URL with path parameters
        url = self._build_url(endpoint, path_params)
        
        # Get dynamic headers (OAuth token, custom headers, etc.)
        dynamic_headers = self._get_headers()
        # Log headers with Authorization redacted
        if dynamic_headers:
            safe_headers = {k: ("***" if k.lower() == "authorization" else v) for k, v in dynamic_headers.items()}
            logger.debug(f"Headers: {safe_headers}")
        
        logger.info(f"{method.upper()} {url}")
        if payload:
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        start_time = time.time()
        
        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                json=payload,
                params=query_params,
                headers=dynamic_headers,
                timeout=self.timeout
            )
            
            duration = time.time() - start_time
            logger.info(f"Response: {response.status_code} | Duration: {duration:.2f}s")
            
            # Log response body for non-2xx responses
            if not (200 <= response.status_code < 300):
                logger.warning(f"Response Body: {response.text}")
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout after {self.timeout}s: {url}")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {url} - {str(e)}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {response.status_code}: {url} - {response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """HTTP GET request"""
        return self.make_request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, payload: Dict[str, Any], **kwargs) -> requests.Response:
        """HTTP POST request"""
        return self.make_request("POST", endpoint, payload=payload, **kwargs)
    
    def put(self, endpoint: str, payload: Dict[str, Any], **kwargs) -> requests.Response:
        """HTTP PUT request"""
        return self.make_request("PUT", endpoint, payload=payload, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """HTTP DELETE request"""
        return self.make_request("DELETE", endpoint, **kwargs)
    
    def patch(self, endpoint: str, payload: Dict[str, Any], **kwargs) -> requests.Response:
        """HTTP PATCH request"""
        return self.make_request("PATCH", endpoint, payload=payload, **kwargs)
