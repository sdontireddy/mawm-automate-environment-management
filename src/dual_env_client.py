"""
Dual Environment API Client for Source/Destination operations
Supports cloning configuration from Golden environment to target environments
"""
from typing import Dict, Any, Optional, Literal
from src.api_client import MAWMAPIClient
from src.utils.logger import get_logger

logger = get_logger()

EnvironmentTarget = Literal["source", "destination"]


class DualEnvironmentClient:
    """Manage API calls across source (golden) and destination environments"""
    
    def __init__(
        self,
        destination_config: Dict[str, Any],
        source_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize dual environment client
        
        Args:
            destination_config: Target/destination environment configuration
            source_config: Source/golden environment configuration (optional)
        """
        self.destination_config = destination_config
        self.source_config = source_config
        
        # Initialize destination client
        logger.info(f"Initializing destination environment: {destination_config['environment']['name']}")
        dest_headers = destination_config.get("environment", {}).get("custom_headers", {})
        if dest_headers:
            logger.info(f"  Custom headers: {dest_headers}")
        
        self.destination_client = MAWMAPIClient(
            base_url=destination_config["environment"]["base_url"],
            auth_config=destination_config["auth"],
            timeout_config=destination_config["timeouts"],
            retry_config=destination_config["retry"],
            custom_headers=dest_headers
        )
        
        # Initialize source client if golden environment is enabled
        self.source_client: Optional[MAWMAPIClient] = None
        if source_config:
            logger.info(f"Initializing source environment: {source_config['environment']['name']}")
            source_headers = source_config.get("environment", {}).get("custom_headers", {})
            if source_headers:
                logger.info(f"  Custom headers: {source_headers}")
            
            self.source_client = MAWMAPIClient(
                base_url=source_config["environment"]["base_url"],
                auth_config=source_config["auth"],
                timeout_config=source_config["timeouts"],
                retry_config=source_config["retry"],
                custom_headers=source_headers
            )
    
    def get_client(self, target: EnvironmentTarget = "destination") -> MAWMAPIClient:
        """
        Get the appropriate API client based on target
        
        Args:
            target: Either "source" or "destination"
            
        Returns:
            Appropriate MAWMAPIClient instance
        """
        if target == "source":
            if not self.source_client:
                raise ValueError(
                    "Source environment not configured. Cannot make source API calls."
                )
            return self.source_client
        else:
            return self.destination_client
    
    def make_request(
        self,
        method: str,
        endpoint: str,
        target: EnvironmentTarget = "destination",
        payload: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None
    ):
        """
        Make API request to specified environment
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            target: "source" or "destination"
            payload: Request payload
            path_params: Path parameters
            query_params: Query parameters
            
        Returns:
            Response from appropriate environment
        """
        client = self.get_client(target)
        env_name = "SOURCE" if target == "source" else "DESTINATION"
        
        logger.info(f"[{env_name}] Making request...")
        
        return client.make_request(
            method=method,
            endpoint=endpoint,
            payload=payload,
            path_params=path_params,
            query_params=query_params
        )
    
    def clone_data(
        self,
        source_endpoint: str,
        destination_endpoint: str,
        method: str = "POST",
        transform_fn: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Clone data from source to destination environment
        
        Args:
            source_endpoint: Endpoint to fetch data from source
            destination_endpoint: Endpoint to post data to destination
            method: HTTP method for destination (default: POST)
            transform_fn: Optional function to transform data before posting
            
        Returns:
            Response from destination environment
        """
        if not self.source_client:
            raise ValueError("Source environment not configured for cloning")
        
        logger.info(f"Cloning data: {source_endpoint} -> {destination_endpoint}")
        
        # Fetch from source
        logger.info("[SOURCE] Fetching data...")
        source_response = self.source_client.get(source_endpoint)
        source_data = source_response.json() if source_response.text else {}
        
        logger.info(f"[SOURCE] Retrieved {len(source_data)} items/fields")
        
        # Transform data if needed
        if transform_fn:
            logger.info("Transforming data...")
            destination_data = transform_fn(source_data)
        else:
            destination_data = source_data
        
        # Post to destination
        logger.info("[DESTINATION] Posting data...")
        destination_response = self.destination_client.make_request(
            method=method,
            endpoint=destination_endpoint,
            payload=destination_data
        )
        
        logger.info("[DESTINATION] Data posted successfully")
        
        return destination_response.json() if destination_response.text else {}
    
    def is_dual_mode(self) -> bool:
        """Check if dual environment mode is enabled"""
        return self.source_client is not None
