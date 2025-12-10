# DoltHub Historical Options Data Setup

This guide explains how to use free historical options data from DoltHub for backtesting.

## Overview

**DoltHub Database**: `post-no-preference/options`
- **Coverage**: 2019-01-01 to 2024-12-31
- **Symbols**: 2,098 symbols (includes QQQ, SPY, major stocks/ETFs)
- **Cost**: Completely FREE
- **Data**: Options chains with Greeks, IV, bid/ask, volume, open interest

## Installation

### 1. Install Dolt CLI

**macOS (Homebrew)**:
```bash
brew install dolt
```

**Linux**:
```bash
sudo bash -c 'curl -L https://github.com/dolthub/dolt/releases/latest/download/install.sh | sudo bash'
```

**Windows**:
```bash
# Download installer from: https://github.com/dolthub/dolt/releases/latest
# Run the .msi installer
```

**Verify Installation**:
```bash
dolt version
```

### 2. Clone the DoltHub Options Database

The DoltHub fetcher will automatically clone the database on first use. However, you can manually clone it:

```bash
# Create data directory
mkdir -p data/dolthub

# Clone the options database (this will take a few minutes)
cd data/dolthub
dolt clone post-no-preference/options

# Verify the clone
cd options
dolt sql -q "SELECT COUNT(*) FROM option_chain"
```

**Database Size**: ~5-10 GB (depends on how much data you query)

### 3. Test the Integration

```bash
# Run the DoltHub backtest script
uv run python scripts/backtest_dolthub_options.py
```

## Usage

### Fetching Option Chains

```python
from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
from datetime import datetime

# Initialize fetcher
fetcher = DoltHubOptionsDataFetcher()

# Fetch option chain for a specific date
chain = fetcher.fetch_option_chain(
    underlying="QQQ",
    as_of_date=datetime(2024, 3, 15),
)

if chain:
    print(f"Loaded {len(chain.contracts)} contracts")
    print(f"Expirations: {sorted(set(c.expiration.date() for c in chain.contracts))}")
```

### Running Backtests

```python
from alpaca_options.backtesting import BacktestEngine
from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
from alpaca_options.strategies import VerticalSpreadStrategy
from datetime import datetime

# Initialize fetchers
dolthub_fetcher = DoltHubOptionsDataFetcher()
alpaca_fetcher = AlpacaOptionsDataFetcher(api_key=..., api_secret=...)

# Fetch underlying data (use Alpaca for this)
underlying_data = alpaca_fetcher.fetch_underlying_bars(
    symbol="QQQ",
    start_date=datetime(2024, 2, 1),
    end_date=datetime(2024, 11, 30),
    timeframe="1Hour",
)

# Fetch options chains (use DoltHub for historical chains)
options_data = {}
for date in daily_dates:
    chain = dolthub_fetcher.fetch_option_chain("QQQ", date)
    if chain:
        options_data[date] = chain

# Run backtest
strategy = VerticalSpreadStrategy()
engine = BacktestEngine(settings.backtesting, settings.risk)
result = await engine.run(
    strategy=strategy,
    underlying_data=underlying_data,
    options_data=options_data,
    start_date=start_date,
    end_date=end_date,
)
```

## DoltHub Schema

The `option_chain` table has the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `quote_date` | DATE | Date of the quote |
| `underlying_symbol` | VARCHAR | Underlying stock symbol |
| `expiration` | DATE | Option expiration date |
| `strike` | DECIMAL | Strike price |
| `option_type` | VARCHAR | 'CALL' or 'PUT' |
| `bid` | DECIMAL | Bid price |
| `ask` | DECIMAL | Ask price |
| `last` | DECIMAL | Last trade price |
| `volume` | INT | Daily volume |
| `open_interest` | INT | Open interest |
| `implied_volatility` | DECIMAL | Implied volatility |
| `delta` | DECIMAL | Delta Greek |
| `gamma` | DECIMAL | Gamma Greek |
| `theta` | DECIMAL | Theta Greek |
| `vega` | DECIMAL | Vega Greek |
| `rho` | DECIMAL | Rho Greek |

## Querying DoltHub Directly

You can query the database directly using Dolt SQL:

```bash
cd data/dolthub/options

# Get available dates for QQQ
dolt sql -q "SELECT DISTINCT quote_date FROM option_chain WHERE underlying_symbol = 'QQQ' ORDER BY quote_date LIMIT 10"

# Get contracts for a specific date
dolt sql -q "SELECT * FROM option_chain WHERE underlying_symbol = 'QQQ' AND quote_date = '2024-03-15' LIMIT 10"

# Count total contracts
dolt sql -q "SELECT underlying_symbol, COUNT(*) as count FROM option_chain GROUP BY underlying_symbol ORDER BY count DESC LIMIT 20"
```

## Advantages of DoltHub

✅ **Free**: No cost for historical data
✅ **Complete**: Full option chains with Greeks and IV
✅ **Reliable**: Version-controlled database (Git for data)
✅ **Local**: All queries run locally after clone
✅ **Historical**: True historical snapshots, not current data

## Limitations

❌ **No Underlying Prices**: DoltHub only has options data, use Alpaca for underlying price bars
❌ **Storage**: Database is ~5-10 GB
❌ **Clone Time**: Initial clone takes 5-10 minutes
❌ **Static**: Data only up to 2024-12-31 (not live)

## Troubleshooting

### "Dolt not found"
```bash
# Install Dolt CLI (see Installation section above)
brew install dolt
```

### "Failed to clone repository"
```bash
# Make sure you have internet connection
# Try cloning manually:
mkdir -p data/dolthub
cd data/dolthub
dolt clone post-no-preference/options
```

### "No data for symbol"
```bash
# Check available symbols:
cd data/dolthub/options
dolt sql -q "SELECT DISTINCT underlying_symbol FROM option_chain ORDER BY underlying_symbol"
```

### "Query timeout"
```bash
# Large queries may take time. Increase timeout or query smaller date ranges.
# The fetcher caches results to avoid re-querying.
```

## Next Steps

1. Install Dolt CLI
2. Run `uv run python scripts/backtest_dolthub_options.py` to test
3. Modify strategy parameters in the script
4. Run backtests on different symbols and date ranges

For more information, see:
- DoltHub Database: https://www.dolthub.com/repositories/post-no-preference/options
- Dolt Documentation: https://docs.dolthub.com/
