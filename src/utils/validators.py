"""
Validation utilities for automation
"""
from typing import Dict, Any, List
import re


class ValidationError(Exception):
    """Custom validation error"""
    pass


class ResponseValidator:
    """Validate API responses"""
    
    @staticmethod
    def validate_status_code(actual: int, expected: int) -> bool:
        """Validate HTTP status code"""
        if actual != expected:
            raise ValidationError(
                f"Status code mismatch: expected {expected}, got {actual}"
            )
        return True
    
    @staticmethod
    def validate_required_fields(response: Dict[str, Any], required_fields: List[str]) -> bool:
        """Validate required fields exist in response"""
        missing_fields = [field for field in required_fields if field not in response]
        if missing_fields:
            raise ValidationError(
                f"Missing required fields in response: {', '.join(missing_fields)}"
            )
        return True
    
    @staticmethod
    def validate_field_format(value: str, pattern: str, field_name: str) -> bool:
        """Validate field matches expected pattern"""
        if not re.match(pattern, value):
            raise ValidationError(
                f"Field '{field_name}' does not match expected format: {pattern}"
            )
        return True


class ConfigValidator:
    """Validate configuration files"""
    
    @staticmethod
    def validate_environment_config(config: Dict[str, Any]) -> bool:
        """Validate environment configuration structure"""
        required_sections = ["environment", "parameters", "timeouts", "retry"]
        missing = [s for s in required_sections if s not in config]
        if missing:
            raise ValidationError(
                f"Invalid environment config - missing sections: {', '.join(missing)}"
            )
        return True
    
    @staticmethod
    def validate_sequence_config(config: Dict[str, Any]) -> bool:
        """Validate API sequence configuration"""
        if "sequences" not in config:
            raise ValidationError("Missing 'sequences' section in config")
        
        for seq_name, sequence in config["sequences"].items():
            if "steps" not in sequence:
                raise ValidationError(f"Sequence '{seq_name}' missing 'steps'")
            
            for idx, step in enumerate(sequence["steps"]):
                required = ["id", "name", "endpoint", "method"]
                missing = [f for f in required if f not in step]
                if missing:
                    raise ValidationError(
                        f"Step {idx} in sequence '{seq_name}' missing: {', '.join(missing)}"
                    )
        return True


class InputValidator:
    """Validate user inputs"""
    
    @staticmethod
    def validate_environment_name(env_name: str, valid_envs: List[str]) -> bool:
        """Validate environment name - relaxed validation with warning"""
        if valid_envs and env_name not in valid_envs:
            # Just log warning instead of raising error
            from src.utils.logger import get_logger
            logger = get_logger()
            logger.warning(
                f"Environment '{env_name}' not in known list: {', '.join(valid_envs)}. "
                f"Proceeding anyway - ensure this environment exists."
            )
        return True
    
    @staticmethod
    def validate_action(action: str, valid_actions: List[str]) -> bool:
        """Validate action type"""
        if action not in valid_actions:
            raise ValidationError(
                f"Invalid action: {action}. Valid options: {', '.join(valid_actions)}"
            )
        return True
