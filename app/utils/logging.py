"""
Logging Configuration

Centralized logging setup using loguru.
"""
import sys
from loguru import logger
from app.config import settings

# Remove default handler
logger.remove()

# Console handler
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL,
)

# File handler
logger.add(
    settings.LOG_FILE_PATH,
    rotation=settings.LOG_ROTATION,
    retention=settings.LOG_RETENTION,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level=settings.LOG_LEVEL,
)

# Export logger
__all__ = ["logger"]
