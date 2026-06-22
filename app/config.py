"""
Application Configuration

Settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    APP_NAME: str = "FastAPI Device Provisioning"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/device_provisioning"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_EXPIRE: int = 3600
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # Ansible
    ANSIBLE_PLAYBOOKS_DIR: str = "/app/ansible/playbooks"
    ANSIBLE_INVENTORY_FILE: str = "/app/ansible/inventory/hosts"
    ANSIBLE_LOG_PATH: str = "/app/logs/ansible.log"
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    # Logging
    LOG_FILE_PATH: str = "/app/logs/app.log"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    # Device Connection Defaults
    DEFAULT_SSH_PORT: int = 22
    DEFAULT_TELNET_PORT: int = 23
    DEFAULT_ROUTEROS_API_PORT: int = 8728
    DEFAULT_CONNECTION_TIMEOUT: int = 30
    
    # Security
    ENABLE_SSL_VERIFICATION: bool = False
    ENCRYPT_DEVICE_CREDENTIALS: bool = True
    CREDENTIAL_ENCRYPTION_KEY: str = "your-encryption-key-change-this"
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # RADIUS CoA (Change of Authorization)
    RADIUS_SERVER_IP: str = "10.42.4.19"
    RADIUS_COA_PORT: int = 3799
    RADIUS_SECRET: str = "ap0ll0"
    RADIUS_COA_ENABLED: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
