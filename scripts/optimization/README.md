# Strategy Optimization Scripts

This directory contains scripts for systematically optimizing the vertical spread strategy parameters using historical data and rigorous backtesting.

## Philosophy

**Evidence-Based Optimization**: All parameter changes must be validated through historical backtesting across multiple market cycles. We optimize for:

1. **Risk-Adjusted Returns** (Primary): Sharpe ratio > 2.0
2. **Drawdown Control** (Secondary): Max drawdown < -12%
3. **Win Rate** (Tertiary): Win rate > 80%
4. **Capital Efficiency** (Quaternary): More trades with maintained quality

## Baseline Performance

From 6-year backtest (2019-2024) on AAPL, MSFT, NVDA, SPY:
- **Average Return**: +174.95% total (+25.38% annualized)
- **Average Win Rate**: 75.3%
- **Average Sharpe**: 1.97
- **Average Max Drawdown**: -14.51%

## Optimization Scripts

### Phase 1: Parameter Grid Search

#### optimize_delta.py
Tests different delta targets (0.15, 0.18, 0.20, 0.22, 0.25) to balance premium captured vs probability of success.

**Usage**:
```bash
# Full 6-year test on all symbols
uv run python scripts/optimize_delta.py

# Quick 2-year test (2023-2024)
uv run python scripts/optimize_delta.py --quick

# Single symbol test
uv run python scripts/optimize_delta.py --symbol AAPL
uv run python scripts/optimize_delta.py --symbol SPY --quick
```

**What it optimizes**:
- Higher delta = More premium, lower win rate
- Lower delta = Less premium, higher win rate
- Find optimal balance for each symbol

**Expected runtime**:
- Quick mode (~2 years): 30-45 minutes per symbol
- Full mode (~6 years): 2-3 hours per symbol
- All 4 symbols, full mode: 8-12 hours total

---

#### optimize_dte.py
Tests different DTE (Days To Expiration) entry and exit ranges.

**Usage**:
```bash
# Full 6-year test on all symbols
uv run python scripts/optimize_dte.py

# Quick 2-year test
uv run python scripts/optimize_dte.py --quick

# Single symbol test
uv run python scripts/optimize_dte.py --symbol SPY
```

**What it optimizes**:
- Entry ranges: (14-30), (21-45), (30-60) DTE
- Exit DTEs: 7, 14, 21 days
- Tests all valid combinations (9 total per symbol)

**Trade-offs**:
- Shorter DTE = More trades, faster capital rotation
- Longer DTE = More theta decay captured
- Earlier exit = Less gamma risk

**Expected runtime**:
- Quick mode: 1-2 hours per symbol (9 combinations)
- Full mode: 6-8 hours per symbol
- All 4 symbols, full mode: 24-32 hours total

---

#### optimize_exits.py (TODO)
Tests different profit target and stop loss combinations.

**Planned tests**:
- Profit targets: 40%, 50%, 60%, 75%
- Stop losses: 1.5x, 2.0x, 2.5x, 3.0x credit
- 16 combinations per symbol

**Usage** (when implemented):
```bash
uv run python scripts/optimize_exits.py --quick
```

---

#### optimize_entries.py (TODO)
Tests different entry signal thresholds and filters.

**Planned tests**:
- RSI thresholds: (40,60), (45,55), (48,52)
- Additional filters: MACD confirmation, volume, trend alignment
- IV rank minimum (currently 0 for DoltHub compatibility)

---

### Phase 2: Symbol-Specific Optimization

#### optimize_per_symbol.py (TODO)
Runs comprehensive optimization for each symbol to find symbol-specific optimal parameters.

**Rationale**: Different symbols have different characteristics:
- AAPL: Exceptional win rate (92.6%), might benefit from higher delta
- MSFT: Good but improvable, might benefit from tighter stops
- SPY: Most consistent, current params working well
- NVDA: Volatile, might benefit from lower delta or stricter filters

---

### Phase 3: Market Regime Detection

#### detect_market_regime.py (TODO)
Classifies market conditions (bull/bear, high/low volatility) and applies regime-specific parameters.

**Market Regimes**:
1. **Bull + Low Vol**: Favor bull put spreads, tighter params
2. **Bear + High Vol**: Favor bear call spreads, wider stops
3. **High Volatility**: Be selective, capture high premiums
4. **Low Volatility**: Standard approach

---

### Phase 4: Multi-Objective Optimization

#### bayesian_optimization.py (TODO)
Uses Bayesian optimization to efficiently explore parameter space and find global optimum.

**Multi-objective scoring**:
- 50% weight on Sharpe ratio
- 30% weight on drawdown
- 20% weight on win rate

Requires: `pip install scikit-optimize`

---

## Running Optimizations

### Quick Test (Recommended First)

Start with quick mode on a single symbol to validate everything works:

```bash
# Test delta optimization on SPY (2023-2024, ~30 min)
uv run python scripts/optimize_delta.py --symbol SPY --quick
```

### Full Optimization Workflow

1. **Delta Optimization** (8-12 hours):
   ```bash
   uv run python scripts/optimize_delta.py > logs/optimize_delta.log 2>&1
   ```

2. **DTE Optimization** (24-32 hours):
   ```bash
   uv run python scripts/optimize_dte.py > logs/optimize_dte.log 2>&1
   ```

