# Alpaca Options Trading Bot

An intelligent, automated options trading system that identifies and executes high-probability trades using the Alpaca API. The system combines technical analysis, options screening, and risk management to find optimal trade opportunities across multiple strategies tailored to different account sizes.

## Overview

This trading bot is designed to automate options trading with a focus on **credit spread strategies** that benefit from time decay (theta). The system:

1. **Screens for Opportunities** - Uses technical indicators (RSI, moving averages) and options metrics (IV rank, liquidity) to identify favorable setups
2. **Selects Appropriate Strategies** - Automatically enables strategies based on your account capital tier
3. **Manages Risk** - Enforces position limits, Greeks constraints, and automatic profit/loss exits
4. **Executes Trades** - Places multi-leg options orders via Alpaca's API
5. **Monitors Positions** - Tracks open positions and closes them based on profit targets, stop losses, or DTE thresholds

## Trading Strategies

### Vertical Spreads (LOW Tier - $2k+)
**Bull Put Spreads** and **Bear Call Spreads** - Credit spreads with defined risk.

- **Entry Criteria**: 20 delta short strike (~80% probability OTM), 30-45 DTE, IV rank > 30
- **Direction**: RSI oversold (< 45) triggers bullish, RSI overbought (> 55) triggers bearish
- **Exit Rules**:
  - Profit target: Close at 50% of max profit
  - Stop loss: Close at 2x credit received
  - DTE exit: Close at 21 DTE to avoid gamma risk
- **Risk/Reward**: Credit should be ~25% of spread width (e.g., $125 credit on $500 risk)

### Iron Condors (MEDIUM Tier - $10k+)
Neutral strategy selling both put and call spreads simultaneously.

- **Entry Criteria**: 16 delta wings, 21-45 DTE, IV rank > 20
- **Best For**: Range-bound markets with elevated implied volatility
- **Risk/Reward**: Collects premium from both sides, profits if underlying stays between strikes

### Wheel Strategy (HIGH Tier - $50k+)
Cash-secured puts leading to covered calls if assigned.

- **Entry Criteria**: 30 delta puts on quality stocks you'd own, 21-45 DTE
- **Flow**: Sell CSP → Get assigned → Sell covered calls → Get called away → Repeat
- **Capital Requirement**: Must have cash to buy 100 shares if assigned

## Capital Tiers

The system automatically enables strategies based on your account equity:

| Tier | Capital Range | Available Strategies | Description |
|------|--------------|---------------------|-------------|
| **MICRO** | $0-$2k | None | Account too small for options |
| **LOW** | $2k-$10k | Vertical Spreads | Defined-risk spreads only |
| **MEDIUM** | $10k-$50k | + Iron Condors | Add neutral strategies |
| **HIGH** | $50k-$100k | + Wheel, CSP | Full strategy access |
| **PREMIUM** | $100k+ | All + Diversification | Multi-strategy portfolio |

## Dynamic Screener

The optional screener module continuously scans for trading opportunities:

- **Technical Screening**: RSI extremes, moving average alignment, volume analysis
- **Options Screening**: IV rank, bid-ask spreads, open interest, expiration availability
- **Hybrid Mode**: Combines technical and options metrics for a weighted score
- **Universe Options**: S&P 500, NASDAQ 100, options-friendly stocks, ETFs

Enable with: `uv run python scripts/run_paper_trading.py --screener --universe options_friendly`

## Position Management

The live trading engine includes automatic position management:

- **Profit Targets**: Closes positions when profit reaches target (e.g., 50% of max)
- **Stop Losses**: Closes positions when loss exceeds threshold (e.g., 2x credit)
- **DTE Exits**: Closes positions approaching expiration to avoid gamma risk
- **Sync with Broker**: Monitors actual Alpaca positions every 60 seconds

## Quick Start (UV Package Manager)

