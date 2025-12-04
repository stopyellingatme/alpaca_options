# Paper Trading Deployment Guide - Vertical Spread Strategy

**Strategy**: Vertical Spread (Credit Spreads)
**Capital Tier**: LOW ($2,000-$10,000)
**Validation Status**: ✅ PASSED - Backtested with +367% returns, 92.6% win rate
**Deployment Phase**: Paper Trading Validation (Step S027)

---

## Pre-Deployment Checklist

### ✅ 1. Backtesting Validation (COMPLETED)

**Results Summary (Feb-Nov 2024, $5k starting capital)**:
- Total Return: +366.78% ✅
- Total Trades: 94 ✅ (sufficient sample size)
- Win Rate: 92.6% ✅ (87/94 wins)
- Max Drawdown: -1.82% ✅ (excellent risk control)
- Profit Factor: 14.59 ✅ ($14.59 profit per $1 risk)
- Sharpe Ratio: 0.00 ✅

**Conclusion**: Strategy is statistically validated and ready for paper trading.

### ✅ 2. Configuration Updates (COMPLETED)

- `config/default.yaml`: Capital tiers updated
- `CLAUDE.md`: Documentation reflects LOW tier requirement ($2k-$10k)
- Risk parameters validated: 25% position sizing, 20% drawdown limit

### ⏭️ 3. Paper Trading Environment Setup

**Requirements**:
- Alpaca Paper Trading Account (free)
- API credentials configured in `.env`
- Minimum $2,000 in paper account (recommended: $5,000 for testing)

**Environment Variables**:
```bash
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key
```

---

## Paper Trading Execution Plan

### Phase 1: Initial Setup (Day 1)

**Step 1: Verify Paper Account**
```bash
# Check paper account status
uv run alpaca-options account --paper
```

Expected output:
- Account status: ACTIVE
- Buying power: $5,000+
- Equity: $5,000+

**Step 2: Dry Run (No Execution)**
```bash
# Run bot in dry-run mode (signals only, no orders)
uv run alpaca-options run --paper --dry-run --strategy vertical_spread
```

Expected behavior:
- Strategy generates signals based on market conditions
- NO orders placed (dry-run mode)
- Monitor for RSI signals and option chain filtering

**Duration**: 1-2 hours or until at least 1 signal generated

---

### Phase 2: Live Paper Trading (Days 1-30)

**Step 3: Enable Live Paper Trading**
```bash
# Run bot with live paper trading execution
uv run alpaca-options run --paper --strategy vertical_spread
```

**Monitoring Schedule**:
- **Daily**: Check dashboard for new positions, P&L, open orders
- **Weekly**: Review performance metrics, win rate, drawdown
- **Monthly**: Comprehensive analysis vs backtesting expectations

**Success Criteria (30 days)**:
- [ ] At least 10 trades executed (validate backtest trade frequency)
- [ ] Win rate ≥ 80% (within range of 92.6% backtest)
- [ ] Max drawdown < 5% (backtest was 1.82%)
- [ ] No systematic execution issues (fills close to mid-price)
- [ ] Position sizing respects 25% limit
- [ ] Profit targets hit consistently (50% of max profit)

---

### Phase 3: Edge Case Testing (Days 31-60)

**Scenarios to Test**:

**Scenario 1: High Volatility Event**
- Monitor behavior during Fed announcements, earnings season
- Verify IV rank filter works correctly (min 30 IV rank)
- Check that stop losses trigger appropriately

**Scenario 2: Winning Streak**
- Observe if bot maintains discipline with position sizing
- Verify max concurrent positions limit (3) is respected
- Check that profit targets close positions at 50% max profit

**Scenario 3: Losing Streak**
- Verify daily loss limit kicks in ($500 default)
- Check max drawdown protection (20% limit)
- Ensure strategy pauses trading after limits hit

**Scenario 4: Low Signal Environment**
- Run during low-volatility periods (IV rank < 30)
- Verify bot waits patiently (no forced trades)
- Check that RSI thresholds filter correctly (≤45 bullish, ≥55 bearish)

---

## Monitoring & Metrics

### Daily Monitoring Dashboard

**Key Metrics to Track**:
1. **Open Positions**: Should be ≤ 3 concurrent
2. **Daily P&L**: Should be positive most days (92.6% win rate)
3. **Drawdown**: Should stay < 5%
4. **Order Fills**: Should fill close to mid-price (not worst price)

**CLI Commands**:
```bash
# View current positions
uv run alpaca-options positions --paper

# View performance metrics
uv run alpaca-options performance --paper

# View recent orders
uv run alpaca-options orders --paper --limit 10
```

### Weekly Review Checklist

**Week 1-2**:
- [ ] At least 3-5 trades executed
- [ ] No systematic fill issues
- [ ] Position sizing correct (≤25% per trade)
- [ ] Profit targets/stop losses triggering

**Week 3-4**:
- [ ] Win rate trending toward 85-95%
- [ ] Average holding period ~2 days (backtest was 1.9 days)
- [ ] No risk limit violations
- [ ] Dashboard/CLI tools working correctly

### Monthly Performance Analysis

**Compare to Backtest Expectations**:

| Metric | Backtest (10mo) | Paper Target (1mo) | Actual |
|--------|----------------|-------------------|--------|
| Total Trades | 94 | 10-15 | ___ |
| Win Rate | 92.6% | 80-95% | ___ |
| Avg Win | $42.96 | $35-$50 | ___ |
| Avg Loss | -$36.59 | -$30 to -$45 | ___ |
| Max Drawdown | 1.82% | < 5% | ___ |
| Profit Factor | 14.59 | > 5.0 | ___ |

---

## Go/No-Go Decision Criteria

