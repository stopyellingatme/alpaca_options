# Project Development Context

@Context.md

> **IMPORTANT: API Credentials Already Configured**
>
> The Alpaca API credentials are already set up in the `.env` file in the project root. DO NOT ask the user to configure API keys or create a `.env` file - it already exists and contains valid credentials. All scripts automatically load these credentials using `python-dotenv`.

# Alpaca Options Trading Bot

An intelligent, automated options trading system that identifies and executes high-probability trades using the Alpaca API. The system combines technical analysis, options screening, and risk management to find optimal trade opportunities across multiple strategies tailored to different account sizes.

## Overview

This trading bot is designed to automate options trading with multiple strategies including **credit spreads** (theta decay) and **debit spreads** (directional plays with lower capital requirements). The system:

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

### Debit Spreads (MEDIUM Tier - $10k+)
**Bull Call Spreads** and **Bear Put Spreads** - Directional strategies for accounts with sufficient capital.

- **Capital Requirement**: **$10,000 minimum** - ITM/near-money options cost $1,100-$1,900 per spread
- **Why $10k?**: 25% position limit requires $2,500 available to execute typical debit spreads
- **Entry Criteria**:
  - Buy 55-75 delta (ITM/near-money), Sell 25-45 delta (OTM)
  - 21-60 DTE, IV rank > 15
  - RSI-based direction: ≤50 = oversold = bullish (buy call spread), ≥50 = overbought = bearish (buy put spread)
  - Max debit capped at 70% of spread width
  - Minimum debit $20 to ensure meaningful profit potential
- **Exit Rules**:
  - Profit target: Close at 50% of max profit
  - Stop loss: Close at 200% of debit paid (2x initial cost)
  - DTE exit: Close at 21 DTE to avoid gamma risk
- **Risk/Reward**: Directional conviction plays with defined max loss
- **Best For**: Traders with $10,000+ accounts who want directional exposure with strong technical signals
- **Note**: Validated via backtesting - requires adequate position sizing to execute reliably

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
| **LOW** | $2k-$10k | Vertical Spreads (Credit Spreads) | Proven +367% returns, 92.6% win rate |
| **MEDIUM** | $10k-$50k | + Debit Spreads, Iron Condors | Add directional and neutral strategies |
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

# Run a backtest (credit spreads)
uv run alpaca-options backtest --strategy vertical_spread --symbol QQQ --capital 5000

# Run a backtest (debit spreads - lower capital requirement)
uv run alpaca-options backtest --strategy debit_spread --symbol QQQ --capital 2000

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

## Configuration Files & Naming Conventions

**IMPORTANT**: Always use generic configuration names. Never name configs, engines, or scripts after specific stocks.

### File Structure

**Config Files** (2 total):
- `config/default.yaml` - System defaults and strategy configurations
- `config/paper_trading.yaml` - Paper trading configuration (generic, works for any underlying)

**Launch Method** (1 primary script):
```bash
uv run python scripts/run_paper_trading.py -d -s -u options_friendly
```

### Naming Rules

✅ **DO** use generic names:
- `config/paper_trading.yaml` - Good (generic)
- `config/production.yaml` - Good (generic)
- `scripts/run_paper_trading.py` - Good (generic)

❌ **DON'T** use stock-specific names:
- ~~`config/paper_qqq.yaml`~~ - Bad (stock-specific)
- ~~`config/spy_config.yaml`~~ - Bad (stock-specific)
- ~~`scripts/run_qqq_bot.py`~~ - Bad (stock-specific)

### Adapting Configs for Different Underlyings

To trade different stocks, edit the `underlyings` list in `config/paper_trading.yaml`:

```yaml
# For QQQ only
underlyings:
  - "QQQ"

# For multiple symbols
underlyings:
  - "QQQ"
  - "SPY"
  - "IWM"
```

The screener can also discover opportunities dynamically:
```bash
# Scan S&P 500 universe
uv run python scripts/run_paper_trading.py -d -s -u sp500

# Scan options-friendly stocks
uv run python scripts/run_paper_trading.py -d -s -u options_friendly
```

## Configuration Sections

Main config: `config/default.yaml`

Key sections:
- `alpaca`: API settings, paper/live mode
- `trading`: Max positions, buying power reserve, order settings
- `risk`: Portfolio Greeks limits, DTE range, position sizing
- `capital_tiers`: Strategy enablement by capital level
- `strategies`: Per-strategy configuration
- `backtesting`: Slippage, commissions, data settings
- `screener`: Dynamic opportunity discovery settings

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

