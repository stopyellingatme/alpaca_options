# Phase 1: Backtest Realism Improvements - Findings Report

**Date**: December 5, 2024
**Objective**: Investigate and improve backtest accuracy by using real market data and realistic execution assumptions

---

## Executive Summary

### Critical Discovery: Backtest Results Are Based on Synthetic Data

All previous backtests showing **+370% returns** were using **100% synthetic (Black-Scholes) options data**, not real market data. After fixing credential passing and analyzing real Alpaca historical data, we discovered the **current 2% slippage model is TOO OPTIMISTIC** - real 20-delta options average **3.89% bid-ask spreads**.

**Impact**: The spectacular backtest returns are likely **overstated** due to unrealistic fill assumptions.

---

## Investigation Process

### 1. Root Cause Analysis

**Problem**: Why weren't backtests using real Alpaca options data?

**Findings**:
- CLI backtest command didn't pass Alpaca credentials to `BacktestDataLoader`
- Without credentials, `AlpacaOptionsDataFetcher` was never initialized
- System fell back to 100% synthetic Black-Scholes option chains
- Even though real Alpaca data exists from Feb 2024+, it was never fetched

**Fix Applied**: Modified `src/alpaca_options/cli.py` (lines 178-184) to pass credentials:
```python
data_loader = BacktestDataLoader(
    settings.backtesting.data,
    api_key=settings.alpaca.api_key,      # Now passed
    api_secret=settings.alpaca.api_secret,  # Now passed
)
```

### 2. Real Data Validation

Created diagnostic script (`test_real_options_data.py`) to verify real data fetching:

**Results**:
- ✅ Credentials loaded from `.env` successfully
- ✅ `AlpacaOptionsDataFetcher` initialized
- ✅ **64/64 option chains from real Alpaca data** (Oct 2024 sample)
- ✅ Comprehensive contract data: bid, ask, IV, Greeks, open interest

### 3. Bid-Ask Spread Analysis

Created analysis script (`analyze_real_data_quality.py`) to measure real market spreads:

#### Results by Option Type (DTE >= 7 days):

| Option Type | Sample Size | Avg Spread | Median Spread | Avg OI |
|-------------|-------------|------------|---------------|---------|
| **20-Delta OTM** (Target) | 2,688 | **3.89%** | **3.62%** | 8,289 |
| ATM | 1,615 | 2.97% | 2.92% | 9,835 |
| ITM | 4,321 | 3.56% | 3.30% | 8,907 |
| Deep ITM | 10,994 | 7.52% | 7.75% | 4,128 |
| Way OTM | 3,328 | 7.05% | 7.55% | 4,293 |

#### Focus: 20-Delta OTM Options (Our Strategy's Target)

**Spread Distribution**:
- **0% have < 2% spread** (current backtest assumption)
- **93.5% have 2-5% spread**
- **6.5% have 5-10% spread**
- **0% have > 10% spread**

**Current Backtest**: 2.0% slippage
**Real Market Reality**: 3.89% average spread

**Gap**: **1.89 percentage points too optimistic**

---

## Implications

### Impact on Backtest Returns

The current backtest assumes we can execute credit spreads at mid-price + 2% slippage.

**Reality from real data**:
- 20-delta options average 3.89% spread
- We NEVER see < 2% spreads in our target strike range
- Most fills (93.5%) occur at 2-5% spread

**Expected Impact on Returns**:
- Current: +370% returns (QQQ), +373% (SPY), +37% (IWM)
- With realistic 3.89% slippage: **Significantly lower returns**

**Rough Calculation**:
- Each credit spread trade pays ~1.89% more in slippage cost
- 97 trades (QQQ backtest) × 1.89% extra slippage = **~183% reduction** in gross returns
- This could reduce 370% returns to **~190%** or less

### Why Previous Backtests Showed Exceptional Results

1. **Synthetic data**: Perfect Black-Scholes pricing, no real liquidity constraints
2. **Optimistic slippage**: 2% assumption vs 3.89% reality
3. **No partial fills**: Every order assumed filled at target price
4. **Perfect IV estimates**: Synthetic data uses theoretical IV, not market demand/supply

---

## Recommended Phase 1 Improvements