This project uses [UV](https://docs.astral.sh/uv/) for fast, reliable Python package management.

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync project dependencies (creates .venv automatically)
uv sync

# Set environment variables (or use .env file)
export ALPACA_API_KEY=your_key
export ALPACA_SECRET_KEY=your_secret

# Run the CLI
uv run alpaca-options --help

# Run the bot (paper trading)
uv run alpaca-options run --paper

# Run a backtest
uv run alpaca-options backtest --strategy vertical_spread --symbol QQQ --capital 5000

# Run paper trading script directly
uv run python scripts/run_paper_trading.py
```

### Alternative: pip install (legacy)

```bash
# Install dependencies with pip
pip install -e ".[dev,backtest]"
```

## Project Architecture

```
src/alpaca_options/
├── alpaca/              # Alpaca API integration
│   ├── client.py        # Main Alpaca client wrapper
│   ├── trading.py       # Order execution and management
│   ├── data.py          # Market data streaming
│   └── options.py       # Options-specific API calls
├── backtesting/         # Backtesting framework
│   ├── engine.py        # Backtest engine (runs strategy on historical data)
│   ├── data_loader.py   # Load historical data (Alpaca + synthetic)
│   └── alpaca_options_fetcher.py  # Fetch historical options data
├── core/
│   ├── engine.py        # Live trading engine orchestrator
│   ├── config.py        # Configuration loading (Settings, RiskConfig, etc.)
│   ├── events.py        # Event bus for component communication
│   └── capital_manager.py  # Capital tier management
├── risk/
│   └── manager.py       # Risk checks (position sizing, Greeks limits, DTE)
├── strategies/
│   ├── base.py          # BaseStrategy ABC, OptionSignal, MarketData, OptionChain
│   ├── vertical_spread.py  # Bull put / bear call spreads (LOW tier)
│   ├── iron_condor.py   # Iron condor strategy (MEDIUM tier)
│   ├── wheel.py         # Wheel strategy (HIGH tier)
│   ├── criteria.py      # Strategy filtering criteria
│   └── registry.py      # Strategy registration system
├── data/
│   └── manager.py       # Market data subscription manager
├── ui/
│   └── dashboard.py     # Rich terminal UI dashboard
├── utils/
│   └── greeks.py        # Black-Scholes Greeks calculation
└── cli.py               # Typer CLI entry point
```

## Key Classes

### BaseStrategy (`strategies/base.py`)
All strategies inherit from this abstract class:
- `on_market_data(MarketData)` - Process price/indicator updates
- `on_option_chain(OptionChain)` - Generate signals from options chains
- `get_criteria()` - Return filtering criteria

### OptionSignal (`strategies/base.py`)
Trade signal with legs:
```python
OptionSignal(
    signal_type=SignalType.SELL_PUT_SPREAD,
    underlying="QQQ",
    legs=[OptionLeg(...), OptionLeg(...)],
    confidence=0.8,
    strategy_name="vertical_spread"
)
```

### BacktestEngine (`backtesting/engine.py`)
Runs strategies on historical data:
```python
result = await engine.run(
    strategy=strat,
    underlying_data=underlying_data,
    options_data=options_data,  # Dict[datetime, OptionChain]
    start_date=start,
    end_date=end,
)
```

## Configuration

Main config: `config/default.yaml`

Key sections:
- `alpaca`: API settings, paper/live mode
- `trading`: Max positions, buying power reserve, order settings
- `risk`: Portfolio Greeks limits, DTE range, position sizing
- `capital_tiers`: Strategy enablement by capital level
- `strategies`: Per-strategy configuration
- `backtesting`: Slippage, commissions, data settings

## Development

### Running Tests
```bash
uv run pytest tests/
```

### Code Quality
```bash
uv run ruff check src/
uv run mypy src/
```

### Running Backtests with Alpaca Data
```bash
source .env && uv run python scripts/run_low_tier_debug.py
```

### Adding Dependencies
```bash
# Add a production dependency
uv add package-name

# Add a dev dependency
uv add --group dev package-name

# Update lock file after changes
uv lock
```

## Environment Variables

Required:
- `ALPACA_API_KEY` - Your Alpaca API key
- `ALPACA_SECRET_KEY` - Your Alpaca secret key

## Important Implementation Notes

1. **MarketData symbol handling**: The backtest engine passes `chain.underlying` to `_get_market_data()` because underlying price data doesn't have a symbol column.

2. **RSI calculation**: First ~14 bars have NaN RSI values (indicator needs history). Strategy handles this gracefully.

3. **Synthetic options data**: When real Alpaca options data isn't available (pre-Feb 2024), the system generates synthetic chains using Black-Scholes pricing.

4. **Strategy signal flow**:
   - Strategy receives `MarketData` via `on_market_data()`
   - Strategy stores indicator values keyed by symbol
   - Strategy receives `OptionChain` via `on_option_chain()`
   - Strategy determines direction (bullish/bearish) from stored indicators
   - Strategy generates `OptionSignal` if conditions met

5. **Risk checks happen in sequence**:
   1. Max concurrent positions
   2. Buying power / margin requirements
   3. RiskManager validation (DTE, Greeks, position size %)
