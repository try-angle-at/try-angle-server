"""
 Copyright (c) 2025. Ebee1205(wavicle) all rights reserved.

 The copyright of this software belongs to Ebee1205(wavicle).
 All rights reserved.
"""

"""
Application context and configuration management module.

This module provides centralized configuration loading, validation, and context
management for the TryAngle Web Server application. It handles logger setup,
database initialization, and service configuration through Pydantic models.

Typical usage:
    ctx = AppContext()
    ctx.load_config("config/tryangle_web_server.prod.cfg.json")
    ctx._init_logger()
    ctx._init_db()
"""

import orjson
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError

from src.modules import logger
from src.handler.db_handler import DBHandler


class LoggerConfig(BaseModel):
    """Logger configuration model.
    
    Attributes:
        level: Logging level (debug, info, warning, error, critical)
        path: File path pattern for log output (supports %DATE% placeholder)
        suffix: Date format suffix for log rotation (e.g., %Y-%m-%d)
        max_bytes: Maximum size of a single log file in bytes
        max_files: Maximum retention period (e.g., "3d" for 3 days)
        rotation: Rotation strategy (daily, midnight, etc.)
        use_console: Whether to also output logs to console
    """
    level: str
    path: str
    suffix: str
    max_bytes: int
    max_files: str
    rotation: str
    use_console: bool


class HTTPConfig(BaseModel):
    """HTTP/CORS configuration model.
    
    Attributes:
        allow_origins: List of allowed CORS origins
        allow_methods: List of allowed HTTP methods
        allow_headers: List of allowed HTTP headers
        allow_credentials: Whether to allow credentials in CORS
    """
    allow_origins: list[str]
    allow_methods: list[str]
    allow_headers: list[str]
    allow_credentials: bool


class DBConfig(BaseModel):
    """Database connection configuration model.
    
    Attributes:
        host: Database server hostname or IP address
        port: Database server port
        user: Database username
        password: Database password (optional, may come from token file)
        database: Database name to connect to
        charset: Character set for connection (default: utf8mb4)
        autocommit: Whether to automatically commit transactions
    """
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    charset: str = "utf8mb4"
    autocommit: bool = True


class R2Config(BaseModel):
    """Cloudflare R2 storage configuration model.
    
    Attributes:
        account_id: R2 bucket name or account identifier
        access_key_id: R2 API access key ID (typically loaded from token file)
        secret_access_key: R2 API secret key (typically loaded from token file)
        bucket_name: Target bucket name for file uploads
        region: AWS region code (default: auto)
        endpoint_url: R2 S3-compatible API endpoint URL
        public_base_url: Public CDN base URL for served files
        image_prefix: Prefix path for images within bucket
        upload_url_expire_seconds: Presigned URL expiration time
    """
    account_id: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    bucket_name: Optional[str] = None
    region: str = "auto"
    endpoint_url: Optional[str] = None
    public_base_url: Optional[str] = None
    image_prefix: str = "images"
    upload_url_expire_seconds: int = 900


class AppConfig(BaseModel):
    """Main application configuration model.
    
    Combines all subsystem configurations into a single validated configuration object.
    All settings are loaded from JSON and validated against this schema.
    
    Attributes:
        environment: Runtime environment (dev, staging, prod)
        project_name: Application project name identifier
        api_v1_str: API version prefix path (e.g., /api/v1)
        host: Server host binding address
        port: Server port number
        secret_key: JWT secret key for token signing
        access_token_expire_minutes: JWT token expiration time in minutes
        logger: Logger configuration
        http_config: HTTP/CORS configuration (optional)
        r2: Cloudflare R2 configuration (optional)
        db: Database configuration (optional)
        enable_monitoring: Enable system monitoring (default: True)
        monitoring_interval: System monitoring interval in seconds
    """
    environment: str
    project_name: str
    api_v1_str: str
    host: str
    port: int
    secret_key: str
    access_token_expire_minutes: int

    logger: LoggerConfig
    http_config: Optional[HTTPConfig] = None
    r2: Optional[R2Config] = None
    db: Optional[DBConfig] = None

    enable_monitoring: bool = True
    monitoring_interval: int = 10


