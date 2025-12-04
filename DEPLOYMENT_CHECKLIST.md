# Paper Trading Deployment Checklist - Vertical Spread Strategy

**Strategy**: Vertical Spread (Credit Spreads)
**Capital**: $5,000
**Expected Performance**: +367% over 10 months, 92.6% win rate
**Deployment Date**: ___________

---

## ✅ Pre-Deployment (Complete Before Starting)

### 1. Alpaca Account Setup
- [ ] Created Alpaca account at https://alpaca.markets
- [ ] Verified paper trading account is active
- [ ] Paper account has $5,000 in equity
- [ ] Generated paper trading API keys
- [ ] Saved API keys securely

### 2. Environment Configuration
- [ ] Created `.env` file from `.env.example`
- [ ] Added `ALPACA_API_KEY` to `.env`
- [ ] Added `ALPACA_SECRET_KEY` to `.env`
- [ ] Verified `.env` is in `.gitignore` (don't commit secrets!)

### 3. Account Verification
```bash
# Run this command to verify setup
uv run python scripts/verify_paper_account.py
```

Expected output:
- [x] ✅ API keys found
- [x] ✅ Paper trading mode enabled
- [x] ✅ Connected to Alpaca API
- [x] ✅ Account equity ≥ $2,000 (recommended $5,000)
- [x] ✅ Vertical spread strategy enabled

---

## 🎯 Phase 1: Dry Run (Day 1 - 2 hours)

**Goal**: Verify bot generates signals correctly without placing orders

### Commands
```bash
# Start in dry-run mode (signals only, no orders)
uv run alpaca-options run --paper --dry-run --strategy vertical_spread --config config/paper_vertical_spread.yaml
```

### Success Criteria
- [ ] Bot starts successfully without errors
- [ ] Strategy processes market data (QQQ)
- [ ] RSI indicators calculated correctly
- [ ] At least 1 signal generated (if market conditions suitable)
- [ ] No orders placed (dry-run mode)
- [ ] Logs show clear decision-making process

### Common Issues
- **No signals for 1-2 hours**: Normal if IV rank < 30 or RSI neutral (45-55)
- **Connection errors**: Check API keys, verify Alpaca API status
- **Missing data**: Verify market is open (Mon-Fri 9:30am-4pm ET)

---

## 🚀 Phase 2: Live Paper Trading (Days 1-30)

**Goal**: Execute trades in paper account, validate backtest expectations

### Commands
```bash
# Start live paper trading
uv run alpaca-options run --paper --strategy vertical_spread --config config/paper_vertical_spread.yaml

# Monitor in separate terminal
uv run alpaca-options dashboard --paper
```

### Daily Monitoring (5-10 minutes/day)

**Check Dashboard**:
```bash
# View current positions
uv run alpaca-options positions --paper

# View recent orders
uv run alpaca-options orders --paper --limit 10

# View performance
uv run alpaca-options performance --paper
```

**Daily Checklist**:
- [ ] Check open positions (should be ≤ 3)
- [ ] Review new trades (expected 1-2 per week)
- [ ] Verify profit targets/stop losses triggered correctly
- [ ] Check drawdown (should be < 5%)
- [ ] Review logs for any errors or warnings

### Weekly Review (30 minutes/week)

**Week 1-2 Goals**:
- [ ] At least 3-5 trades executed
- [ ] No systematic order fill issues
- [ ] Position sizing correct (≤ 25% per trade)
- [ ] Win rate tracking toward 80-95%
- [ ] Drawdown < 5%

**Week 3-4 Goals**:
- [ ] At least 8-12 total trades
- [ ] Win rate ≥ 80%
- [ ] Average holding period ~2 days (matches backtest)
- [ ] Profit factor > 5.0
- [ ] No risk limit violations

---

## 📊 Phase 3: Performance Analysis (Day 30)

### Metrics Comparison

| Metric | Backtest Target | Actual | Status |
|--------|----------------|--------|--------|
| Total Trades | 10-15 | ___ | ___ |
| Win Rate | 80-95% | ___ | ___ |
| Avg Win | $35-$50 | ___ | ___ |
| Avg Loss | -$30 to -$45 | ___ | ___ |
| Max Drawdown | < 5% | ___ | ___ |
| Profit Factor | > 5.0 | ___ | ___ |

### Decision: GO / NO-GO / EXTEND

**✅ GO to Production** (all must be true):
- [ ] 10+ trades executed
- [ ] Win rate ≥ 80%
- [ ] Max drawdown < 5%
- [ ] No systematic execution issues
- [ ] Risk limits functioning correctly
- [ ] Comfortable with strategy behavior

**⏸️ EXTEND Paper Trading** (if any):
- [ ] Win rate < 75%
- [ ] Max drawdown > 10%
- [ ] Execution quality concerns
- [ ] Fewer than 8 trades

**❌ STOP - Do Not Deploy** (if any):
- [ ] Win rate < 60%
- [ ] Max drawdown > 20%
- [ ] Systematic failures
- [ ] Risk management broken

---

## 🔧 Troubleshooting Guide

### Issue: No Signals Generated

**Symptoms**: Bot runs but no trades for 2+ days

**Diagnosis**:
```bash
# Check market conditions manually
# RSI should be ≤45 (bullish) or ≥55 (bearish)
# IV rank should be ≥30
```

**Resolution**: Wait for market conditions or adjust thresholds in config (not recommended initially)

### Issue: Orders Not Filling

**Symptoms**: Orders stuck in "pending_new" or "new" status

**Diagnosis**:
```bash
# Check order status
uv run alpaca-options orders --paper --status new
```

**Possible Causes**:
- Limit price too far from market (increase `limit_price_buffer` to 3-5%)
- Low liquidity options (increase OI threshold or widen bid-ask tolerance)
- Market closed

### Issue: Positions Not Closing at Profit Target

**Symptoms**: Positions held beyond 50% profit

**Check**:
- Verify `profit_target_pct: 0.50` in config
- Review position management logs
- Check if bot is running continuously (needs to be running to monitor exits)

### Issue: Excessive Losses

**Symptoms**: Win rate < 60% or losses exceeding expectations

**Immediate Actions**:
1. **STOP paper trading immediately**
2. Review all losing trades in detail
3. Check logs for systematic issues
4. Compare to backtest assumptions
5. Do NOT proceed to production

**Investigation**:
- Are fills worse than expected (bad slippage)?
- Is market behavior different from backtest period?
- Are stop losses triggering correctly?
- Is position sizing correct?

---

## 📝 Daily Log Template

### Date: ___________

**Market Conditions**:
- QQQ Price: $_____
- QQQ RSI: _____
- Estimated IV Rank: _____ (high/medium/low)

**Positions**:
- Open: ___
- Closed today: ___
- P&L today: $_____

**New Signals**:
- Signals generated: ___
- Orders placed: ___
- Orders filled: ___

**Issues/Notes**:
- ________________________________
- ________________________________

**Action Items**:
- [ ] ________________________________
- [ ] ________________________________

---

## 🚀 Production Deployment (After Paper Trading Success)

### Pre-Production Checklist
- [ ] 30+ days paper trading completed
- [ ] All success criteria met
- [ ] Performance reviewed and approved
- [ ] Risk parameters confirmed
- [ ] Live account funded with $2,000-$5,000
- [ ] Live API keys generated and configured
- [ ] Backup plan documented

### Production Commands
```bash
# IMPORTANT: Remove --paper flag for live trading
uv run alpaca-options run --strategy vertical_spread --config config/production.yaml

# Monitor live account
uv run alpaca-options dashboard
```

### Production Monitoring (Higher Frequency)
- **First Week**: Daily check-ins
- **Weeks 2-4**: Every 2-3 days
- **After 30 days**: Weekly reviews

### Emergency Stop Conditions
- Max drawdown > 15%
- Win rate < 70% over 10+ trades
- Systematic execution failures
- Account equity < $1,500

**Emergency Stop Command**:
```bash
# Stop the bot immediately
# Cancel all open orders
uv run alpaca-options stop --cancel-orders
```

---

## 📞 Support & Resources

- **Alpaca Status**: https://status.alpaca.markets/
- **Alpaca Docs**: https://docs.alpaca.markets/
- **Paper Trading Dashboard**: https://app.alpaca.markets/paper/dashboard
- **Project Issues**: https://github.com/anthropics/claude-code/issues

---

## ✅ Final Approval

**Paper Trading Results Approved**:
- [ ] Signed: ___________________ Date: ___________

**Production Deployment Approved**:
- [ ] Signed: ___________________ Date: ___________

---

*Keep this checklist updated throughout your deployment process*
