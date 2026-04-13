"""
Configuration loader for MAWM automation
"""
import os
import csv
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
from dotenv import load_dotenv
from src.utils.validators import ConfigValidator, ValidationError
from src.utils.logger import get_logger

logger = get_logger()


class ConfigLoader:
    """Load and manage configuration files"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.env_config_dir = self.config_dir / "environments"
        self.validator = ConfigValidator()
        load_dotenv()
        
        # Load unified environments configuration
        self.environments_config = self._load_unified_environments()
        self.unified_config_path = self.config_dir / "environments.yaml"
    
    def load_environment_config(self, env_name: str) -> Dict[str, Any]:
        """Load environment-specific configuration"""
        config_file = self.env_config_dir / f"{env_name}.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Environment configuration not found: {config_file}"
            )
        
        logger.info(f"Loading environment config: {env_name}")
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate configuration structure
        self.validator.validate_environment_config(config)
        
        # Merge with environment variables
        config = self._merge_env_vars(config)
        
        return config
    
    def load_api_sequences(self) -> Dict[str, Any]:
        """Load API sequence configuration"""
        sequence_file = self.config_dir / "api_sequences.yaml"
        
        if not sequence_file.exists():
            raise FileNotFoundError(
                f"API sequence configuration not found: {sequence_file}"
            )
        
        logger.info("Loading API sequences configuration")
        with open(sequence_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate sequence structure
        self.validator.validate_sequence_config(config)
        
        return config
    
    def get_available_environments(self) -> list:
        """Get list of available environment configurations"""
        # First try unified config
        if self.environments_config and "environments" in self.environments_config:
            envs = list(self.environments_config["environments"].keys())
            if envs:
                logger.debug(f"Available environments (unified): {envs}")
                return envs
        
        # Fallback to file-based
        if not self.env_config_dir.exists():
            return []
        
        envs = [
            f.stem for f in self.env_config_dir.glob("*.yaml")
        ]
        logger.debug(f"Available environments (file-based): {envs}")
        return envs
    
    def _merge_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge configuration with environment variables"""
        # Override base URL if provided
        if os.getenv("MAWM_BASE_URL"):
            config["environment"]["base_url"] = os.getenv("MAWM_BASE_URL")
        
        # Override OAuth token URL if provided
        if os.getenv("OAUTH_TOKEN_URL"):
            config["environment"]["oauth_token_url"] = os.getenv("OAUTH_TOKEN_URL")
        
        # Add authentication details
        auth_type = os.getenv("AUTH_TYPE", "basic")
        config["auth"] = {
            "type": auth_type,
            "username": os.getenv("MAWM_USERNAME"),
            "password": os.getenv("MAWM_PASSWORD"),
            "api_key": os.getenv("MAWM_API_KEY")
        }
        
        # Add OAuth configuration if using OAuth
        if auth_type == "oauth":
            config["auth"]["oauth"] = {
                "token_url": config["environment"].get("oauth_token_url") or os.getenv("OAUTH_TOKEN_URL"),
                "client_id": os.getenv("OAUTH_CLIENT_ID"),
                "client_secret": os.getenv("OAUTH_CLIENT_SECRET"),
                "username": os.getenv("OAUTH_USERNAME") or os.getenv("MAWM_USERNAME"),
                "password": os.getenv("OAUTH_PASSWORD") or os.getenv("MAWM_PASSWORD"),
                "grant_type": os.getenv("OAUTH_GRANT_TYPE", "password")
            }
        
        # Override retry settings if provided
        if os.getenv("MAX_RETRIES"):
            config["retry"]["max_attempts"] = int(os.getenv("MAX_RETRIES"))
        
        if os.getenv("TIMEOUT"):
            config["timeouts"]["total"] = int(os.getenv("TIMEOUT"))
        
        return config
    
    def get_payload_template(self, template_name: str) -> Dict[str, Any]:
        """Get payload template from api_sequences.yaml or external JSON file"""
        # First check if external JSON file exists
        payload_file = self.config_dir / "payloads" / f"{template_name}.json"
        if payload_file.exists():
            logger.info(f"Loading payload template from external file: {payload_file}")
            import json
            with open(payload_file, 'r') as f:
                return json.load(f)
        
        # Fallback to inline payloads in api_sequences.yaml
        sequences = self.load_api_sequences()
        
        if "payloads" not in sequences:
            raise ValidationError("No payload templates defined in configuration")
        
        if template_name not in sequences["payloads"]:
            raise ValidationError(f"Payload template not found: {template_name}")
        
        return sequences["payloads"][template_name]
    
    def load_csv_data(self, csv_file: str) -> List[Dict[str, str]]:
        """
        Load CSV file for data-driven iteration
        
        Args:
            csv_file: Path to CSV file (relative to config dir or absolute)
            
        Returns:
            List of dictionaries with CSV data (one dict per row)
        """
        csv_path = Path(csv_file)
        
        # If relative path, assume it's in config dir
        if not csv_path.is_absolute():
            csv_path = self.config_dir / csv_file
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        logger.info(f"Loading CSV data from: {csv_path}")
        rows = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader, 1):
                    rows.append(row)
                    logger.debug(f"CSV Row {idx}: {row}")
            
            logger.info(f"Loaded {len(rows)} rows from CSV: {csv_path}")
            return rows
        except Exception as e:
            raise ValidationError(f"Error loading CSV file {csv_path}: {e}")

    
    def load_golden_environment_config(
        self, 
        destination_env_config: Dict[str, Any],
        source_env_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Load source/golden environment configuration
        
        Args:
            destination_env_config: Destination environment configuration
            source_env_name: Explicit source environment name (dev, qa, etc.)
            
        Returns:
            Source environment configuration or None if not enabled
        """
        if source_env_name:
            logger.info(f"Loading explicit source environment: {source_env_name}")
            # Try unified config first
            if source_env_name.lower() in self.environments_config.get("environments", {}):
                return self.load_environment_variant(source_env_name)
            # Fallback to file-based
            return self.load_environment_config(source_env_name)
        
        # If no explicit source, return None (no golden cloning)
        logger.info("No source environment specified")
        return None

    def _load_unified_environments(self) -> Dict[str, Any]:
        """Load unified environments configuration from environments.yaml"""
        unified_config_path = self.config_dir / "environments.yaml"
        
        if not unified_config_path.exists():
            logger.warning(f"Unified environments config not found: {unified_config_path}")
            return {"environments": {}}
        
        try:
            with open(unified_config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded unified environments configuration from {unified_config_path}")
            return config or {"environments": {}}
        except Exception as e:
            logger.error(f"Error loading unified environments config: {e}")
            return {"environments": {}}

    def load_environment_variant(self, env_name: str) -> Dict[str, Any]:
        """Load a specific environment variant from unified configuration"""
        env_key = env_name.lower()
        
        if env_key not in self.environments_config.get("environments", {}):
            raise ValueError(f"Environment variant not found: {env_name}")
        
        variant = self.environments_config["environments"][env_key]
        
        # Get OAuth config from variant, fallback to .env
        oauth_config = variant.get("oauth", {})
        
        # Get base_url and oauth_token_url: environment-specific first, then default, then hardcoded fallback
        base_url = variant.get("base_url") or self.environments_config.get("default_base_url") or self.environments_config.get("base_url", "https://{{clientID}}.sce.manh.com")
        oauth_token_url = variant.get("oauth_token_url") or self.environments_config.get("default_oauth_token_url") or self.environments_config.get("oauth_token_url", "https://{{clientID}}-auth.sce.manh.com/oauth/token")
        
        # Construct complete config from unified format
        config = {
            "environment": {
                "name": variant.get("name", env_name),
                "base_url": base_url,
                "custom_headers": variant.get("custom_headers", {}),
                "oauth_token_url": oauth_token_url
            },
            "auth": {
                "type": "oauth",
                "username": oauth_config.get("username") or os.getenv("MAWM_USERNAME"),
                "password": oauth_config.get("password") or os.getenv("MAWM_PASSWORD"),
                "oauth": {
                    "token_url": oauth_token_url,
                    "client_id": oauth_config.get("client_id") or os.getenv("OAUTH_CLIENT_ID"),
                    "client_secret": oauth_config.get("client_secret") or os.getenv("OAUTH_CLIENT_SECRET"),
                    "username": oauth_config.get("username") or os.getenv("OAUTH_USERNAME"),
                    "password": oauth_config.get("password") or os.getenv("OAUTH_PASSWORD"),
                    "grant_type": oauth_config.get("grant_type", "password")
                }
            },
            "retry": self.environments_config.get("retry", {
                "max_attempts": 3,
                "backoff_factor": 0.3
            }),
            "timeouts": self.environments_config.get("timeouts", {
                "total": 30,
                "connect": 10
            })
        }
        
        return config