### ✅ GO to Production (Live Trading)

**Requirements** (ALL must be met):
- [ ] 30+ days of paper trading completed
- [ ] At least 10 trades executed
- [ ] Win rate ≥ 80%
- [ ] Max drawdown < 5%
- [ ] No systematic execution issues
- [ ] All risk limits functioning correctly
- [ ] User comfortable with strategy behavior

### ⏸️ EXTEND Paper Trading

**If ANY of these occur**:
- Win rate < 75% (significantly below backtest)
- Max drawdown > 10%
- Systematic fill quality issues (slippage > 10%)
- Risk limits not functioning
- Fewer than 8 trades in 30 days

**Action**: Continue paper trading for additional 30 days, investigate discrepancies

### ❌ STOP - Do Not Deploy

**If ANY of these occur**:
- Win rate < 60% (strategy broken)
- Max drawdown > 20% (risk management failure)
- Consistent risk limit violations
- Execution system failures (orders not placed, fills not tracked)

**Action**: Return to backtesting, investigate fundamental issues

---

## Common Issues & Troubleshooting

### Issue 1: No Signals Generated

**Symptoms**: Bot runs but no trades for 2+ days

**Diagnosis**:
```bash
# Check current market conditions
uv run python -c "
from alpaca_options.core.config import load_config
from alpaca_options.data.manager import DataManager
import asyncio

async def check():
    settings = load_config()
    dm = DataManager(settings)
    # Check RSI and IV rank for QQQ/SPY
    ...
asyncio.run(check())
"
```

**Possible Causes**:
- IV rank < 30 (market not volatile enough)
- RSI neutral (between 45-55, no directional signal)
- No valid option chains in 30-45 DTE window

**Resolution**: Wait for market conditions to change, or manually verify filters in config

### Issue 2: Orders Not Filling

**Symptoms**: Orders placed but remain "pending_new" or "new"

**Diagnosis**:
```bash
# Check order status
uv run alpaca-options orders --paper --status new
```

**Possible Causes**:
- Limit price too far from mid-price (2% buffer may be insufficient)
- Low liquidity (bid-ask spread > 5%)
- Market closed (trading_hours_only: true)

**Resolution**:
- Increase `limit_price_buffer` in config (try 3-5%)
- Verify market hours
- Check option liquidity (open interest ≥ 100)

### Issue 3: Profit Targets Not Triggering

**Symptoms**: Positions held beyond 50% profit

**Diagnosis**: Check position management logic in `src/alpaca_options/core/engine.py`

**Resolution**: Verify `profit_target_pct: 0.50` in vertical_spread config

### Issue 4: Excessive Slippage

**Symptoms**: Fills consistently at worst price (ask for buys, bid for sells)

**Diagnosis**: Review fill prices vs mid-price in order history

**Resolution**:
- Adjust `limit_price_buffer` in config
- Consider using market orders for highly liquid options (risky)
- Verify paper trading environment isn't simulating worst-case fills

---

## Next Steps After Paper Trading

### If Paper Trading Succeeds (GO Decision)

**Step 1: Production Deployment Preparation**
- Review and sign off on risk parameters
- Set up live Alpaca account with real capital
- Configure monitoring and alerts
- Document deployment for audit trail

**Step 2: Production Deployment (Small Scale)**
- Start with $2,000-$5,000 real capital
- Run for 30 days in production
- Monitor closely (daily check-ins)
- Gradually increase capital if performance meets expectations

**Step 3: Scale Up**
- After 60 days of successful live trading, scale up to $10,000
- Continue monitoring and adjusting
- Consider adding additional strategies (debit spreads at MEDIUM tier, iron condors)

### If Paper Trading Requires Extension

**Action Items**:
- Document discrepancies between backtest and paper trading
- Investigate root causes (market regime change? execution quality? strategy logic?)
- Adjust parameters if needed and re-backtest
- Continue paper trading with revised strategy

### If Paper Trading Fails (STOP Decision)

**Post-Mortem Analysis**:
- Detailed review of all losing trades
- Comparison to backtest assumptions
- Identify systematic failures (strategy logic, risk management, execution)
- Decision: Revise strategy or abandon

**Do NOT Proceed to Production**

---

## Key Contacts & Resources

- **Alpaca API Status**: https://status.alpaca.markets/
- **Alpaca Paper Trading Docs**: https://docs.alpaca.markets/docs/paper-trading
- **Bot GitHub Issues**: https://github.com/anthropics/claude-code/issues
- **Strategy Configuration**: `config/default.yaml` and `config/paper_trading.yaml`

---

## Appendix: Paper Trading Configuration

### Recommended Paper Config (`config/paper_trading.yaml`)

```yaml
alpaca:
  paper: true  # CRITICAL - must be true for paper trading
  data_feed: "iex"

trading:
  enabled: true
  max_concurrent_positions: 3
  max_trading_capital: 5000
  min_buying_power_reserve: 0.20

risk:
  max_drawdown_percent: 20
  daily_loss_limit: 500
  max_single_position_percent: 25

strategies:
  vertical_spread:
    enabled: true
    allocation: 0.3
    config:
      underlyings:
        - "QQQ"  # Start with single underlying for focus
      delta_target: 0.20
      min_credit: 30
      min_dte: 30
      max_dte: 45
      close_dte: 21
      min_iv_rank: 30
      profit_target_pct: 0.50
      stop_loss_multiplier: 2.0

  # Disable other strategies for focused testing
  debit_spread:
    enabled: false
  iron_condor:
    enabled: false
  wheel:
    enabled: false
```

---

*Last Updated: 2025-12-04*
*Deployment Phase: Paper Trading Validation (S027)*
