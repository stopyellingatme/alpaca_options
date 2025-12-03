# Alpaca Options Trading Bot - Development Specification

## 1. Project Overview

### 1.1 Purpose
A Python-based automated options trading bot that integrates with Alpaca's trading API, featuring comprehensive backtesting capabilities, pluggable strategy architecture, and real-time terminal monitoring using Rich.

### 1.2 Core Technologies
- **Language**: Python 3.11+
- **Trading API**: Alpaca SDK (`alpaca-py`)
- **Terminal UI**: Rich (tables, live displays, progress bars)
- **Data Processing**: Pandas, NumPy
- **Backtesting**: Custom engine with vectorized operations
- **Configuration**: YAML/TOML with Pydantic validation
- **Testing**: pytest, pytest-asyncio
- **Async Runtime**: asyncio with aiohttp

### 1.3 Key Features
- Real-time options trading via Alpaca
- Modular strategy system with hot-swappable strategies
- Comprehensive backtesting with historical options data
- Live terminal dashboard with Rich
- Risk management and position sizing
- Performance analytics and reporting
- Paper trading support for strategy validation

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Terminal UI (Rich)                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐│
│  │ Live Quotes  │ │  Positions   │ │    P&L       │ │   Logs      ││
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Core Engine                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Trading Orchestrator                       │  │
│  │  - Event Loop Management                                      │  │
│  │  - Strategy Coordination                                      │  │
│  │  - Order Execution Pipeline                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Strategy Engine │  │  Risk Manager   │  │  Data Manager   │
│                 │  │                 │  │                 │
│ - Strategy Base │  │ - Position Limit│  │ - Market Data   │
│ - Signal Gen    │  │ - Greeks Limits │  │ - Options Chain │
│ - Entry/Exit    │  │ - Max Drawdown  │  │ - Historical    │
│ - Criteria Eval │  │ - Stop Loss     │  │ - Real-time     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Alpaca Integration Layer                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │  Trading Client │  │  Data Client    │  │  Options Client     │ │
│  │  - Orders       │  │  - Bars         │  │  - Chains           │ │
│  │  - Positions    │  │  - Quotes       │  │  - Greeks           │ │
│  │  - Account      │  │  - Trades       │  │  - Contracts        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Breakdown

#### 2.2.1 Terminal UI Layer
- **Live Dashboard**: Real-time display of positions, P&L, and market data
- **Strategy Monitor**: Active strategy status and signals
- **Order Book**: Pending and executed orders
- **Log Panel**: Scrolling log output with severity coloring
- **Performance Metrics**: Sharpe ratio, win rate, drawdown

#### 2.2.2 Core Engine
- **Trading Orchestrator**: Main event loop, coordinates all components
- **Event Bus**: Pub/sub system for decoupled communication
- **State Manager**: Tracks application state, positions, and orders

#### 2.2.3 Strategy Engine
- **Strategy Base Class**: Abstract interface for all strategies
- **Strategy Registry**: Dynamic loading and management
- **Signal Generator**: Produces buy/sell signals from strategies
- **Criteria Evaluator**: Filters signals based on configurable criteria

#### 2.2.4 Risk Manager
- **Position Sizing**: Kelly criterion, fixed fractional, volatility-based
- **Greeks Management**: Delta, gamma, theta, vega limits
- **Portfolio Risk**: Correlation analysis, sector exposure
- **Stop Loss/Take Profit**: Automated exit conditions

#### 2.2.5 Data Manager
- **Market Data Feed**: Real-time quotes and trades
- **Options Chain Manager**: Contract discovery and filtering
- **Historical Data**: OHLCV and options data storage
- **Data Normalization**: Consistent format across sources

---

## 3. Strategy System Design

### 3.1 Strategy Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime

class SignalType(Enum):
    BUY_CALL = "buy_call"
    BUY_PUT = "buy_put"
    SELL_CALL = "sell_call"
    SELL_PUT = "sell_put"
    SPREAD = "spread"
    NO_ACTION = "no_action"

@dataclass
class OptionSignal:
    signal_type: SignalType
    underlying: str
    strike: float
    expiration: datetime
    contracts: int
    confidence: float  # 0.0 - 1.0
    metadata: dict

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable strategy description."""
        pass

    @abstractmethod
    async def initialize(self, config: dict) -> None:
        """Initialize strategy with configuration."""
        pass

    @abstractmethod
    async def on_market_data(self, data: MarketData) -> Optional[OptionSignal]:
        """Process market data and optionally generate signal."""
        pass

    @abstractmethod
    async def on_option_chain(self, chain: OptionChain) -> Optional[OptionSignal]:
        """Process options chain data and optionally generate signal."""
        pass

    @abstractmethod
    def get_criteria(self) -> StrategyCriteria:
        """Return criteria this strategy uses for filtering."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        pass
