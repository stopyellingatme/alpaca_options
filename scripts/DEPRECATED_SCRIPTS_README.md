# Deprecated Scripts

## comprehensive_backtest.py.DEPRECATED

**Status**: DEPRECATED - DO NOT USE

**Reason**: This script uses synthetic options data generation, which has been removed from the codebase.

**Replacement**: Use real data backtests instead:
- `backtest_multi_symbol.py` - Multi-symbol backtest with DoltHub real data
- `backtest_dolthub_aapl.py` - Single-symbol backtest with DoltHub real data
- `backtest_dolthub_options.py` - DoltHub options backtest

**Available Real Data**:
- AAPL: 133 chain files (Feb 26 - Nov 29, 2024)
- MSFT: 133 chain files (Feb 26 - Nov 29, 2024)
- NVDA: 133 chain files (Feb 26 - Nov 29, 2024)
- SPY: 120 chain files (Feb 26 - Nov 29, 2024)

**Note**: All synthetic data generation has been removed from `src/alpaca_options/backtesting/data_loader.py`. Only real historical data is now supported.