### Running Backtests
```bash
# Vertical spreads (credit spreads)
uv run alpaca-options backtest --strategy vertical_spread --symbol QQQ --capital 5000 --start 2024-02-01 --end 2024-11-30

# Debit spreads
uv run alpaca-options backtest --strategy debit_spread --symbol QQQ --capital 10000 --start 2024-02-01 --end 2024-11-30

# Comprehensive backtest script (with detailed analysis)
uv run python scripts/comprehensive_backtest.py
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

## Code Quality & Maintenance

### Codebase Health Status

**Current Grade**: A- (Excellent)
**Last Updated**: December 15, 2024

The codebase has undergone systematic cleanup and refactoring:
- **Phase 1 & 2 Complete**: Removed 12 obsolete files (2,279 lines), reorganized 11 files into proper structure
- **Phase 3A Complete**: Refactored core backtesting engine using Extract Method pattern
- **Validation**: 6-year comprehensive backtest (2019-2024) confirms refactored code works correctly

### Refactoring Methodology

The project follows **Extract Method** refactoring pattern (Martin Fowler's "Refactoring") combined with **Single Responsibility Principle (SRP)**:

**Clean Code Guidelines**:
- Methods should not exceed 150 lines
- Each method should have one well-defined purpose
- Comprehensive documentation with detailed docstrings
- Full type annotations for all parameters and return values
- Zero behavior changes (pure structural refactoring)

### Backtesting Engine Refactoring (Phase 3A)

**File**: `src/alpaca_options/backtesting/engine.py` (1,467 lines)

Three large methods were refactored to improve maintainability:

#### 1. `run()` Method
- **Before**: 177 lines (mixed initialization, simulation, finalization)
- **After**: 25 lines (86% reduction)
- **Extracted helpers**:
  - `_initialize_backtest()` - Setup phase
  - `_process_timestamp()` - Core simulation loop
  - `_finalize_backtest()` - Results calculation

#### 2. `_execute_signal()` Method
- **Before**: ~185 lines (mixed fillability checks, execution, recording)
- **After**: 19 lines (90% reduction)
- **Extracted helpers**:
  - `_check_order_fillability()` - 108 lines (Phase 2A fill probability model + legacy liquidity checks)
  - `_execute_and_record_trade()` - 103 lines (slippage, commission, trade recording)

#### 3. `_process_positions()` Method
- **Before**: 174 lines (mixed profit/loss checks, expiration, assignment, gap risk)
- **After**: 47 lines (73% reduction)
- **Extracted helpers**:
  - `_check_profit_loss_dte_exits()` - 70 lines (profit targets, stop losses, DTE checks)
  - `_check_expiration_and_assignment()` - 65 lines (expiration and early assignment risk)
  - `_calculate_gap_risk_adjustment()` - 68 lines (overnight gap risk simulation)

### Validation Results

**6-Year Backtest** (2019-2024, post-refactoring):
- **Total trades**: 801 across 4 symbols (SPY, AAPL, MSFT, NVDA)
- **Average return**: +211.09%
- **Average Sharpe ratio**: 3.53
- **Average win rate**: 82.9%
- **Average max drawdown**: 9.68%

**Confirmed**: Refactored code maintains identical functionality with zero behavior changes.

### Benefits Realized

1. **Improved Testability**: Each extracted method can be unit tested independently
2. **Better Readability**: Main methods now read like high-level documentation
3. **Easier Maintenance**: Changes to specific functionality are isolated to single methods
4. **Clear Separation of Concerns**: Each method has one well-defined responsibility
5. **No Performance Impact**: Pure structural changes with zero behavior modification

### Development Workflow

When adding new features or modifying existing code:

1. **Follow Clean Code Principles**: Keep methods under 150 lines, single responsibility
2. **Add Type Hints**: Full type annotations on all functions
3. **Document Thoroughly**: Comprehensive docstrings explaining purpose, parameters, returns
4. **Test Before Commit**: Run validation scripts to ensure no breakage
5. **Preserve Git History**: Use `git mv` for file reorganization

**Validation Scripts**:
```bash
# Quick validation (single symbol, 4 years)
uv run python scripts/validation/walk_forward_final.py --quick

# Full validation (all symbols, 4 years)
uv run python scripts/validation/walk_forward_final.py

# Comprehensive 6-year backtest
uv run python scripts/backtest_optimized_config.py
```

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

6. **Backtesting engine architecture**: The engine uses extracted helper methods for better maintainability. Core methods (`run()`, `_execute_signal()`, `_process_positions()`) delegate to focused helper methods with single responsibilities.
