# Paper Trading Configuration Update - Dec 2024

**Date**: 2025-12-08
**Purpose**: Align paper trading configuration with validated 6-year backtest results

---

## Executive Summary

The paper trading configuration has been updated to match the validated 6-year backtest parameters (2019-2024). This ensures the live trading system behaves consistently with the backtested strategy that demonstrated strong performance across multiple market cycles.

**Key Change**: Paper trading now uses **SPY** with validated parameters instead of QQQ with custom settings.

---

## Critical Changes

### 1. Symbol Change: QQQ → SPY

**Before**:
```yaml
underlyings:
  - "QQQ"  # Only QQQ for paper trading
```

**After**:
```yaml
underlyings:
  - "SPY"  # VALIDATED: +118.88% over 6 years, 78.6% win rate, 28 trades
```

**Rationale**:
- SPY has validated 6-year performance (+118.88%, 78.6% win rate)
- Most consistent performer across market cycles
- 28 trades executed in backtest (good sample size)
- QQQ was not tested in the 6-year backtest

### 2. Exit Timing Fix: close_dte 21 → 14 Days

**Before**:
```yaml
close_dte: 21  # Close at 21 DTE to avoid gamma risk
```

**After**:
```yaml
close_dte: 14  # CRITICAL FIX: Close at 14 DTE (was 21, backtest uses 14)
```

**Rationale**:
- **CRITICAL MISMATCH**: Paper trading was holding positions 7 days longer than backtest
- Backtest closes at 14 DTE to avoid gamma risk
- Holding to 21 DTE increases risk exposure beyond validated strategy

**Impact**: This is the most critical fix - ensures positions exit when expected.

---

## Parameter Alignment Changes

### 3. Entry Filters (More Opportunities)

| Parameter | Before (Paper) | After (Backtest) | Change |
|-----------|---------------|------------------|---------|
| **min_credit** | $30 | $15 | ✓ More opportunities |
| **min_dte** | 30 days | 21 days | ✓ Wider entry window |
| **min_iv_rank** | 30 | 0 | ✓ Removed filter |
| **max_spread_percent** | 5% | 15% | ✓ Allow wider spreads |
| **min_return_on_risk** | 25% (0.25) | 8% (0.08) | ✓ More realistic |
| **min_open_interest** | 100 | 0 | ⚠️ Keep 0 for flexibility |

**Rationale**:
- Backtest used DoltHub data (OI=0, no IV rank)
- Original paper trading filters were too conservative (would miss many trades)
- Aligned with validated backtest parameters

### 4. Capital Adjustment

**Before**:
```yaml
max_trading_capital: 5000  # $5k paper trading capital
initial_capital: 5000
```

**After**:
```yaml
max_trading_capital: 10000  # $10k paper trading capital (matches backtest)
initial_capital: 10000  # Matches 6-year backtest
```

**Rationale**:
- Backtest used $10k initial capital
- Ensures position sizing matches backtest

---

## Parameters That Stayed the Same (Already Matched)

These parameters were already correctly configured:

✓ **spread_width**: 5.0
✓ **delta_target**: 0.20 (20 delta)
✓ **max_dte**: 45
✓ **rsi_oversold**: 45
✓ **rsi_overbought**: 55
✓ **profit_target_pct**: 0.50 (50% of max profit)
✓ **stop_loss_multiplier**: 2.0 (2x credit)
✓ **max_concurrent_positions**: 3
✓ **max_single_position_percent**: 25%

---

## Screener Configuration Update

**Before**:
```yaml
custom_symbols:
  - "QQQ"  # Primary focus
  - "SPY"  # Backup option
```

**After**:
```yaml
custom_symbols:
  - "SPY"  # PRIMARY: Validated with +118.88% over 6 years, 78.6% win rate
  - "AAPL"  # OPTIONAL: Best performer +367.16%, 92.6% win rate (add after SPY success)
```

**Rationale**: Focus screener on validated symbols from backtest.

---

## Validation Against 6-Year Backtest

### SPY Performance (2019-2024)

```
Total Return:      +118.88% (+14.58% annualized)
Win Rate:          78.6% (22 wins, 6 losses)
Max Drawdown:      -14.91%
Sharpe Ratio:      1.10 (solid risk-adjusted returns)
Sortino Ratio:     1.79
Profit Factor:     7.41x
Total Trades:      28 (most active)
Coverage:          756 chains (49.8%)
```