3. **Exit Optimization** (12-16 hours, when implemented):
   ```bash
   uv run python scripts/optimize_exits.py > logs/optimize_exits.log 2>&1
   ```

4. **Analyze Results**: Review logs and tables to identify improvements

5. **Update Configuration**: Apply optimized parameters to `config/paper_trading.yaml`

6. **Validate**: Run multi-symbol backtest with new parameters

7. **Paper Trade**: Test in paper trading for 2-4 weeks before live

---

## Output Format

All optimization scripts output:

1. **Progress**: Real-time status during execution
2. **Results Table**: Comparison of all tested parameters
3. **Best Performers**: Top results by different metrics
4. **Recommendations**: Actionable suggestions for config updates
5. **Improvement**: Percentage improvement vs baseline

Example output:
```
AAPL Results:
┌────────┬──────────────┬────────┬───────────┬────────┬───────────┬──────────────┐
│ Delta  │ Total Return │ Sharpe │ Win Rate  │ Trades │   Max DD  │ Profit Factor│
├────────┼──────────────┼────────┼───────────┼────────┼───────────┼──────────────┤
│  0.15  │   +289.45%   │  3.92  │   95.2%   │   24   │  -10.31%  │    28.45     │
│  0.18  │   +342.18%   │  4.28  │   93.8%   │   26   │  -11.02%  │    30.12     │
│ 0.20*  │   +367.16%   │  4.71  │   92.6%   │   27   │  -12.42%  │    32.13     │
│  0.22  │   +381.24%   │  4.58  │   90.9%   │   28   │  -13.58%  │    29.67     │
│  0.25  │   +358.91%   │  4.12  │   87.5%   │   30   │  -15.42%  │    24.89     │
└────────┴──────────────┴────────┴───────────┴────────┴───────────┴──────────────┘

  ✓ Best Sharpe: delta=0.20 (Sharpe 4.71)
  ✓ Best Win Rate: delta=0.15 (95.2%)
  ✓ Best Return: delta=0.22 (+381.24%)

Recommendations:
✓ AAPL: Current delta=0.20 is optimal
```

---

## Validation and Safety

### Overfitting Prevention

1. **Train/Test Split**: Optimize on 2019-2022, validate on 2023-2024
2. **Walk-Forward Analysis**: Test on rolling windows
3. **Out-of-Sample**: Always validate on unseen data
4. **Multiple Metrics**: Don't optimize for single metric
5. **Simplicity**: Prefer simple params over complex combinations

### Rollback Criteria

Revert to baseline if optimized strategy shows:
- Sharpe ratio < 1.50 (worse than baseline 1.97)
- Win rate < 70% (worse than baseline 75.3%)
- Max drawdown > -20% (worse than baseline -14.51%)

### Paper Trading Gate

Before live trading:
1. Update paper trading config with optimized params
2. Monitor for 2-4 weeks
3. Validate actual vs expected performance
4. Check order execution, spread selection, exit triggers
5. Only proceed if paper trading matches backtest expectations

---

## Directory Structure

```
scripts/
├── optimization/
│   ├── README.md              # This file
│   ├── optimize_delta.py      # Delta target optimization
│   ├── optimize_dte.py        # DTE range optimization
│   ├── optimize_exits.py      # Profit/stop optimization (TODO)
│   ├── optimize_entries.py    # Entry signal optimization (TODO)
│   ├── optimize_per_symbol.py # Symbol-specific optimization (TODO)
│   ├── detect_market_regime.py # Regime detection (TODO)
│   └── bayesian_optimization.py # Multi-objective optimization (TODO)
├── backtest_multi_symbol.py   # Baseline backtest
├── download_extended_sample.py # Data downloader
└── check_dolthub_coverage.py  # Data availability checker

logs/
├── optimize_delta.log         # Delta optimization output
├── optimize_dte.log           # DTE optimization output
└── ...
```

---

## Performance Tips

1. **Use Quick Mode First**: Test with `--quick` flag (2 years) before full 6-year run
2. **Single Symbol Testing**: Use `--symbol SPY` to test one symbol first
3. **Run Overnight**: Full optimizations take hours, run overnight or on weekends
4. **Check DoltHub Cache**: Ensure chains are pre-downloaded with `download_extended_sample.py`
5. **Monitor Progress**: Scripts output real-time progress bars and status

---

## Next Steps

After completing Phase 1 optimizations:

1. **Review Results**: Analyze all optimization logs
2. **Identify Winners**: Find parameters that improve Sharpe > 5%
3. **Cross-Validate**: Test winning params on out-of-sample data
4. **Update Config**: Apply validated improvements to paper trading
5. **Document Changes**: Update `CONFIG_UPDATE_SUMMARY.md`
6. **Paper Trade**: Validate in paper trading environment
7. **Phase 2**: Proceed to symbol-specific optimization

---

## References

- **Baseline Report**: `../../EXTENDED_BACKTEST_REPORT.md`
- **Optimization Plan**: `../../STRATEGY_OPTIMIZATION_PLAN.md`
- **Config**: `../../config/paper_trading.yaml`
- **DoltHub Data**: Historical options 2019-2024

---

**Last Updated**: 2025-12-08
**Status**: Phase 1 scripts implemented (delta, DTE)
**Next**: Implement Phase 1 remaining scripts (exits, entries)