class AppContext:
    """Centralized application context manager.
    
    Manages application lifecycle, configuration loading, and component initialization.
    Provides a singleton-like interface for accessing configuration and core services
    throughout the application.
    
    Attributes:
        cfg: Loaded application configuration (AppConfig instance)
        log: Configured logger instance
        db_handler: Database connection handler
    """

    def __init__(self) -> None:
        """Initialize empty application context."""
        self.cfg: Optional[AppConfig] = None
        self.log: Optional[logging.Logger] = None
        self.db_handler: Optional[DBHandler] = None

    def load_config(self, config_path: str) -> AppConfig:
        """Load and parse application configuration from JSON file.
        
        Args:
            config_path: Path to configuration JSON file
            
        Returns:
            Parsed AppConfig instance
            
        Raises:
            FileNotFoundError: If configuration file does not exist
            ValidationError: If configuration data fails validation
            orjson.JSONDecodeError: If JSON is malformed
            
        Example:
            >>> ctx = AppContext()
            >>> cfg = ctx.load_config("config/tryangle_web_server.prod.cfg.json")
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
            
            print(f"[CONFIG] Loading configuration from {config_path}")
            
            with open(config_file, "rb") as f:
                raw_config = orjson.loads(f.read())
            
            self.cfg = AppConfig(**raw_config)
            print(f"[CONFIG] Successfully loaded configuration for environment: {self.cfg.environment}")
            
            return self.cfg
            
        except FileNotFoundError as e:
            print(f"[ERROR] {str(e)}")
            raise
        except ValidationError as e:
            print(f"[ERROR] Configuration validation failed: {e}")
            raise
        except Exception as e:
            print(f"[ERROR] Unexpected error loading configuration: {e}")
            raise

    def load_json_map(self, name: str, path: str) -> bool:
        """Load arbitrary JSON file and register as context attribute.
        
        Dynamically loads and attaches JSON data to the context instance,
        allowing flexible configuration of application maps, events, etc.
        
        Args:
            name: Attribute name to store loaded data (e.g., "event_map")
            path: File path to JSON data
            
        Returns:
            True if loading succeeded, False otherwise
            
        Example:
            >>> ctx.load_json_map("event_map", "config/event_map.json")
            >>> event_map = ctx.event_map
        """
        try:
            json_file = Path(path)
            if not json_file.exists():
                raise FileNotFoundError(f"JSON map file not found: {path}")
            
            with open(json_file, "rb") as f:
                data = orjson.loads(f.read())

            setattr(self, name, data)
            print(f"[CONFIG] Successfully loaded JSON map '{name}' from {path}")
            return True
            
        except FileNotFoundError as e:
            print(f"[WARNING] {str(e)}")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load JSON map '{name}' from {path}: {e}")
            return False

    def load_token(self, token_path: str) -> bool:
        """Load sensitive token data and merge into configuration.
        
        Loads API credentials and secrets from a separate file for security,
        merging them into the existing configuration (typically R2 credentials).
        
        Args:
            token_path: Path to token JSON file
            
        Returns:
            True if loading succeeded, False otherwise
            
        Note:
            This method should be called after load_config() to merge tokens
            into the already-loaded configuration.
            
        Example:
            >>> ctx.load_config("config/tryangle_web_server.prod.cfg.json")
            >>> ctx.load_token("/etc/tryangle/tokens.json")
        """
        if not self.cfg:
            print("[ERROR] Configuration not loaded. Call load_config() first.")
            return False
            
        try:
            token_file = Path(token_path)
            if not token_file.exists():
                print(f"[WARNING] Token file not found: {token_path} (optional)")
                return False
            
            with open(token_file, "rb") as f:
                tokens = orjson.loads(f.read())

            # Merge R2 credentials
            if "r2" in tokens and self.cfg.r2:
                r2_tokens = tokens["r2"]
                if "access_key_id" in r2_tokens:
                    self.cfg.r2.access_key_id = r2_tokens["access_key_id"]
                if "secret_access_key" in r2_tokens:
                    self.cfg.r2.secret_access_key = r2_tokens["secret_access_key"]

            print(f"[CONFIG] Successfully loaded and merged tokens from {token_path}")
            return True
            
        except FileNotFoundError as e:
            print(f"[WARNING] {str(e)}")
            return False
        except ValidationError as e:
            print(f"[ERROR] Token validation failed: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load token from {token_path}: {e}")
            return False

    def _init_logger(self) -> None:
        """Initialize application logger from configuration.
        
        Sets up the logging system based on logger configuration settings,
        including file rotation, console output, and logging level.
        
        Raises:
            RuntimeError: If configuration not loaded or logger initialization fails
            
        Note:
            Must be called after load_config() to have valid configuration.
        """
        if not self.cfg:
            raise RuntimeError("Configuration not loaded. Call load_config() first.")
            
        try:
            print("[LOGGER] Initializing application logger")
            
            log_level = self.cfg.logger.level
            log_path = self.cfg.logger.path
            log_max_files = self.cfg.logger.max_files
            
            self.log = logger.setup_logger(log_level, log_path, log_max_files)
            self.log.debug("Logger initialization completed successfully")
            
        except Exception as e:
            print(f"[ERROR] Failed to initialize logger: {e}")
            raise

    def _init_db(self) -> None:
        """Initialize database handler from configuration.
        
        Creates and configures the database connection handler based on
        database configuration settings.
        
        Raises:
            RuntimeError: If configuration or logger not loaded
            Exception: If database initialization fails
            
        Note:
            Requires both load_config() and _init_logger() to be called first.
        """
        if not self.cfg:
            raise RuntimeError("Configuration not loaded. Call load_config() first.")
        if not self.log:
            raise RuntimeError("Logger not initialized. Call _init_logger() first.")
            
        try:
            self.log.debug("Initializing database handler")
            # DBHandler는 pymysql.connect(**config)로 풀어 쓰므로 dict를 넘긴다
            self.db_handler = DBHandler(self.cfg.db.model_dump())
            self.log.debug("Database handler initialized successfully")
            
        except Exception as e:
            self.log.error(f"Failed to initialize database handler: {e}", exc_info=True)
            raise

