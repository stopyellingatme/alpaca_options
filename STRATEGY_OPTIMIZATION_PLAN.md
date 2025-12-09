# Vertical Spread Strategy Optimization Plan

**Date**: 2025-12-08
**Branch**: `feature/strategy-optimization`
**Baseline**: 6-year backtest (2019-2024) on AAPL, MSFT, NVDA, SPY

---

## Executive Summary

Based on the validated 6-year backtest results, we have a solid foundation for optimization. The strategy shows:
- **Average Performance**: +174.95% total return, 75.3% win rate, 1.97 Sharpe ratio
- **Best Performer**: AAPL (+367%, 92.6% win rate, 4.71 Sharpe)
- **Most Consistent**: SPY (+119%, 78.6% win rate, 28 trades)

**Optimization Goals**:
1. Improve risk-adjusted returns (target Sharpe > 2.0)
2. Reduce maximum drawdown (target < 12%)
3. Increase win rate (target > 80%)
4. Optimize capital efficiency (more frequent trades with maintained quality)

---

## Phase 1: Parameter Grid Search

### 1.1 Delta Target Optimization

**Current**: 20 delta (~80% probability OTM)

**Test Grid**:
- 15 delta (higher probability, lower premium)
- 18 delta
- 20 delta (baseline)
- 22 delta
- 25 delta (lower probability, higher premium)

**Hypothesis**: AAPL's exceptional performance (92.6% win rate) suggests we might be able to move to slightly higher delta (more premium) while maintaining win rate.

**Test Approach**:
```python
# scripts/optimize_delta.py
deltas = [0.15, 0.18, 0.20, 0.22, 0.25]
for delta in deltas:
    run_backtest(delta_target=delta, symbol="AAPL", ...)
```

**Success Metrics**:
- Sharpe ratio improvement
- Win rate maintenance (> 90% for AAPL)
- Premium captured per trade

---

### 1.2 DTE Range Optimization

**Current**:
- Entry: 21-45 DTE
- Exit: 14 DTE

**Test Grid**:

Entry DTE:
- 14-30 DTE (shorter duration, faster capital rotation)
- 21-45 DTE (baseline)
- 30-60 DTE (longer duration, more theta decay)

Exit DTE:
- 7 DTE (exit earlier, less gamma risk)
- 14 DTE (baseline)
- 21 DTE (hold longer for more decay)

**Hypothesis**:
- Shorter DTE ranges might increase trade frequency
- Earlier exits (7 DTE) might improve risk-adjusted returns by avoiding late-stage gamma
- 6-year data shows we're closing positions at 14 DTE successfully

**Test Combinations**:
```python
# Test matrix
entry_ranges = [(14, 30), (21, 45), (30, 60)]
exit_dtes = [7, 14, 21]

for entry_min, entry_max in entry_ranges:
    for exit_dte in exit_dtes:
        if exit_dte < entry_min:  # Skip invalid combinations
            continue
        run_backtest(
            min_dte=entry_min,
            max_dte=entry_max,
            close_dte=exit_dte,
            ...
        )
```

---

### 1.3 Profit Target / Stop Loss Optimization

**Current**:
- Profit target: 50% of max profit
- Stop loss: 2x credit received

**Test Grid**:

Profit Targets:
- 40% (exit earlier, higher win rate)
- 50% (baseline)
- 60% (hold longer, more profit per trade)
- 75% (aggressive profit capture)

Stop Losses:
- 1.5x credit (tighter stop)
- 2.0x credit (baseline)
- 2.5x credit (wider stop)
- 3.0x credit (give more room)

**Hypothesis**:
- AAPL's 92.6% win rate suggests we might tighten stops without hurting performance
- Lower profit targets (40%) might increase win rate further while maintaining total return

**Test Approach**:
```python
profit_targets = [0.40, 0.50, 0.60, 0.75]
stop_losses = [1.5, 2.0, 2.5, 3.0]

for pt in profit_targets:
    for sl in stop_losses:
        run_backtest(
            profit_target_pct=pt,
            stop_loss_multiplier=sl,
            ...
        )
```

---

### 1.4 Entry Signal Optimization

**Current**:
- RSI oversold: ≤ 45 (bullish signal → bull put spread)
- RSI overbought: ≥ 55 (bearish signal → bear call spread)

**Test Grid**:

RSI Thresholds:
- Conservative: 40/60 (fewer trades, stronger signals)
- Current: 45/55 (baseline)
- Aggressive: 48/52 (more trades, weaker signals)

**Additional Filters to Test**:
1. **MACD Confirmation**: Require MACD agreement with RSI
2. **Volume Filter**: Require above-average volume
3. **Trend Alignment**: Only trade with 20/50 MA trend
4. **IV Rank Minimum**: Require IV rank > 15 (currently 0 for DoltHub compatibility)

**Hypothesis**:
- Adding confirmation filters might reduce losing trades
- SPY's consistency (78.6% win rate, most trades) suggests current signals work well
- NVDA's lower performance (55.6% win rate) might benefit from stricter filters

---

## Phase 2: Symbol-Specific Optimization

### 2.1 Per-Symbol Parameter Tuning