```

### 3.2 Strategy Criteria System

```python
@dataclass
class StrategyCriteria:
    """Defines conditions under which a strategy should be active."""

    # Market conditions
    min_iv_rank: Optional[float] = None      # 0-100
    max_iv_rank: Optional[float] = None
    min_iv_percentile: Optional[float] = None
    max_iv_percentile: Optional[float] = None

    # Underlying conditions
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[int] = None
    min_market_cap: Optional[float] = None

    # Options-specific
    min_open_interest: Optional[int] = None
    min_bid_ask_spread: Optional[float] = None  # Max spread as %
    min_days_to_expiry: Optional[int] = None
    max_days_to_expiry: Optional[int] = None

    # Time-based
    trading_hours_only: bool = True
    allowed_days: list[int] = None  # 0=Monday, 4=Friday

    # Technical
    trend_direction: Optional[str] = None  # "bullish", "bearish", "neutral"
    min_atr_percentile: Optional[float] = None
```

### 3.3 Built-in Strategies

| Strategy | Description | Best Conditions |
|----------|-------------|-----------------|
| **CoveredCall** | Sell calls against long stock | Low IV, sideways market |
| **CashSecuredPut** | Sell puts with cash collateral | High IV, bullish bias |
| **IronCondor** | Neutral strategy, sell OTM call/put spreads | High IV, range-bound |
| **Straddle** | Buy ATM call and put | Low IV, expecting volatility |
| **VerticalSpread** | Bull/bear call or put spreads | Directional bias |
| **WheelStrategy** | CSP → Assignment → CC cycle | Income generation |
| **CalendarSpread** | Different expiration, same strike | IV term structure |
| **EarningsPlay** | Pre/post earnings volatility | Earnings events |

---

## 4. Backtesting Framework

### 4.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Backtesting Engine                              │
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │
│  │ Data Loader │───▶│ Event Sim   │───▶│ Strategy Executor       │ │
│  │             │    │             │    │                         │ │
│  │ - Historical│    │ - Time Sim  │    │ - Signal Generation     │ │
│  │ - Options   │    │ - Market    │    │ - Order Simulation      │ │
│  │ - Greeks    │    │   Events    │    │ - Position Tracking     │ │
│  └─────────────┘    └─────────────┘    └─────────────────────────┘ │
│         │                  │                       │                │
│         ▼                  ▼                       ▼                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Performance Analyzer                      │   │
│  │  - Returns Analysis    - Risk Metrics     - Trade Stats     │   │
│  │  - Drawdown Analysis   - Greeks P&L       - Strategy Compare│   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Backtesting Features

#### Data Requirements
- **Underlying**: OHLCV bars (1min to daily)
- **Options**: Strike, expiry, bid/ask, volume, open interest
- **Greeks**: Delta, gamma, theta, vega, rho (calculated or sourced)
- **Dividends/Splits**: Corporate action adjustments

#### Simulation Capabilities
- **Realistic Execution**: Slippage modeling, partial fills
- **Bid-Ask Spread**: Use mid, bid, or ask prices
- **Assignment Risk**: Early assignment simulation for American options
- **Expiration Handling**: Auto-exercise, pin risk
- **Margin Requirements**: Reg-T and portfolio margin

#### Performance Metrics
```python
@dataclass
class BacktestResults:
    # Returns
    total_return: float
    annualized_return: float
    daily_returns: pd.Series

    # Risk
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: timedelta
    volatility: float

    # Options-specific
    theta_pnl: float
    delta_pnl: float
    gamma_pnl: float
    vega_pnl: float

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float

    # Exposure
    avg_delta_exposure: float
    avg_theta_exposure: float
    max_margin_used: float
```

### 4.3 Backtest Configuration

```yaml
backtest:
  start_date: "2023-01-01"
  end_date: "2024-01-01"
  initial_capital: 100000

  execution:
    slippage_model: "percentage"  # percentage, fixed, volatility
    slippage_value: 0.001
    commission_per_contract: 0.65

  data:
    underlying_timeframe: "1h"
    options_snapshot_interval: "15min"
    use_adjusted_prices: true

  strategies:
    - name: "iron_condor"
      allocation: 0.5
      config:
        wing_width: 5
        delta_target: 0.16

    - name: "wheel"
      allocation: 0.5
      config:
        delta_target: 0.30