### Market Cycles Tested
- **2019**: Bull market continuation
- **2020**: COVID crash + recovery
- **2021**: Bull market peak
- **2022**: Bear market (Fed rate hikes)
- **2023**: Recovery + AI rally
- **2024**: Consolidation

---

## Expected Behavior Changes

### More Trade Opportunities

**Before (Conservative)**:
- Min credit: $30
- Min ROR: 25%
- Min IV rank: 30
- Result: **Very few trades** (overly selective)

**After (Validated)**:
- Min credit: $15
- Min ROR: 8%
- Min IV rank: 0 (no filter)
- Result: **More trade opportunities** matching backtest frequency

### Shorter Hold Times

**Before**: Positions held until 21 DTE
**After**: Positions close at 14 DTE

**Impact**: Reduced gamma risk, earlier profit capture, matches validated strategy.

---

## Risk Management Notes

### Live Trading Considerations

1. **Open Interest**:
   - Backtest used OI=0 (DoltHub limitation)
   - Live trading should prefer OI > 100 for liquidity
   - Config set to 0 for flexibility, but strategy should check actual OI

2. **Bid-Ask Spreads**:
   - Backtest used max 15% spreads (DoltHub data)
   - Live trading should prefer < 5% for better execution
   - Monitor actual spreads during paper trading

3. **IV Rank**:
   - Backtest had no IV rank filter (DoltHub limitation)
   - Live trading could add min IV rank 15-20 for premium quality
   - Currently set to 0 to match backtest behavior

---

## Deployment Timeline

### Phase 1: Initial Deployment (Weeks 1-4)
- **Symbol**: SPY only
- **Capital**: $10,000
- **Max Positions**: 1-2 concurrent
- **Goal**: Validate order execution, position tracking, exit triggers

### Phase 2: Expansion (Weeks 5-12)
- **Symbol**: Add AAPL if SPY successful
- **Max Positions**: 2-3 concurrent
- **Goal**: Test multi-symbol management

### Phase 3: Full Deployment (Week 13+)
- **Symbols**: SPY, AAPL, selectively MSFT
- **Max Positions**: 3 concurrent (system limit)
- **Goal**: Full strategy deployment

---

## Configuration Files Updated

1. **config/paper_trading.yaml**:
   - Updated vertical_spread strategy parameters
   - Changed underlying from QQQ to SPY
   - Aligned all filters with backtest
   - Updated capital to $10k
   - Fixed close_dte from 21 to 14
   - Updated screener symbols

2. **Documentation**:
   - Updated header comments with 6-year backtest results
   - Added inline comments explaining backtest values
   - Referenced specific performance metrics

---

## Verification Checklist

Before starting paper trading, verify:

- [ ] SPY is the only underlying in config
- [ ] close_dte = 14 (not 21)
- [ ] min_credit = 15.0
- [ ] min_dte = 21
- [ ] max_spread_percent = 15.0
- [ ] min_return_on_risk = 0.08
- [ ] max_trading_capital = 10000
- [ ] Alpaca credentials configured (.env)
- [ ] Paper trading mode enabled (alpaca.paper = true)

---

## Next Steps

1. **Test Alpaca Connection**:
   ```bash
   uv run python scripts/test_alpaca_connection.py
   ```

2. **Verify Configuration**:
   ```bash
   # Check config loads correctly
   uv run python -c "from alpaca_options.core.config import load_config; print(load_config())"
   ```

3. **Start Paper Trading**:
   ```bash
   uv run python scripts/run_paper_trading.py --dashboard
   ```

4. **Monitor Closely**:
   - First 2 weeks: Daily review of all positions
   - Check exit triggers fire correctly (14 DTE, profit target, stop loss)
   - Validate spread selection matches backtest criteria

---

## Rollback Plan

If paper trading shows unexpected behavior, revert to conservative settings:

```yaml
underlyings: ["SPY"]
min_credit: 20.0
min_dte: 25
max_spread_percent: 8.0
min_return_on_risk: 0.15
close_dte: 14  # Keep this fix
```

---

**Configuration Updated**: 2025-12-08
**Backtest Reference**: EXTENDED_BACKTEST_REPORT.md
**Validated Period**: 2019-02-09 to 2024-12-31 (~6 years)
