"""
Logging configuration for MAWM automation
"""
import logging
import os
from datetime import datetime
from pathlib import Path
import colorlog


class AutomationLogger:
    """Centralized logging for automation tasks"""
    
    def __init__(self, log_dir: str = "logs", log_level: str = "INFO"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """Configure logging with file and console handlers"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create logger
        self.logger = logging.getLogger("MAWMAutomation")
        self.logger.setLevel(self.log_level)
        self.logger.handlers.clear()
        
        # Console handler with colors
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler - all logs
        all_logs_file = self.log_dir / f"automation_{timestamp}.log"
        file_handler = logging.FileHandler(all_logs_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # File handler - errors only
        error_logs_file = self.log_dir / f"errors_{timestamp}.log"
        error_handler = logging.FileHandler(error_logs_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
        
        self.logger.info(f"Logging initialized - Logs: {all_logs_file}")
    
    def get_logger(self) -> logging.Logger:
        """Get the configured logger instance"""
        return self.logger
    
    def log_api_call(self, method: str, endpoint: str, status_code: int = None, duration: float = None):
        """Log API call details"""
        msg = f"API Call: {method} {endpoint}"
        if status_code:
            msg += f" | Status: {status_code}"
        if duration:
            msg += f" | Duration: {duration:.2f}s"
        self.logger.info(msg)
    
    def log_step_start(self, step_name: str, step_id: str):
        """Log the start of a sequence step"""
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Starting Step: {step_name} (ID: {step_id})")
        self.logger.info(f"{'='*60}")
    
    def log_step_complete(self, step_name: str, success: bool = True):
        """Log the completion of a sequence step"""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"Step Complete: {step_name} - {status}")
        self.logger.info(f"{'-'*60}")


# Singleton instance
_logger_instance = None

def get_logger() -> logging.Logger:
    """Get or create the singleton logger instance"""
    global _logger_instance
    if _logger_instance is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")
        _logger_instance = AutomationLogger(log_level=log_level)
    return _logger_instance.get_logger()