```

---

## 5. Terminal UI Design (Rich)

### 5.1 Dashboard Layout

```
╭─────────────────────────── Alpaca Options Bot ────────────────────────────╮
│ Status: 🟢 LIVE TRADING    Account: $125,432.50    Buying Power: $45,200  │
╰───────────────────────────────────────────────────────────────────────────╯

╭─ Active Positions ─────────────────────────────────────────────────────────╮
│ Symbol      │ Type │ Strike │ Exp     │ Qty │ Entry  │ Current │ P&L      │
│─────────────┼──────┼────────┼─────────┼─────┼────────┼─────────┼──────────│
│ AAPL 240119 │ PUT  │ 180.00 │ 15 DTE  │ -5  │ $3.45  │ $2.80   │ +$325.00 │
│ SPY 240112  │ CALL │ 475.00 │ 8 DTE   │ 10  │ $2.10  │ $2.45   │ +$350.00 │
│ TSLA 240126 │ IC   │ 240/250│ 22 DTE  │ 3   │ $4.20  │ $3.80   │ +$120.00 │
╰────────────────────────────────────────────────────────────────────────────╯

╭─ Strategy Status ──────────────────────╮ ╭─ Greeks Exposure ───────────────╮
│ Strategy       │ Status   │ Signals   │ │ Delta:  -245.3  │ Limit: ±500   │
│────────────────┼──────────┼───────────│ │ Gamma:   +12.4  │ Limit: ±50    │
│ WheelStrategy  │ 🟢 Active│ 2 pending │ │ Theta:  +$89.50 │ Target: +$100 │
│ IronCondor     │ 🟢 Active│ 1 pending │ │ Vega:   -$234   │ Limit: ±$500  │
│ EarningsPlay   │ 🟡 Idle  │ 0 pending │ ╰─────────────────────────────────╯
╰────────────────────────────────────────╯

╭─ Recent Orders ────────────────────────────────────────────────────────────╮
│ Time     │ Symbol       │ Side │ Qty │ Price  │ Status   │ Strategy       │
│──────────┼──────────────┼──────┼─────┼────────┼──────────┼────────────────│
│ 14:32:05 │ AAPL 240119P │ SELL │ 5   │ $3.45  │ FILLED   │ WheelStrategy  │
│ 14:28:12 │ SPY 240112C  │ BUY  │ 10  │ $2.10  │ FILLED   │ IronCondor     │
│ 14:15:00 │ TSLA 240126IC│ SELL │ 3   │ $4.20  │ FILLED   │ IronCondor     │
╰────────────────────────────────────────────────────────────────────────────╯

╭─ Performance ─────────────────────────╮ ╭─ Log ──────────────────────────────╮
│ Today:     +$795.00  (+0.63%)         │ │ 14:32:05 INFO  Order filled AAPL   │
│ Week:    +$2,340.00  (+1.89%)         │ │ 14:32:04 INFO  Signal: SELL PUT    │
│ Month:   +$5,432.50  (+4.52%)         │ │ 14:28:15 WARN  High IV detected    │
│ YTD:    +$25,432.50 (+25.43%)         │ │ 14:28:12 INFO  Order filled SPY    │
│                                       │ │ 14:15:01 INFO  IC opened TSLA      │
│ Sharpe: 2.34  │ Win Rate: 68%         │ │ 14:10:00 INFO  Market data updated │
╰───────────────────────────────────────╯ ╰────────────────────────────────────╯
```

### 5.2 UI Components

```python
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn

class TradingDashboard:
    """Rich-based terminal dashboard for trading bot."""

    def __init__(self):
        self.console = Console()
        self.layout = Layout()

    def create_layout(self) -> Layout:
        """Create the dashboard layout structure."""
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=10),
        )

        self.layout["main"].split_row(
            Layout(name="positions", ratio=2),
            Layout(name="sidebar", ratio=1),
        )

        self.layout["sidebar"].split(
            Layout(name="strategies"),
            Layout(name="greeks"),
        )

        self.layout["footer"].split_row(
            Layout(name="performance"),
            Layout(name="logs"),
        )

        return self.layout
