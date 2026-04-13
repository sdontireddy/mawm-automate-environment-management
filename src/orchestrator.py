"""
API Orchestration Engine for MAWM Environment Creation
"""
from typing import Dict, Any, List, Optional
import time
import json
import uuid
from pathlib import Path
from datetime import datetime
from src.api_client import MAWMAPIClient
from src.dual_env_client import DualEnvironmentClient
from src.config_loader import ConfigLoader
from src.utils.validators import ResponseValidator, ValidationError
from src.utils.logger import get_logger

logger = get_logger()


class OrchestrationError(Exception):
    """Custom orchestration error"""
    pass


class APIOrchestrator:
    """Orchestrate sequential API execution for environment creation"""
    
    def __init__(
        self, 
        environment: str, 
        dry_run: bool = False,
        source_environment: Optional[str] = None
    ):
        self.environment = environment
        self.dry_run = dry_run
        self.source_environment = source_environment
        self.config_loader = ConfigLoader()
        self.validator = ResponseValidator()
        
        # Try unified configuration first, fallback to file-based
        try:
            self.env_config = self.config_loader.load_environment_variant(environment)
            logger.info(f"Using unified environment configuration for: {environment}")
        except (ValueError, FileNotFoundError):
            logger.info(f"Unified config not available, trying file-based for: {environment}")
            self.env_config = self.config_loader.load_environment_config(environment)
        
        self.sequence_config = self.config_loader.load_api_sequences()
        
        # Load source/golden environment config if needed
        self.source_config = self.config_loader.load_golden_environment_config(
            self.env_config,
            source_environment
        )
        
        # Generate run ID based on environment name(s)
        env_name = self.env_config.get("environment", {}).get("name", environment).upper()
        if self.source_config:
            source_name = self.source_config.get("environment", {}).get("name", "source").upper()
            self.run_id = f"{source_name}_{env_name}"
        else:
            self.run_id = env_name
        self.run_folder = Path("runs") / self.run_id
        self.run_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Run folder: {self.run_folder}")
        
        # Initialize API client (dual or single)
        if not dry_run:
            if self.source_config:
                logger.info("Initializing dual-environment mode (source + destination)")
                self.dual_client = DualEnvironmentClient(
                    destination_config=self.env_config,
                    source_config=self.source_config
                )
                self.api_client = self.dual_client.destination_client
            else:
                logger.info("Initializing single-environment mode")
                custom_headers = self.env_config.get("environment", {}).get("custom_headers", {})
                if custom_headers:
                    logger.info(f"Custom headers: {custom_headers}")
                
                self.api_client = MAWMAPIClient(
                    base_url=self.env_config["environment"]["base_url"],
                    auth_config=self.env_config["auth"],
                    timeout_config=self.env_config["timeouts"],
                    retry_config=self.env_config["retry"],
                    custom_headers=custom_headers
                )
                self.dual_client = None
        
        # State tracking
        target_headers = self.env_config.get("environment", {}).get("custom_headers", {})
        source_headers = self.source_config.get("environment", {}).get("custom_headers", {}) if self.source_config else {}
        target_location = target_headers.get("Location") or self.environment.upper()
        target_organization = target_headers.get("Organization")
        source_location = source_headers.get("Location")
        source_organization = source_headers.get("Organization")
        target_username = self.env_config.get("auth", {}).get("oauth", {}).get("username")
        self.execution_state = {
            "timestamp": datetime.now().isoformat(),
            "target_location": target_location,
            "target_organization": target_organization,
            "source_location": source_location,
            "source_organization": source_organization,
            "user_name": target_username
        }
        self.completed_steps = []
        self.failed_steps = []
    
    def execute_sequence(self, sequence_name: str = "create_environment") -> Dict[str, Any]:
        """Execute a complete API sequence"""
        logger.info(f"{'='*80}")
        logger.info(f"Starting Orchestration: {sequence_name}")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Dry Run: {self.dry_run}")
        logger.info(f"{'='*80}")
        
        if sequence_name not in self.sequence_config["sequences"]:
            raise OrchestrationError(f"Sequence not found: {sequence_name}")
        
        sequence = self.sequence_config["sequences"][sequence_name]
        steps = sequence["steps"]
        
        # Resolve description with dynamic values
        description = sequence.get("description", "")
        if description:
            source_location = self.source_config.get("environment", {}).get("custom_headers", {}).get("Location") if self.source_config else "Source"
            target_location = self.env_config.get("environment", {}).get("custom_headers", {}).get("Location") or self.environment.upper()
            description = description.replace("{source_location}", source_location or "Source")
            description = description.replace("{target_location}", target_location)
            logger.info(f"Description: {description}")
        
        # Check if sequence has CSV data for iteration
        csv_file = sequence.get("csv_data")
        if csv_file:
            logger.info(f"CSV-driven sequence detected: {csv_file}")
            return self._execute_sequence_with_csv(sequence, steps, csv_file)
        else:
            return self._execute_sequence_standard(sequence, steps)
    
    def _execute_sequence_with_csv(self, sequence: Dict[str, Any], steps: List[Dict[str, Any]], csv_file: str) -> Dict[str, Any]:
        """Execute sequence with CSV data iteration"""
        # Load CSV data
        csv_rows = self.config_loader.load_csv_data(csv_file)
        
        if not csv_rows:
            raise OrchestrationError(f"CSV file is empty: {csv_file}")
        
        logger.info(f"Loaded {len(csv_rows)} rows from CSV for iteration")
        
        all_results = []
        total_rows = len(csv_rows)
        
        try:
            for row_idx, csv_row in enumerate(csv_rows, 1):
                logger.info(f"\n{'='*80}")
                logger.info(f"Processing CSV Row {row_idx}/{total_rows}: {csv_row}")
                logger.info(f"{'='*80}")
                
                # Reset step tracking for each CSV row
                self.completed_steps = []
                self.failed_steps = []
                
                # Store CSV row data in execution state for placeholder resolution
                self.execution_state["csv_row"] = csv_row
                
                row_result = {
                    "row_number": row_idx,
                    "csv_data": csv_row,
                    "steps": []
                }
                
                try:
                    for step_idx, step in enumerate(steps, 1):
                        # Check if step should be skipped
                        if step.get("skip_step", False):
                            logger.info(f"[{step_idx}/{len(steps)}] Skipping step: {step['name']} (skip_step=true)")
                            self.completed_steps.append(step["id"])
                            row_result["steps"].append({
                                "id": step["id"],
                                "name": step["name"],
                                "status": "skipped"
                            })
                            continue
                        
                        # Check if already completed (prevents re-execution)
                        if step["id"] in self.completed_steps:
                            logger.info(f"[{step_idx}/{len(steps)}] Step already completed: {step['name']}")
                            continue
                        
                        logger.info(f"[{step_idx}/{len(steps)}] Executing step: {step['name']}")
                        try:
                            self._execute_step(step)
                            self.completed_steps.append(step["id"])
                            row_result["steps"].append({
                                "id": step["id"],
                                "name": step["name"],
                                "status": "success"
                            })
                        except Exception as step_error:
                            # Check if step is required
                            is_required = step.get("required", True)
                            if not is_required:
                                logger.warning(f"Step '{step['id']}' failed but is optional (required=false), continuing...")
                                self.completed_steps.append(step["id"])
                                self.failed_steps.append(step["id"])
                                row_result["steps"].append({
                                    "id": step["id"],
                                    "name": step["name"],
                                    "status": "failed_optional",
                                    "error": str(step_error)
                                })
                                continue  # Continue to next step
                            else:
                                logger.error(f"Step '{step['id']}' is required (required=true), stopping row execution")
                                self.failed_steps.append(step["id"])
                                row_result["steps"].append({
                                    "id": step["id"],
                                    "name": step["name"],
                                    "status": "failed_required",
                                    "error": str(step_error)
                                })
                                raise  # Re-raise to skip to next CSV row
                    
                    row_result["status"] = "success"
                    logger.info(f"✓ CSV Row {row_idx} completed successfully")
                    
                except Exception as row_error:
                    row_result["status"] = "failed"
                    row_result["error"] = str(row_error)
                    logger.warning(f"✗ CSV Row {row_idx} failed: {row_error}")
                    # Continue to next CSV row instead of stopping
                
                all_results.append(row_result)
            
            logger.info(f"\n{'='*80}")
            logger.info(f"✓ CSV Orchestration completed")
            logger.info(f"Processed {total_rows} rows")
            successful_rows = sum(1 for r in all_results if r.get("status") == "success")
            logger.info(f"Successful rows: {successful_rows}/{total_rows}")
            logger.info(f"{'='*80}")
            
            return {
                "status": "success" if successful_rows == total_rows else "partial_success",
                "csv_rows_processed": total_rows,
                "csv_rows_successful": successful_rows,
                "results": all_results,
                "execution_state": self.execution_state
            }
            
        except Exception as e:
            logger.error(f"\n{'='*80}")
            logger.error(f"✗ CSV Orchestration failed: {str(e)}")
            logger.error(f"{'='*80}")
            
            return {
                "status": "failed",
                "error": str(e),
                "csv_rows_processed": len(all_results),
                "results": all_results
            }
    
    def _execute_sequence_standard(self, sequence: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute standard sequence without CSV iteration"""
        total_steps = len(steps)
        logger.info(f"Total steps to execute: {total_steps}")
        
        try:
            for idx, step in enumerate(steps, 1):
                # Check if step should be skipped
                if step.get("skip_step", False):
                    logger.info(f"\n[{idx}/{total_steps}] Skipping step: {step['name']} (skip_step=true)")
                    self.completed_steps.append(step["id"])
                    continue
                
                # Check if already completed (prevents re-execution)
                if step["id"] in self.completed_steps:
                    logger.info(f"\n[{idx}/{total_steps}] Step already completed: {step['name']}")
                    continue
                
                logger.info(f"\n[{idx}/{total_steps}] Executing step: {step['name']}")
                try:
                    self._execute_step(step)
                    self.completed_steps.append(step["id"])
                except Exception as step_error:
                    # Check if step is required
                    is_required = step.get("required", True)
                    if not is_required:
                        logger.warning(f"Step '{step['id']}' failed but is optional (required=false), continuing...")
                        self.completed_steps.append(step["id"])
                        self.failed_steps.append(step["id"])
                        continue  # Continue to next step
                    else:
                        logger.error(f"Step '{step['id']}' is required (required=true), stopping execution")
                        self.failed_steps.append(step["id"])
                        raise  # Re-raise to trigger outer exception handler
            
            logger.info(f"\n{'='*80}")
            logger.info(f"✓ Orchestration completed successfully")
            logger.info(f"{'='*80}")
            
            return {
                "status": "success",
                "completed_steps": len(self.completed_steps),
                "execution_state": self.execution_state
            }
            
        except Exception as e:
            logger.error(f"\n{'='*80}")
            logger.error(f"✗ Orchestration failed: {str(e)}")
            logger.error(f"{'='*80}")
            
            # Attempt rollback if enabled
            if self.sequence_config.get("rollback", {}).get("enabled", False):
                self._execute_rollback()
            
            return {
                "status": "failed",
                "error": str(e),
                "completed_steps": self.completed_steps,
                "failed_steps": self.failed_steps
            }
    
    def _execute_step(self, step: Dict[str, Any]):
        """Execute a single API call step"""
        step_id = step["id"]
        step_name = step["name"]
        
        # Check if step is marked as required
        is_required = step.get("required", True)
        
        # Check dependencies
        if "depends_on" in step:
            self._check_dependencies(step["depends_on"])
        
        # Determine target environment
        target = step.get("target", "destination")

        # Check flags
        save_key = step.get("save_response")
        ignore_cache = step.get("ignore_cache", False) or step.get("ignore-cache", False)
        skip_only_api = step.get("skip_only_api", False)
        
        # If ignore_cache is true, delete any existing cached file
        if save_key and ignore_cache:
            self._delete_response_file(step_id, save_key)
            logger.info(f"  Ignore-cache enabled: deleted cached file for step '{step_id}'")
        
        # If cached response exists and ignore_cache is false, load and skip entirely
        if save_key and not ignore_cache:
            cached_data = self._load_response_from_file(step_id, save_key)
            if cached_data is not None:
                self.execution_state[save_key] = cached_data
                logger.info(f"  Using cached data for step '{step_id}' from run folder; skipping API call")
                return
        
        # If ignore_cache=true and skip_only_api=true, load cached file for transformation override
        if save_key and ignore_cache and skip_only_api:
            cached_data = self._load_response_from_file(step_id, save_key)
            if cached_data is not None:
                logger.info(f"  Loading cached file for transformation override (ignore_cache + skip_only_api)")
                # Store as saved data for use_saved_data to pick up
                if "use_saved_data" in step:
                    saved_key = step["use_saved_data"]
                    self.execution_state[saved_key] = cached_data
        elif save_key and ignore_cache:
            logger.info(f"  Ignore-cache enabled for step '{step_id}'; will not use cached data")
        
        # Build request parameters
        endpoint = self._resolve_placeholders(step["endpoint"])
        method = step["method"]
        
        # Build payload from template or use saved data
        if "use_saved_data" in step:
            # Use previously saved data from source environment
            saved_key = step["use_saved_data"]
            logger.debug(f"  Looking for saved data key: {saved_key}")
            logger.debug(f"  Available keys in execution_state: {list(self.execution_state.keys())}")
            if saved_key not in self.execution_state:
                raise OrchestrationError(f"Required data not found: {saved_key}")
            payload = self.execution_state[saved_key]
            logger.info(f"  Using saved data: {saved_key}")
            
            # Apply data transformations if specified
            if "transform_data" in step:
                payload = self._transform_payload_data(payload, step["transform_data"])
                logger.info(f"  Applied data transformations")
        elif "payload_template" in step:
            payload = self._build_payload(step)
        else:
            payload = None

        # Save request payload for visibility/debugging
        if payload is not None:
            self._save_request_payload(step_id, payload)
            # Log the final payload with all transformations applied
            logger.info(f"  Final payload (after transformations):")
            logger.info(f"{json.dumps(payload, indent=2)}")
        
        logger.info(f"  Endpoint: {method} {endpoint}")
        logger.info(f"  Target: {target.upper()}")
        
        # Log the actual environment name being targeted
        if target == "source" and self.source_config:
            env_name = self.source_config.get("environment", {}).get("name", "source")
            env_url = self.source_config.get("environment", {}).get("base_url", "unknown")
        else:
            env_name = self.env_config.get("environment", {}).get("name", self.environment)
            env_url = self.env_config.get("environment", {}).get("base_url", "unknown")
        
        logger.info(f"  Executing against: {env_name} ({env_url})")
        
        # Check if we should skip only the API call but process data
        skip_only_api = step.get("skip_only_api", False)
        
        # Prepare step-specific authentication and headers
        step_config = self.env_config.copy()
        
        # Check for OAuth override in step
        if "oauth_override" in step:
            oauth_override = step["oauth_override"]
            logger.info(f"  Using step-specific OAuth credentials (overriding environment defaults)")
            # Update OAuth config with override values
            if "auth" not in step_config:
                step_config["auth"] = {}
            if "oauth" not in step_config["auth"]:
                step_config["auth"]["oauth"] = {}
            step_config["auth"]["oauth"].update(oauth_override)
        
        # Check for header exclusions in step
        exclude_headers = step.get("exclude_headers", [])
        if exclude_headers:
            logger.info(f"  Excluding headers: {', '.join(exclude_headers)}")
            custom_headers = step_config.get("environment", {}).get("custom_headers", {}).copy()
            for header in exclude_headers:
                custom_headers.pop(header, None)
            if "environment" not in step_config:
                step_config["environment"] = {}
            step_config["environment"]["custom_headers"] = custom_headers
        
        # Execute or simulate
        if self.dry_run:
            logger.info(f"  [DRY RUN] Would execute: {method} {endpoint}")
            if payload:
                logger.debug(f"  Payload: {payload}")
            # For dry-run, create mock response data that looks like actual API response
            response_data = {
                "dry_run": True,
                "mock_data": {
                    "id": "mock_id_12345",
                    "status": "success",
                    "timestamp": self.execution_state["timestamp"],
                    "data": [
                        {
                            "id": f"item_{i}",
                            "name": f"Item {i}",
                            "status": "active"
                        } for i in range(3)
                    ]
                }
            }
        elif skip_only_api:
            # Skip API call but create mock response with the transformed payload
            logger.info(f"  [SKIP API] Processing data transformations without making API call")
            response_data = payload  # Save the transformed payload directly
        else:
            # Make actual API call (dual or single environment)
            if self.dual_client and target == "source":
                response = self.dual_client.make_request(
                    method=method,
                    endpoint=endpoint,
                    target="source",
                    payload=payload,
                    path_params=self.execution_state
                )
            elif self.dual_client and target == "destination":
                response = self.dual_client.make_request(
                    method=method,
                    endpoint=endpoint,
                    target="destination",
                    payload=payload,
                    path_params=self.execution_state
                )
            else:
                response = self.api_client.make_request(
                    method=method,
                    endpoint=endpoint,
                    payload=payload,
                    path_params=self.execution_state
                )
            
            response_data = response.json() if response.text else {}
            
            # Validate response
            if "validate_response" in step:
                self._validate_response(response, response_data, step["validate_response"])
        
        # Save response data to state
        if "save_response" in step:
            save_key = step["save_response"]
            # For dry-run, save mock data; for real, save from response
            if self.dry_run:
                # Save the full mock_data structure (not just wrapper)
                self.execution_state[save_key] = response_data.get("mock_data", {})
                logger.info(f"  Saved to state (dry-run): {save_key}")
                logger.debug(f"  Data saved: {self.execution_state[save_key]}")
            else:
                # For real API calls, save the entire response as the data
                self.execution_state[save_key] = response_data
                logger.info(f"  Saved to state: {save_key}")
                logger.debug(f"  Available keys in execution_state: {list(self.execution_state.keys())}")
                
                # Extract nested values for common patterns
                self._extract_nested_values(save_key, response_data)
            
            # Save response to file in run folder
            self._save_response_to_file(step.get("id", "unknown"), save_key, response_data)
        
        # Retry logic for specific steps
        if step.get("retry_on_failure", False) and not self.dry_run:
            self._retry_step_if_needed(step, response_data)
        
        logger.info(f"  ✓ Step completed: {step_name}")
    
    def _check_dependencies(self, dependencies: List[str]):
        """Verify all dependencies are satisfied"""
        missing = [dep for dep in dependencies if dep not in self.completed_steps]
        if missing:
            raise OrchestrationError(
                f"Unmet dependencies: {', '.join(missing)}"
            )
    
    def _build_payload(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Build request payload from template"""
        template_name = step["payload_template"]
        template = self.config_loader.get_payload_template(template_name)
        
        # Resolve placeholders in template
        payload = self._resolve_payload_placeholders(template)
        return payload
    
    def _resolve_placeholders(self, text: str) -> str:
        """Replace placeholders with actual values"""
        result = text
        
        # Replace environment name
        result = result.replace("{env_name}", self.environment.upper())
        
        # Handle CSV row data with {{COLUMN_NAME}} syntax (double curly braces)
        if "csv_row" in self.execution_state:
            csv_row = self.execution_state["csv_row"]
            import re
            # Pattern for {{COLUMN_NAME}}
            csv_pattern = r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}'
            csv_matches = re.findall(csv_pattern, result)
            for column_name in csv_matches:
                if column_name in csv_row:
                    csv_value = csv_row[column_name]
                    result = result.replace(f"{{{{{column_name}}}}}", str(csv_value))
                    logger.info(f"  Resolved CSV placeholder {{{{{column_name}}}}} = {csv_value}")
                else:
                    logger.warning(f"  CSV column '{column_name}' not found in row data")
        
        # Replace state values with JSON path support
        for key, value in self.execution_state.items():
            # Skip csv_row from simple replacement (already handled above)
            if key == "csv_row":
                continue
            # Simple placeholder without path
            result = result.replace(f"{{{key}}}", str(value))
        
        # Handle JSON path references like {response_key.data[0].fieldName}
        import re
        # Pattern: {base_key followed by one or more of (.field or [index])}
        path_pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)((?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])+)\}'
        matches = re.findall(path_pattern, result)
        logger.debug(f"  JSON path regex matches: {matches}")
        logger.debug(f"  Available execution_state keys: {list(self.execution_state.keys())}")
        for base_key, json_path in matches:
            logger.debug(f"  Processing JSON path: base_key='{base_key}', json_path='{json_path}'")
            if base_key in self.execution_state:
                try:
                    value = self._resolve_json_path(self.execution_state[base_key], json_path)
                    logger.info(f"  Resolved JSON path {{{base_key}{json_path}}} = {value}")
                    result = result.replace(f"{{{base_key}{json_path}}}", str(value))
                except Exception as e:
                    logger.warning(f"  Could not resolve JSON path {{{base_key}{json_path}}}: {str(e)}")
            else:
                logger.warning(f"  Key '{base_key}' not found in execution_state")
        
        return result
    
    def _resolve_json_path(self, data: Any, path: str) -> Any:
        """Resolve a JSON path like .[0].publicKey or .data[0].publicKey"""
        import re
        current = data
        
        # Split path into segments (.[0], .publicKey, [0], etc.)
        segments = re.findall(r'\.([^\[\].]+)|\[(\d+)\]', path)
        
        for dict_key, list_index in segments:
            if dict_key:  # Dictionary access like .publicKey
                if isinstance(current, dict):
                    current = current.get(dict_key)
                else:
                    raise ValueError(f"Expected dict for key '{dict_key}', got {type(current)}")
            elif list_index:  # List access like [0]
                # Check if current is a dict with empty string key (common in MAWM APIs)
                if isinstance(current, dict) and "" in current:
                    current = current[""][int(list_index)]
                elif isinstance(current, list):
                    current = current[int(list_index)]
                else:
                    raise ValueError(f"Expected list for index [{list_index}], got {type(current)}")
        
        return current
    
    def _resolve_payload_placeholders(self, payload: Any) -> Any:
        """Recursively resolve placeholders in payload"""
        if isinstance(payload, dict):
            return {k: self._resolve_payload_placeholders(v) for k, v in payload.items()}
        elif isinstance(payload, list):
            return [self._resolve_payload_placeholders(item) for item in payload]
        elif isinstance(payload, str):
            return self._resolve_placeholders(payload)
        else:
            return payload
    
    def _transform_payload_data(self, payload: Any, transform_config: Dict[str, Any]) -> Any:
        """Transform payload data based on configuration"""
        import copy
        import os
        transformed_payload = copy.deepcopy(payload)
        
        # Handle attribute replacements
        if "attribute_replacements" in transform_config:
            replacements = transform_config["attribute_replacements"]
            
            # Get target location from config
            target_location = None
            target_username = None
            if self.env_config:
                target_location = self.env_config.get("environment", {}).get("custom_headers", {}).get("Location")
                target_username = self.env_config.get("auth", {}).get("oauth", {}).get("username")
            
            # Add placeholders to state for resolution
            temp_state = {
                "target_location": target_location or self.environment.upper(),
                "source_location": self.source_config.get("environment", {}).get("custom_headers", {}).get("Location") if self.source_config else None,
                "user_name": target_username or os.getenv("USER") or os.getenv("USERNAME") or os.getenv("MAWM_USERNAME") or "system"
            }
            
            transformed_payload = self._apply_attribute_replacements(
                transformed_payload, 
                replacements, 
                temp_state
            )
            
            logger.debug(f"  Attribute replacements applied: {replacements}")
        
        return transformed_payload
    
    def _apply_attribute_replacements(self, data: Any, replacements: Dict[str, str], placeholders: Dict[str, str]) -> Any:
        """Recursively apply attribute replacements in nested structures"""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # Check if this key should be replaced
                if key in replacements:
                    new_value = replacements[key]
                    # Resolve placeholders in replacement value
                    for placeholder_key, placeholder_value in placeholders.items():
                        if placeholder_value:
                            new_value = new_value.replace(f"{{{placeholder_key}}}", str(placeholder_value))
                    result[key] = new_value
                    logger.debug(f"    Replaced {key}: {value} -> {new_value}")
                else:
                    result[key] = self._apply_attribute_replacements(value, replacements, placeholders)
            return result
        elif isinstance(data, list):
            return [self._apply_attribute_replacements(item, replacements, placeholders) for item in data]
        else:
            return data
    
    def _validate_response(self, response, response_data: Dict[str, Any], validation_rules: Dict[str, Any]):
        """Validate API response against rules"""
        # Validate status code
        if "status_code" in validation_rules:
            self.validator.validate_status_code(
                response.status_code,
                validation_rules["status_code"]
            )
        
        # Validate required fields
        if "required_fields" in validation_rules:
            self.validator.validate_required_fields(
                response_data,
                validation_rules["required_fields"]
            )
    
    def _retry_step_if_needed(self, step: Dict[str, Any], response_data: Dict[str, Any]):
        """Retry step if validation fails"""
        max_retries = step.get("max_retries", 3)
        retry_delay = step.get("retry_delay", 5)
        
        for attempt in range(1, max_retries + 1):
            if response_data.get("status") == "healthy":
                break
            
            logger.warning(f"  Retry {attempt}/{max_retries} after {retry_delay}s...")
            time.sleep(retry_delay)
            
            # Re-execute step
            response = self.api_client.make_request(
                method=step["method"],
                endpoint=self._resolve_placeholders(step["endpoint"]),
                path_params=self.execution_state
            )
            response_data = response.json() if response.text else {}
    
    def _save_response_to_file(self, step_id: str, save_key: str, response_data: Dict[str, Any]):
        """Save response data to a JSON file in the run folder"""
        try:
            response_file = self.run_folder / f"{save_key}.json"
            with open(response_file, 'w') as f:
                json.dump(response_data, f, indent=2, default=str)
            logger.info(f"  Response saved to file: {response_file}")
        except Exception as e:
            logger.warning(f"  Failed to save response to file: {str(e)}")

    def _save_request_payload(self, step_id: str, payload: Any):
        """Save request payload to a JSON file in the run folder"""
        try:
            requests_folder = self.run_folder / "requests"
            requests_folder.mkdir(parents=True, exist_ok=True)
            payload_file = requests_folder / f"{step_id}_payload.json"
            with open(payload_file, 'w') as f:
                json.dump(payload, f, indent=2, default=str)
            logger.info(f"  Request payload saved to file: {payload_file}")
        except Exception as e:
            logger.warning(f"  Failed to save request payload to file: {str(e)}")

    def _load_response_from_file(self, step_id: str, save_key: str) -> Optional[Dict[str, Any]]:
        """Load cached response data from a JSON file in the run folder"""
        try:
            response_file = self.run_folder / f"{save_key}.json"
            if not response_file.exists():
                return None
            with open(response_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"  Failed to load cached response from file: {str(e)}")
            return None
    
    def _delete_response_file(self, step_id: str, save_key: str):
        """Delete cached response file from the run folder"""
        try:
            response_file = self.run_folder / f"{save_key}.json"
            if response_file.exists():
                response_file.unlink()
                logger.debug(f"  Deleted cached file: {response_file}")
        except Exception as e:
            logger.warning(f"  Failed to delete cached file: {str(e)}")
    
    def _extract_nested_values(self, base_key: str, data: Dict[str, Any]):
        """Extract common nested values from response and add to execution_state"""
        try:
            # Handle array responses with empty string key (common in MAWM APIs)
            if "" in data and isinstance(data[""], list) and len(data[""]) > 0:
                first_item = data[""][0]
                # Extract publicKey if present
                if "publicKey" in first_item:
                    extracted_key = f"{base_key.replace('_result', '')}_publicKey"
                    self.execution_state[extracted_key] = first_item["publicKey"]
                    logger.debug(f"  Extracted nested value: {extracted_key}")
        except Exception as e:
            logger.debug(f"  Could not extract nested values: {str(e)}")
    
    def _execute_rollback(self):
        """Execute rollback sequence on failure"""
        logger.warning("\nInitiating rollback sequence...")
        
        rollback_config = self.sequence_config.get("rollback", {})
        cleanup_endpoints = rollback_config.get("cleanup_endpoints", [])
        
        for cleanup in reversed(cleanup_endpoints):
            try:
                endpoint = self._resolve_placeholders(cleanup["endpoint"])
                method = cleanup["method"]
                
                logger.info(f"  Rollback: {method} {endpoint}")
                
                if not self.dry_run:
                    self.api_client.make_request(
                        method=method,
                        endpoint=endpoint,
                        path_params=self.execution_state
                    )
            except Exception as e:
                logger.error(f"  Rollback failed: {str(e)}")
        
        logger.info("Rollback sequence completed")