**Observation**: Different symbols have vastly different performance:

| Symbol | Return | Win Rate | Sharpe | Trades | Characteristics |
|--------|--------|----------|--------|--------|-----------------|
| AAPL | +367% | 92.6% | 4.71 | 27 | High win rate, exceptional Sharpe |
| MSFT | +167% | 70.0% | 1.36 | 20 | Solid but more losses |
| SPY | +119% | 78.6% | 1.10 | 28 | Most active, consistent |
| NVDA | +47% | 55.6% | 0.72 | 18 | Volatile, lower win rate |

**Hypothesis**: One-size-fits-all parameters are suboptimal. Each symbol might benefit from custom parameters.

**Approach**:

For **AAPL** (already excellent):
- Test higher delta (22-25) to capture more premium
- Test tighter profit targets (40%) to lock in wins faster
- Test wider entry window (30-60 DTE) for more opportunities

For **MSFT** (good but improvable):
- Test tighter stops (1.5x) to cut losses faster
- Test stricter entry signals (RSI 40/60) for higher quality setups

For **SPY** (consistent, most active):
- Keep current parameters (working well)
- Test slightly more aggressive entries for more trades

For **NVDA** (volatile, needs improvement):
- Test lower delta (15-18) for higher probability
- Test stricter entry filters (MACD confirmation)
- Test wider stops (2.5-3.0x) to handle volatility
- Consider removing NVDA if optimization doesn't improve results

---

### 2.2 Implementation Plan

Create symbol-specific config sections:

```yaml
# config/paper_trading.yaml (future enhancement)
vertical_spread:
  # Default parameters
  default:
    delta_target: 0.20
    profit_target_pct: 0.50
    stop_loss_multiplier: 2.0
    ...

  # Symbol-specific overrides
  symbol_overrides:
    AAPL:
      delta_target: 0.22  # Higher delta for more premium
      profit_target_pct: 0.40  # Exit earlier to lock wins
      min_dte: 30
      max_dte: 60

    MSFT:
      stop_loss_multiplier: 1.5  # Tighter stops
      rsi_oversold: 40  # Stricter signals
      rsi_overbought: 60

    NVDA:
      delta_target: 0.18  # Higher probability
      stop_loss_multiplier: 2.5  # Wider stops for volatility
      min_dte: 30  # Longer DTE for less gamma
```

---

## Phase 3: Market Regime Detection

### 3.1 Regime Classification

**Observation**: Strategy performed across 6 market cycles with varying characteristics.

**Regimes to Detect**:

1. **Bull Market** (2019, 2021, 2023):
   - SPY trending up
   - Lower volatility
   - Better for bull put spreads

2. **Bear Market** (2020 crash, 2022 bear):
   - SPY trending down
   - Higher volatility
   - Better for bear call spreads

3. **High Volatility** (VIX > 25):
   - Wider spreads
   - More premium available
   - Higher risk

4. **Low Volatility** (VIX < 15):
   - Tighter spreads
   - Less premium
   - Fewer opportunities

### 3.2 Regime-Based Parameter Adjustment

**Approach**:

```python
# Detect regime based on:
# - 50-day MA trend (bull/bear)
# - VIX level (volatility)
# - Recent volatility (20-day realized vol)

if market_regime == "BULL_LOW_VOL":
    # Favor bull put spreads, tighter parameters
    config["delta_target"] = 0.20
    config["prefer_put_spreads"] = True

elif market_regime == "BEAR_HIGH_VOL":
    # Favor bear call spreads, wider stops
    config["delta_target"] = 0.18  # Higher probability
    config["stop_loss_multiplier"] = 2.5
    config["prefer_call_spreads"] = True

elif market_regime == "HIGH_VOLATILITY":
    # Be more selective, capture high premiums
    config["min_credit"] = 20.0  # Higher minimum
    config["min_iv_rank"] = 30  # Only trade elevated IV
```

### 3.3 Backtest with Regime Detection

Test whether regime-aware parameters improve results:

```python
# scripts/backtest_regime_aware.py
results_baseline = run_backtest(use_regime_detection=False)
results_regime = run_backtest(use_regime_detection=True)

compare_results(results_baseline, results_regime)
```

**Success Metrics**:
- Improved Sharpe ratio
- Lower drawdown in bear markets
- Better risk-adjusted returns across all regimes

---

## Phase 4: Multi-Objective Optimization

### 4.1 Optimization Goals (Ranked)

1. **Primary**: Maximize risk-adjusted returns (Sharpe ratio)
2. **Secondary**: Minimize maximum drawdown
3. **Tertiary**: Maximize win rate
4. **Quaternary**: Maximize trade frequency (capital efficiency)

### 4.2 Optimization Algorithm

Use Bayesian optimization to explore parameter space efficiently:

```python
# scripts/bayesian_optimization.py
from skopt import gp_minimize
from skopt.space import Real, Integer

# Define parameter space
space = [
    Real(0.15, 0.25, name='delta_target'),
    Integer(14, 60, name='min_dte'),
    Integer(21, 90, name='max_dte'),
    Integer(7, 21, name='close_dte'),
    Real(0.30, 0.75, name='profit_target_pct'),
    Real(1.5, 3.0, name='stop_loss_multiplier'),
    Real(40.0, 50.0, name='rsi_oversold'),
    Real(50.0, 60.0, name='rsi_overbought'),
]

# Objective function
def objective(params):
    results = run_backtest(*params, symbol="SPY")

    # Multi-objective score
    score = (
        results.sharpe_ratio * 0.5 +  # 50% weight on Sharpe
        (1 - results.max_drawdown) * 0.3 +  # 30% weight on drawdown
        results.win_rate * 0.2  # 20% weight on win rate
    )

    return -score  # Minimize negative score = maximize score

# Run optimization
result = gp_minimize(objective, space, n_calls=100, random_state=42)
```

---

## Phase 5: Validation and Deployment

### 5.1 Out-of-Sample Testing

**Approach**:
- Train optimization on 2019-2022 (4 years)
- Validate on 2023-2024 (2 years)
- Check for overfitting

### 5.2 Walk-Forward Analysis

Test on rolling windows:
- Train: 2019-2020, Test: 2021
- Train: 2020-2021, Test: 2022
- Train: 2021-2022, Test: 2023
- Train: 2022-2023, Test: 2024

**Success Criteria**: Optimized parameters should work across all test periods.

### 5.3 Paper Trading Validation

Before live deployment:
1. Deploy optimized parameters to paper trading
2. Monitor for 2-4 weeks
3. Compare actual results to backtest expectations
4. Validate:
   - Entry/exit timing
   - Spread selection
   - P&L tracking
   - Order execution

---

## Implementation Timeline

### Week 1: Phase 1 - Parameter Grid Search
- [ ] Implement delta optimization script
- [ ] Implement DTE range optimization script
- [ ] Implement profit/stop optimization script
- [ ] Implement entry signal optimization script
- [ ] Run all grid searches
- [ ] Document results

### Week 2: Phase 2 - Symbol-Specific Optimization
- [ ] Analyze per-symbol characteristics
- [ ] Run symbol-specific parameter searches
- [ ] Implement symbol override configuration
- [ ] Validate symbol-specific results

### Week 3: Phase 3 - Market Regime Detection
- [ ] Implement regime detection logic
- [ ] Create regime classification tests
- [ ] Run regime-aware backtests
- [ ] Compare with baseline

### Week 4: Phase 4 - Multi-Objective Optimization
- [ ] Install skopt for Bayesian optimization
- [ ] Implement multi-objective scoring function
- [ ] Run Bayesian optimization (100+ iterations)
- [ ] Analyze optimal parameters

### Week 5: Phase 5 - Validation
- [ ] Out-of-sample testing
- [ ] Walk-forward analysis
- [ ] Update paper trading configuration
- [ ] Begin paper trading validation

---

## Success Metrics

**Minimum Acceptable Improvement**:
- Sharpe ratio: +0.20 improvement (baseline 1.97 → target 2.17+)
- Max drawdown: -2% reduction (baseline -14.51% → target -12.5% or better)
- Win rate: +3% improvement (baseline 75.3% → target 78%+)

**Stretch Goals**:
- Sharpe ratio: > 2.50
- Max drawdown: < -10%
- Win rate: > 80%
- Trade frequency: 25% more trades with maintained quality

---

## Risk Management

**Overfitting Prevention**:
1. Use train/test splits
2. Validate on out-of-sample data
3. Require consistent performance across multiple market regimes
4. Prefer simpler models over complex ones
5. Paper trade before live deployment

**Rollback Criteria**:
If optimized strategy shows:
- Sharpe ratio < 1.50 (worse than baseline 1.97)
- Win rate < 70% (worse than baseline 75.3%)
- Max drawdown > -20% (worse than baseline -14.51%)

→ Revert to validated baseline parameters

---

## Tools and Scripts to Create

1. `scripts/optimize_delta.py` - Delta target grid search
2. `scripts/optimize_dte.py` - DTE range grid search
3. `scripts/optimize_exits.py` - Profit/stop optimization
4. `scripts/optimize_entries.py` - Entry signal optimization
5. `scripts/optimize_per_symbol.py` - Symbol-specific optimization
6. `scripts/detect_market_regime.py` - Regime classification
7. `scripts/bayesian_optimization.py` - Multi-objective optimization
8. `scripts/validate_optimization.py` - Out-of-sample validation
9. `scripts/walk_forward_analysis.py` - Rolling window validation
10. `scripts/compare_optimization_results.py` - Results comparison and visualization

---

## Documentation Requirements

For each optimization phase:
1. Document parameter ranges tested
2. Show performance comparison tables
3. Visualize parameter sensitivity (heatmaps)
4. Explain why certain parameters work better
5. Highlight trade-offs (e.g., higher Sharpe vs lower frequency)

---

**Next Steps**:
1. Review and approve this optimization plan
2. Begin Phase 1 implementation (parameter grid search)
3. Create optimization scripts

**References**:
- Baseline: `EXTENDED_BACKTEST_REPORT.md`
- Config: `config/paper_trading.yaml`
- Backtest script: `scripts/backtest_multi_symbol.py`