```

---

## 6. Project Structure

```
alpaca_options/
├── pyproject.toml
├── README.md
├── DEVELOPMENT_SPEC.md
├── config/
│   ├── default.yaml           # Default configuration
│   ├── paper.yaml             # Paper trading config
│   └── live.yaml              # Live trading config
│
├── src/
│   └── alpaca_options/
│       ├── __init__.py
│       ├── main.py            # Entry point
│       ├── cli.py             # CLI argument parsing
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── engine.py      # Trading orchestrator
│       │   ├── events.py      # Event bus system
│       │   ├── state.py       # Application state
│       │   └── config.py      # Configuration loading
│       │
│       ├── alpaca/
│       │   ├── __init__.py
│       │   ├── client.py      # Alpaca API wrapper
│       │   ├── trading.py     # Order execution
│       │   ├── data.py        # Market data feeds
│       │   └── options.py     # Options-specific API
│       │
│       ├── strategies/
│       │   ├── __init__.py
│       │   ├── base.py        # BaseStrategy ABC
│       │   ├── registry.py    # Strategy discovery
│       │   ├── criteria.py    # Criteria evaluation
│       │   ├── covered_call.py
│       │   ├── cash_secured_put.py
│       │   ├── iron_condor.py
│       │   ├── wheel.py
│       │   ├── vertical_spread.py
│       │   └── earnings_play.py
│       │
│       ├── risk/
│       │   ├── __init__.py
│       │   ├── manager.py     # Risk management
│       │   ├── sizing.py      # Position sizing
│       │   ├── greeks.py      # Greeks calculations
│       │   └── limits.py      # Risk limits
│       │
│       ├── backtesting/
│       │   ├── __init__.py
│       │   ├── engine.py      # Backtest engine
│       │   ├── data_loader.py # Historical data
│       │   ├── simulator.py   # Market simulation
│       │   ├── analyzer.py    # Performance analysis
│       │   └── report.py      # Report generation
│       │
│       ├── data/
│       │   ├── __init__.py
│       │   ├── manager.py     # Data coordination
│       │   ├── options_chain.py
│       │   ├── market_data.py
│       │   └── storage.py     # Local data storage
│       │
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── dashboard.py   # Main Rich dashboard
│       │   ├── components.py  # Reusable UI components
│       │   ├── tables.py      # Table formatters
│       │   └── charts.py      # ASCII charts
│       │
│       └── utils/
│           ├── __init__.py
│           ├── logging.py     # Logging setup
│           ├── dates.py       # Date utilities
│           └── calculations.py # Financial math
│
├── tests/
│   ├── conftest.py
│   ├── test_strategies/
│   ├── test_backtesting/
│   ├── test_risk/
│   └── test_integration/
│
└── data/
    ├── historical/            # Cached historical data
    ├── backtest_results/      # Saved backtest results
    └── logs/                  # Application logs
```

---

## 7. Implementation Phases

### Phase 1: Foundation (Core Infrastructure)
- [ ] Project setup (pyproject.toml, dependencies)
- [ ] Configuration system with Pydantic
- [ ] Logging infrastructure with Rich integration
- [ ] Alpaca client wrapper (authentication, basic calls)
- [ ] Basic CLI interface

### Phase 2: Data Layer
- [ ] Market data streaming from Alpaca
- [ ] Options chain retrieval and parsing
- [ ] Greeks calculation (Black-Scholes, or use Alpaca's)
- [ ] Historical data storage (SQLite/Parquet)
- [ ] Data normalization utilities

### Phase 3: Strategy Framework
- [ ] BaseStrategy abstract class
- [ ] Strategy registry with dynamic loading
- [ ] Criteria evaluation system
- [ ] Signal generation pipeline
- [ ] Implement 2-3 core strategies (Wheel, Iron Condor, Vertical Spread)

### Phase 4: Risk Management
- [ ] Position sizing algorithms
- [ ] Portfolio Greeks tracking
- [ ] Risk limit enforcement
- [ ] Stop loss / take profit automation
- [ ] Margin requirement calculation

### Phase 5: Backtesting Engine
- [ ] Historical data loader
- [ ] Event-driven simulation engine
- [ ] Order execution simulation
- [ ] Performance metrics calculation
- [ ] Report generation

### Phase 6: Trading Engine
- [ ] Order execution pipeline
- [ ] Position management
- [ ] Real-time P&L tracking
- [ ] Event bus for component communication
- [ ] Paper trading mode

### Phase 7: Terminal UI
- [ ] Dashboard layout with Rich
- [ ] Live position display
- [ ] Strategy status panels
- [ ] Order book view
- [ ] Performance metrics display
- [ ] Log panel with filtering

### Phase 8: Testing & Polish
- [ ] Unit tests for all components
- [ ] Integration tests with paper trading
- [ ] Performance optimization
- [ ] Documentation
- [ ] Error handling and recovery

---

## 8. Dependencies

```toml
[project]
name = "alpaca-options-bot"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "alpaca-py>=0.21.0",        # Alpaca SDK
    "rich>=13.7.0",              # Terminal UI
    "pandas>=2.1.0",             # Data manipulation
    "numpy>=1.26.0",             # Numerical computing
    "pydantic>=2.5.0",           # Configuration validation
    "pydantic-settings>=2.1.0",  # Settings management
    "aiohttp>=3.9.0",            # Async HTTP
    "python-dateutil>=2.8.0",    # Date utilities
    "pytz>=2024.1",              # Timezone support
    "pyyaml>=6.0.0",             # YAML config files
    "scipy>=1.11.0",             # Scientific computing (BS model)
    "sqlalchemy>=2.0.0",         # Database ORM
    "aiosqlite>=0.19.0",         # Async SQLite
    "typer>=0.9.0",              # CLI framework
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "mypy>=1.8.0",
    "ruff>=0.1.0",
    "black>=24.1.0",
]

