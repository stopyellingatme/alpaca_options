# Paper Trading Quick Start Guide

**Status**: ✅ READY TO LAUNCH
**Configuration**: Verified and Validated
**Date**: 2025-12-04

---

## ✅ Configuration Summary

### Strategy: Vertical Spread (Credit Spreads)
- **Enabled**: ✅ YES
- **Symbol**: QQQ (Nasdaq-100 ETF)
- **Capital**: $5,000
- **Backtest Results**: +367% returns, 92.6% win rate (Feb-Nov 2024)

### Screener: Dynamic Opportunity Discovery
- **Enabled**: ✅ YES
- **Mode**: HYBRID (technical + options analysis)
- **Universe**: Options-friendly stocks + QQQ/SPY focus
- **Scan Frequency**: Every 5 minutes
- **Scoring**: 60% technical, 40% options metrics

### Risk Management
- **Max Concurrent Positions**: 3
- **Position Size Limit**: 25% ($1,250 max per trade)
- **Max Drawdown**: 20% (backtest showed 1.82%)
- **Daily Loss Limit**: $500
- **Profit Target**: 50% of max profit
- **Stop Loss**: 2x credit received

---

## 🚀 Launch Commands

### Option 1: Dry-Run First (Recommended)
Test without placing orders (1-2 hours):

```bash
uv run alpaca-options run --paper --dry-run --config config/paper_trading.yaml
```

**What This Does**:
- ✅ Processes market data for QQQ
- ✅ Calculates RSI and technical indicators
- ✅ Runs screener every 5 minutes
- ✅ Generates signals when conditions are met
- ❌ Does NOT place orders (dry-run mode)

**Expected Output**:
```
INFO - Alpaca Options Bot - QQQ Paper Trading
INFO - Paper trading mode: ENABLED
INFO - Screener: ENABLED (hybrid mode)
INFO - Strategy: vertical_spread ENABLED for QQQ
INFO - Waiting for market data...
INFO - Screener scan complete: 0 opportunities found (no signals yet)
```

Press **Ctrl+C** to stop when satisfied.

---

### Option 2: Live Paper Trading
Start actual paper trading (places orders in paper account):

```bash
uv run alpaca-options run --paper --config config/paper_trading.yaml
```

**What This Does**:
- ✅ Everything from dry-run mode
- ✅ Places orders in your Alpaca paper account
- ✅ Monitors positions for profit targets/stop losses
- ✅ Automatically closes positions at:
  - 50% profit target
  - 2x credit stop loss
  - 21 DTE (gamma risk avoidance)

---

### Option 3: Monitor Dashboard
Open a second terminal to watch in real-time:

```bash
uv run alpaca-options dashboard --paper
```

**Dashboard Panels**:
- 📊 Open Positions
- 📋 Recent Orders
- 📈 Performance Metrics
- 🔢 Portfolio Greeks
- 📝 Strategy Logs

---

## 🔍 How the Screener Works

### Every 5 Minutes, the Screener:

1. **Scans Options-Friendly Universe**:
   - QQQ (primary focus)
   - SPY (backup)
   - Other liquid options stocks

2. **Technical Analysis** (60% weight):
   - RSI ≤ 45 → Bullish signal → Sell put spread
   - RSI ≥ 55 → Bearish signal → Sell call spread
   - Volume ≥ 1M daily
   - Moving average alignment

3. **Options Analysis** (40% weight):
   - IV Rank ≥ 30% (elevated volatility)
   - Open Interest ≥ 100
   - Bid-ask spread ≤ 5%
   - DTE 30-45 days available

4. **Scoring & Ranking**:
   - Combines technical + options scores
   - Filters out scores < 60/100
   - Ranks top 10 opportunities
   - Sends high-scoring opportunities to strategy

5. **Strategy Execution**:
   - Vertical spread strategy receives opportunities
   - Validates against its own criteria
   - Places orders if all conditions met
   - Manages position through exit

### When to Expect Signals

**QQQ Will Generate Signals When**:
- RSI hits ≤45 (oversold) or ≥55 (overbought)
- IV rank is ≥30% (elevated volatility)
- 30-45 DTE options are available
- Liquidity requirements met

**Frequency**:
- Backtest showed ~1 trade per week (94 trades / 10 months)
- Real-time may vary based on market conditions
- More signals during volatile periods
- Fewer signals during low-volatility, range-bound markets

---

## 📊 Monitoring Commands

### Check Account Status
```bash
uv run alpaca-options account --paper
```

### View Current Positions
```bash
uv run alpaca-options positions --paper
```