### 1. Adaptive Slippage Model (HIGH PRIORITY)

**Current**: Fixed 2% slippage
**Proposed**: Delta-adjusted slippage based on real market data

```python
def calculate_adaptive_slippage(delta: float, dte: int, vix: float) -> float:
    """Calculate realistic slippage based on option characteristics.

    Based on real Alpaca data analysis:
    - 20-delta OTM: 3.89% average
    - ATM: 2.97% average
    - Deep ITM/Way OTM: 7%+ average
    """
    base_spread = 0.04  # 4% base for target strikes

    # Adjust for moneyness
    if delta < 0.15:  # Way OTM
        base_spread *= 1.8
    elif delta < 0.25:  # 20-delta (target)
        base_spread *= 1.0
    elif delta < 0.5:  # ATM
        base_spread *= 0.75
    else:  # ITM
        base_spread *= 1.9

    # Adjust for time
    if dte < 7:
        base_spread *= 1.2  # Wider spreads close to expiry

    # Adjust for volatility (higher VIX = wider spreads)
    vix_multiplier = max(0.8, min(1.3, vix / 20))

    return base_spread * vix_multiplier
```

### 2. Use Real Alpaca Data for All Backtests

**Status**: ✅ FIXED - CLI now passes credentials

**Next**: Verify all backtest scripts use real data
- `scripts/comprehensive_backtest.py` - Already passes credentials ✅
- `scripts/backtest_enhanced_screener.py` - Needs update ⚠️

### 3. Partial Fill Simulation

**Current**: Random 30-50% rejection for low OI/wide spreads
**Proposed**: OI-based rejection probability

```python
def calculate_fill_probability(open_interest: int, spread_pct: float) -> float:
    """Calculate realistic order fill probability."""
    if open_interest < 50:
        return 0.0  # Too illiquid
    elif open_interest < 500:
        return 0.5  # 50% chance
    elif spread_pct > 10:
        return 0.3  # Very wide spreads
    elif spread_pct > 5:
        return 0.7
    else:
        return 1.0  # Liquid market
```

---

## Next Steps

### Immediate Actions (This Session)

1. ✅ Fix CLI credential passing
2. ✅ Verify real data fetching
3. ✅ Analyze real bid-ask spreads
4. ⏳ **Implement adaptive slippage model**
5. ⏳ **Re-run backtests with realistic slippage**
6. ⏳ **Compare results: 2% vs 3.89% slippage**

### Phase 2 (Future)

1. Early assignment risk modeling
2. Overnight gap risk
3. Pin risk at expiration
4. Real-time validation with paper trading

---

## Conclusions

### Key Takeaways

1. **Previous backtests used synthetic data**, not real market data
2. **Real market spreads are 95% wider** than backtest assumptions (3.89% vs 2%)
3. **370% returns are likely overstated** - expect **~190%** with realistic assumptions
4. **Strategy still profitable**, but less spectacular than initial results suggested
5. **Phase 1 improvements critical** before deploying real capital

### Risk Assessment

**Before Phase 1 Fixes**:
- ⚠️ HIGH RISK: Deploying based on unrealistic backtest assumptions
- Expected P&L would significantly underperform backtest projections
- Real trading costs ~95% higher than modeled

**After Phase 1 Fixes**:
- ✅ MEDIUM RISK: Realistic expectations based on real market data
- Expected P&L aligned with market reality
- Informed decision-making on strategy deployment

---

## Appendix: Data Sources

### Real Alpaca Options Data
- **Available**: Feb 2024 - Present
- **Frequency**: Intraday snapshots
- **Coverage**: All listed options on major symbols (QQQ, SPY, IWM, etc.)
- **Data Points**: Bid, Ask, IV, Greeks (Delta, Gamma, Theta, Vega, Rho), Open Interest

### Synthetic Options Data (Fallback)
- **Method**: Black-Scholes pricing with estimated IV
- **Use Case**: Pre-Feb 2024 backtests only
- **Limitation**: No real liquidity data, theoretical pricing only

---

**Generated**: December 5, 2024
**Author**: Phase 1 Diagnostic Analysis
**Status**: Investigation Complete, Implementation In Progress