backtest = [
    "pyarrow>=14.0.0",           # Parquet support
    "plotly>=5.18.0",            # Interactive charts
]
```

---

## 9. Configuration Schema

```yaml
# config/default.yaml

app:
  name: "Alpaca Options Bot"
  log_level: "INFO"
  timezone: "America/New_York"

alpaca:
  paper: true                    # Use paper trading
  api_key: "${ALPACA_API_KEY}"
  api_secret: "${ALPACA_SECRET_KEY}"
  data_feed: "iex"               # "iex" or "sip"

trading:
  enabled: true
  max_positions: 10
  max_order_value: 5000
  trading_hours_only: true

risk:
  max_portfolio_delta: 500
  max_portfolio_gamma: 50
  max_portfolio_vega: 1000
  min_portfolio_theta: -200
  max_drawdown_percent: 15
  max_single_position_percent: 10

strategies:
  wheel:
    enabled: true
    allocation: 0.4
    config:
      underlyings: ["AAPL", "MSFT", "GOOGL"]
      delta_target: 0.30
      min_premium: 100
      min_dte: 21
      max_dte: 45

  iron_condor:
    enabled: true
    allocation: 0.3
    config:
      underlyings: ["SPY", "QQQ"]
      wing_width: 5
      delta_target: 0.16
      min_iv_rank: 30

  vertical_spread:
    enabled: true
    allocation: 0.3
    config:
      max_spread_width: 5
      min_probability_otm: 0.65

ui:
  refresh_rate: 1.0              # seconds
  show_greeks: true
  log_lines: 10
```

---

## 10. API Reference

### 10.1 Key Alpaca Options Endpoints

```python
# Options contracts discovery
GET /v2/options/contracts
    ?underlying_symbols=AAPL,MSFT
    &expiration_date_gte=2024-01-01
    &expiration_date_lte=2024-03-01
    &strike_price_gte=150
    &strike_price_lte=200
    &type=call|put

# Get specific contract
GET /v2/options/contracts/{symbol_or_contract_id}

# Options quotes (market data)
GET /v1/options/quotes/latest
    ?symbols=AAPL240119C00180000

# Options trades
GET /v1/options/trades/latest
    ?symbols=AAPL240119C00180000

# Place options order
POST /v2/orders
{
    "symbol": "AAPL240119C00180000",
    "qty": "1",
    "side": "buy",
    "type": "limit",
    "time_in_force": "day",
    "limit_price": "3.50"
}
```

---

## 11. Success Criteria

### Functional Requirements
- [ ] Execute options trades via Alpaca API
- [ ] Support at least 5 distinct options strategies
- [ ] Backtest strategies with historical data
- [ ] Real-time terminal monitoring
- [ ] Configurable risk limits
- [ ] Paper trading validation

### Non-Functional Requirements
- [ ] < 100ms latency for order submission
- [ ] Handle 1000+ options contracts in chain
- [ ] 24/7 stability for live trading
- [ ] < 5% CPU usage during idle
- [ ] Comprehensive test coverage (>80%)

---

## 12. Risk Considerations

### Technical Risks
- **API Rate Limits**: Implement exponential backoff
- **Data Quality**: Validate all incoming data
- **Network Failures**: Graceful degradation, reconnection logic
- **State Corruption**: Transaction-based state updates

### Trading Risks
- **Assignment Risk**: Monitor ITM options near expiry
- **Liquidity Risk**: Check bid-ask spreads before orders
- **Gap Risk**: Weekend/overnight exposure limits
- **Margin Calls**: Real-time margin monitoring

---

*Document Version: 1.0*
*Created: 2024*
*Last Updated: 2024*