### View Recent Orders
```bash
uv run alpaca-options orders --paper --limit 10
```

### Check Performance
```bash
uv run alpaca-options performance --paper
```

### View Logs
```bash
tail -f ./data/logs/paper_trading.log
```

---

## ⚠️ Important Notes

### While Running

1. **Keep Bot Running** - The bot needs to stay active to:
   - Monitor positions for exits
   - Scan for new opportunities every 5 minutes
   - Execute profit targets and stop losses

2. **Don't Manually Intervene** - Let the strategy execute as designed:
   - Don't manually close positions (unless emergency)
   - Don't adjust pending orders
   - Let automated exits work

3. **Check Daily** - Quick daily review (~5 minutes):
   - Open positions count (should be ≤ 3)
   - Any new trades
   - Current P&L
   - Check logs for errors

### First Week Expectations

- **Trades**: 1-2 (depends on market conditions)
- **Signals**: May see multiple per day if volatile
- **Fills**: Should execute close to mid-price
- **Holding Period**: ~2 days average

### If No Signals for 2+ Days

This is **NORMAL** if:
- QQQ RSI is neutral (45-55 range)
- IV rank < 30% (low volatility)
- Market is range-bound and calm

**Don't Panic** - The strategy waits for quality setups!

### Emergency Stop

If you need to stop immediately:

```bash
# Press Ctrl+C in the terminal running the bot

# Or kill all bot processes
pkill -f "alpaca-options run"
```

---

## 📈 Expected Performance (30 Days)

Based on backtest data scaled to 1 month:

| Metric | Target | Notes |
|--------|--------|-------|
| **Trades** | 10-15 | ~1 per week |
| **Win Rate** | 80-95% | Backtest: 92.6% |
| **Avg Win** | $35-$50 | Backtest: $42.96 |
| **Avg Loss** | -$30 to -$45 | Backtest: -$36.59 |
| **Max Drawdown** | < 5% | Backtest: 1.82% |
| **Profit Factor** | > 5.0 | Backtest: 14.59 |

---

## 🎯 Go/No-Go After 30 Days

### ✅ GO to Production (all must be true)
- [ ] At least 10 trades executed
- [ ] Win rate ≥ 80%
- [ ] Max drawdown < 5%
- [ ] No systematic execution issues
- [ ] Screener finding quality opportunities
- [ ] Risk limits functioning correctly

### ⏸️ EXTEND Paper Trading (if any)
- [ ] Win rate < 75%
- [ ] Max drawdown > 10%
- [ ] Fewer than 8 trades
- [ ] Screener not finding opportunities

### ❌ STOP - Do Not Deploy (if any)
- [ ] Win rate < 60%
- [ ] Max drawdown > 20%
- [ ] Systematic failures
- [ ] Risk management broken

---

## 🆘 Troubleshooting

### No Screener Results
**Symptom**: "Screener scan complete: 0 opportunities found"

**Likely Cause**:
- Market conditions neutral (RSI 45-55)
- IV rank < 30% (low volatility)
- No technical signals currently

**Action**: Wait for market conditions to change

### Orders Not Filling
**Symptom**: Orders stuck in "pending_new" status

**Diagnosis**:
```bash
uv run alpaca-options orders --paper --status new
```

**Possible Fixes**:
- Increase `limit_price_buffer` in config to 3-5%
- Verify market is open (Mon-Fri 9:30am-4pm ET)
- Check liquidity (OI ≥ 100)

### High Slippage
**Symptom**: Fills consistently at worst price

**Action**:
- Review fill prices vs mid-price
- Adjust `limit_price_buffer` in config
- Ensure trading during market hours only

---

## 📞 Support

- **Alpaca Status**: https://status.alpaca.markets/
- **Paper Dashboard**: https://app.alpaca.markets/paper/dashboard
- **Logs**: `./data/logs/paper_trading.log`
- **Config**: `config/paper_trading.yaml`

---

## ✅ Deployment Checklist

Before starting:
- [ ] Alpaca paper account active
- [ ] API keys in `.env` file
- [ ] Ran verification: `uv run python scripts/verify_paper_account.py`
- [ ] Read this guide completely
- [ ] Understand expected behavior

Ready to start:
- [ ] Terminal 1: `uv run alpaca-options run --paper --config config/paper_trading.yaml`
- [ ] Terminal 2: `uv run alpaca-options dashboard --paper`
- [ ] Daily check-ins scheduled
- [ ] 30-day review date set

---

**Last Updated**: 2025-12-04
**Configuration File**: `config/paper_trading.yaml`
**Validation Status**: ✅ VERIFIED - Ready for deployment
