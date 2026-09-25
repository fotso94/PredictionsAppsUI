"""
Logging Configuration
Structured logging setup for the application
"""

import logging
import sys
import json
from datetime import datetime

from app.core.config import settings
from app.core.redaction import install_credential_redaction


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present. The redaction filter leaves the traceback it redacted
        # in exc_text; rendering it again from exc_info would print what it removed.
        if record.exc_info:
            log_data["exception"] = record.exc_text or self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        return json.dumps(log_data)


def setup_logging():
    """Configure application logging"""
    
    # Get log level from settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Set formatter based on settings
    if settings.LOG_FORMAT == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Set specific log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Provider credentials never reach the log: Live Score's travel in the query string, and httpx
    # logs every request URL. Everything reaching the root handler is redacted, and so is what
    # uvicorn's own handlers print, which it attached before this module was imported.
    uvicorn_handlers = [handler for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
                        for handler in logging.getLogger(name).handlers]
    install_credential_redaction([console_handler, *uvicorn_handlers])

    return root_logger

