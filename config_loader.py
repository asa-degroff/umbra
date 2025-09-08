"""
Configuration loader for Void Bot.
Loads configuration from config.yaml and environment variables.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ConfigLoader:
    """Configuration loader that handles YAML config files and environment variables."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the configuration loader.
        
        Args:
            config_path: Path to the YAML configuration file
        """
        self.config_path = Path(config_path)
        self._config = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please copy config.yaml.example to config.yaml and configure it."
            )
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration file: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation (e.g., 'letta.api_key')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_with_env(self, key: str, env_var: str, default: Any = None) -> Any:
        """
        Get configuration value, preferring environment variable over config file.
        
        Args:
            key: Configuration key in dot notation
            env_var: Environment variable name
            default: Default value if neither found
            
        Returns:
            Value from environment variable, config file, or default
        """
        # First try environment variable
        env_value = os.getenv(env_var)
        if env_value is not None:
            return env_value
        
        # Then try config file
        config_value = self.get(key)
        if config_value is not None:
            return config_value
        
        return default
    
    def get_required(self, key: str, env_var: Optional[str] = None) -> Any:
        """
        Get a required configuration value.
        
        Args:
            key: Configuration key in dot notation
            env_var: Optional environment variable name to check first
            
        Returns:
            Configuration value
            
        Raises:
            ValueError: If required value is not found
        """
        if env_var:
            value = self.get_with_env(key, env_var)
        else:
            value = self.get(key)
        
        if value is None:
            source = f"config key '{key}'"
            if env_var:
                source += f" or environment variable '{env_var}'"
            raise ValueError(f"Required configuration value not found: {source}")
        
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get an entire configuration section.
        
        Args:
            section: Section name
            
        Returns:
            Dictionary containing the section
        """
        return self.get(section, {})
    
    def setup_logging(self) -> None:
        """Setup logging based on configuration."""
        logging_config = self.get_section('logging')
        
        # Set root logging level
        level = logging_config.get('level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Set specific logger levels
        loggers = logging_config.get('loggers', {})
        for logger_name, logger_level in loggers.items():
            logger_obj = logging.getLogger(logger_name)
            logger_obj.setLevel(getattr(logging, logger_level))


# Global configuration instance
_config_instance = None

def get_config(config_path: str = "config.yaml") -> ConfigLoader:
    """
    Get the global configuration instance.
    
    Args:
        config_path: Path to configuration file (only used on first call)
        
    Returns:
        ConfigLoader instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader(config_path)
    return _config_instance

def reload_config() -> None:
    """Reload the configuration from file."""
    global _config_instance
    if _config_instance is not None:
        _config_instance._load_config()

def get_letta_config() -> Dict[str, Any]:
    """Get Letta configuration."""
    config = get_config()
    return {
        'api_key': config.get_required('letta.api_key'),
        'timeout': config.get('letta.timeout', 600),
        'project_id': config.get_required('letta.project_id'),
        'agent_id': config.get_required('letta.agent_id'),
    }

def get_bluesky_config() -> Dict[str, Any]:
    """Get Bluesky configuration, prioritizing config.yaml over environment variables."""
    config = get_config()
    return {
        'username': config.get_required('bluesky.username'),
        'password': config.get_required('bluesky.password'),
        'pds_uri': config.get('bluesky.pds_uri', 'https://bsky.social'),
    }

def get_bot_config() -> Dict[str, Any]:
    """Get bot behavior configuration."""
    config = get_config()
    return {
        'fetch_notifications_delay': config.get('bot.fetch_notifications_delay', 30),
        'max_processed_notifications': config.get('bot.max_processed_notifications', 10000),
        'max_notification_pages': config.get('bot.max_notification_pages', 20),
    }

def get_agent_config() -> Dict[str, Any]:
    """Get agent configuration."""
    config = get_config()
    return {
        'name': config.get('bot.agent.name', 'void'),
        'model': config.get('bot.agent.model', 'openai/gpt-4o-mini'),
        'embedding': config.get('bot.agent.embedding', 'openai/text-embedding-3-small'),
        'description': config.get('bot.agent.description', 'A social media agent trapped in the void.'),
        'max_steps': config.get('bot.agent.max_steps', 100),
        'blocks': config.get('bot.agent.blocks', {}),
    }

def get_threading_config() -> Dict[str, Any]:
    """Get threading configuration."""
    config = get_config()
    return {
        'parent_height': config.get('threading.parent_height', 40),
        'depth': config.get('threading.depth', 10),
        'max_post_characters': config.get('threading.max_post_characters', 300),
    }

def get_queue_config() -> Dict[str, Any]:
    """Get queue configuration."""
    config = get_config()
    return {
        'priority_users': config.get('queue.priority_users', ['cameron.pfiffer.org']),
        'base_dir': config.get('queue.base_dir', 'queue'),
        'error_dir': config.get('queue.error_dir', 'queue/errors'),
        'no_reply_dir': config.get('queue.no_reply_dir', 'queue/no_reply'),
        'processed_file': config.get('queue.processed_file', 'queue/processed_notifications.json'),
    }
