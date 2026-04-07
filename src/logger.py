from loguru import logger
import sys
from pathlib import Path

def setup_logging():
    """Configures the logging for the application."""
    log_path = Path("logs")
    log_path.mkdir(exist_ok=True)
    
    config = {
        "handlers": [
            {"sink": sys.stdout, "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"},
            {"sink": "logs/app.log", "serialize": True, "rotation": "10 MB", "retention": "10 days", "level": "DEBUG", "encoding": "utf-8"},
        ]
    }
    logger.configure(**config)
    logger.info("Logging initialized.")
