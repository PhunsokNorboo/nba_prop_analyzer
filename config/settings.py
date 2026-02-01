"""
Application settings using Pydantic Settings.
Load configuration from environment variables and .env file.
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the project root directory (where .env lives)
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # API Keys
    odds_api_key: Optional[str] = None

    # Ollama Settings (local LLM)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 120  # seconds

    # Email Configuration
    email_enabled: bool = False  # Set to True to enable email delivery
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""  # Gmail app password
    email_recipient: str = ""
    email_from_name: str = "NBA Prop Analyzer"

    # Analysis Settings
    min_odds: int = -140  # No props with odds worse than this
    max_picks: int = 4    # Output exactly this many picks (or fewer if not enough quality)
    min_minutes_threshold: float = 24.0  # Minimum average minutes for consideration
    min_minutes_last_n: int = 5  # Games to check for minutes stability

    # Time Windows for Stats
    recent_games_window: int = 5     # "Current form"
    medium_games_window: int = 10    # "Direction"
    extended_games_window: int = 15  # "Extended sample"

    # Edge Discovery Thresholds
    min_edge_strength: float = 0.5   # Minimum strength (0-1) to consider an edge
    injury_impact_threshold: float = 15.0  # Min usage% of injured player to trigger edge

    # Rate Limiting (seconds between API calls)
    nba_api_delay: float = 0.6
    odds_api_delay: float = 1.0
    scrape_delay: float = 2.0

    # Caching TTL (seconds)
    cache_stats_ttl: int = 14400     # 4 hours for player/team stats
    cache_props_ttl: int = 1800      # 30 minutes for prop lines
    cache_injuries_ttl: int = 3600   # 1 hour for injury reports
    cache_schedule_ttl: int = 86400  # 24 hours for schedule data

    # Scheduler Settings
    analysis_hour: int = 10  # Run at 10 AM
    analysis_minute: int = 0
    analysis_timezone: str = "America/New_York"

    # LLM Generation Settings
    llm_max_tokens: int = 1500
    llm_temperature: float = 0.7  # Slightly higher for Llama

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/nba_props.log"

    # Prop Types to Analyze (can be overridden via env)
    allowed_prop_types: List[str] = [
        "points",
        "rebounds",
        "assists",
        "threes",
        "pts_rebs_asts",
        "pts_asts",
        "pts_rebs",
        "rebs_asts",
        "double_double"
    ]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
