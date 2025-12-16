"""Configuration management with Pydantic validation."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AlpacaConfig(BaseModel):
    """Alpaca API configuration."""

    model_config = {"populate_by_name": True}

    paper: bool = True
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    data_feed: str = "iex"
    base_url: Optional[str] = None


class TradingConfig(BaseModel):
    """Trading configuration."""

    enabled: bool = True
    dry_run: bool = False  # If True, generate signals but don't submit orders
    max_positions: int = 10
    max_concurrent_positions: int = 3  # Max positions open at same time
    max_order_value: float = 5000
    max_trading_capital: Optional[float] = None  # Cap on capital to use (None = use full account)
    trading_hours_only: bool = True
    order_timeout_seconds: int = 30
    default_order_type: str = "limit"
    limit_price_buffer: float = 0.02
    min_buying_power_reserve: float = 0.20  # Keep 20% cash reserve


class RiskConfig(BaseModel):
    """Risk management configuration."""

    max_portfolio_delta: float = 500
    max_portfolio_gamma: float = 50
    max_portfolio_vega: float = 1000
    min_portfolio_theta: float = -200
    max_drawdown_percent: float = 15
    daily_loss_limit: float = 1000
    max_single_position_percent: float = 10
    max_contracts_per_trade: int = 10
    min_days_to_expiry: int = 7
    max_days_to_expiry: int = 60
    min_open_interest: int = 100
    max_bid_ask_spread_percent: float = 5


class StrategyConfig(BaseModel):
    """Individual strategy configuration."""

    enabled: bool = False
    allocation: float = 0.0
    config: dict[str, Any] = Field(default_factory=dict)


class BacktestExecutionConfig(BaseModel):
    """Backtest execution settings."""

    slippage_model: str = "realistic"  # realistic, percentage, fixed, volatility
    slippage_value: float = 0.02  # Base slippage for percentage/fixed models
    commission_per_contract: float = 0.65
    # Realistic model parameters
    gap_risk_probability: float = 0.015  # 1.5% daily chance of adverse gap
    gap_severity_min: float = 0.20  # Gaps move position 20-50% against you
    gap_severity_max: float = 0.50
    early_assignment_threshold: float = 0.90  # ITM > 90% triggers assignment risk
    liquidity_rejection_rate: float = 0.05  # 5% of trades rejected for liquidity


class BacktestDataConfig(BaseModel):
    """Backtest data settings."""

    underlying_timeframe: str = "1h"
    options_snapshot_interval: str = "15min"
    use_adjusted_prices: bool = True
    cache_enabled: bool = True
    cache_dir: str = "./data/historical"


class BacktestConfig(BaseModel):
    """Backtesting configuration."""

    default_start_date: str = "2023-01-01"
    default_end_date: str = "2024-01-01"
    initial_capital: float = 100000
    execution: BacktestExecutionConfig = Field(default_factory=BacktestExecutionConfig)
    data: BacktestDataConfig = Field(default_factory=BacktestDataConfig)


class UIPanelsConfig(BaseModel):
    """UI panel visibility configuration."""

    positions: bool = True
    orders: bool = True
    strategies: bool = True
    greeks: bool = True
    performance: bool = True
    logs: bool = True


class UIConfig(BaseModel):
    """Terminal UI configuration."""

    refresh_rate: float = 1.0
    show_greeks: bool = True
    show_performance: bool = True
    log_lines: int = 10
    theme: str = "default"
    panels: UIPanelsConfig = Field(default_factory=UIPanelsConfig)


class LoggingConfig(BaseModel):
    """Logging configuration."""

    console_level: str = "INFO"
    file_level: str = "DEBUG"
    log_file: str = "./data/logs/trading.log"
    max_file_size_mb: int = 10
    backup_count: int = 5


class ScreenerCriteriaConfig(BaseModel):
    """Screening criteria configuration."""

    # Price filters
    min_price: float = 10.0
    max_price: float = 500.0

    # Volume filters
    min_volume: int = 500_000
    min_dollar_volume: float = 10_000_000.0

    # Technical filters
    rsi_oversold: Optional[float] = 30.0
    rsi_overbought: Optional[float] = 70.0
    rsi_period: int = 14

    # Options filters
    min_option_volume: int = 1000
    min_open_interest: int = 500
    max_bid_ask_spread_percent: float = 5.0
    min_expirations: int = 3


class ScreenerConfig(BaseModel):
    """Stock screener configuration."""

    enabled: bool = False
    mode: str = "hybrid"  # "technical_only", "options_only", "hybrid"
    universe: str = "options_friendly"  # "sp500", "nasdaq100", "options_friendly", "etfs", "custom"
    custom_symbols: list[str] = Field(default_factory=list)
    max_results: int = 20
    min_combined_score: float = 50.0
    technical_weight: float = 0.5
    options_weight: float = 0.5
    require_options: bool = True
    require_signal: bool = False
    auto_refresh_seconds: int = 300
    cache_ttl_seconds: int = 300
    criteria: ScreenerCriteriaConfig = Field(default_factory=ScreenerCriteriaConfig)


class AppConfig(BaseModel):
    """Application configuration."""

    name: str = "Alpaca Options Bot"
    log_level: str = "INFO"
    timezone: str = "America/New_York"
    data_dir: str = "./data"


class Settings(BaseSettings):
    """Main settings class combining all configuration."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategies: dict[str, StrategyConfig] = Field(default_factory=dict)
    screener: ScreenerConfig = Field(default_factory=ScreenerConfig)
    backtesting: BacktestConfig = Field(default_factory=BacktestConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def get_enabled_strategies(self) -> dict[str, StrategyConfig]:
        """Get all enabled strategies."""
        return {k: v for k, v in self.strategies.items() if v.enabled}


def load_config(config_path: Optional[Path] = None) -> Settings:
    """Load configuration from YAML file and environment variables.

    Args:
        config_path: Path to YAML configuration file.
                    If None, looks for config/default.yaml.

    Returns:
        Validated Settings instance.
    """
    config_data: dict[str, Any] = {}

    # Determine config file path
    if config_path is None:
        # Look for config file in standard locations
        search_paths = [
            Path("config/default.yaml"),
            Path("config.yaml"),
            Path.home() / ".alpaca_options" / "config.yaml",
        ]
        for path in search_paths:
            if path.exists():
                config_path = path
                break

    # Load YAML config if found
    if config_path and config_path.exists():
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}

    # Override with environment variables for sensitive data
    if "alpaca" not in config_data:
        config_data["alpaca"] = {}

    config_data["alpaca"]["api_key"] = os.environ.get(
        "ALPACA_API_KEY", config_data.get("alpaca", {}).get("api_key", "")
    )
    config_data["alpaca"]["api_secret"] = os.environ.get(
        "ALPACA_SECRET_KEY", config_data.get("alpaca", {}).get("api_secret", "")
    )

    # Convert strategies dict format
    if "strategies" in config_data:
        strategies = {}
        for name, cfg in config_data["strategies"].items():
            strategies[name] = StrategyConfig(**cfg) if isinstance(cfg, dict) else cfg
        config_data["strategies"] = strategies

    return Settings(**config_data)


def save_config(settings: Settings, config_path: Path) -> None:
    """Save configuration to YAML file.

    Args:
        settings: Settings instance to save.
        config_path: Path to save the configuration.
    """
    # Convert to dict, excluding sensitive fields
    data = settings.model_dump(exclude={"alpaca": {"api_key", "api_secret"}})

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
