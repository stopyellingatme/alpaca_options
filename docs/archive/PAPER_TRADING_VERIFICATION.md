# Paper Trading Engine Verification

This document explains how the paper trading engine integrates strategies and the screener to find and execute opportunities.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Trading Engine                             │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │   Strategy       │    │   Screener       │                  │
│  │   Registry       │    │   Integration    │                  │
│  └────────┬─────────┘    └────────┬─────────┘                  │
│           │                       │                             │
│           ▼                       ▼                             │
│  ┌──────────────────────────────────────────────┐              │
│  │         Active Strategies                     │              │
│  │  • Vertical Spread (enabled)                  │              │
│  │  • Debit Spread (disabled)                    │              │
│  │  • Iron Condor (disabled)                     │              │
│  │  • Wheel (disabled)                           │              │
│  └──────────────────────────────────────────────┘              │
│                                                                  │
│  Flow:                                                           │
│  1. Screener scans universe every 5 minutes                     │
│  2. Finds opportunities (RSI oversold/overbought)               │
│  3. Adds symbols to _screener_symbols set                       │
│  4. Engine processes symbols through active strategies           │
│  5. Strategies generate signals                                  │
│  6. Signals processed through risk manager                       │
│  7. Orders executed via Alpaca                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Current Configuration Status

### ✅ Strategies Enabled

From `config/paper_trading.yaml`:

```yaml
strategies:
  vertical_spread:
    enabled: true           # ✅ ACTIVE
    allocation: 0.3
    config:
      underlyings:
        - "QQQ"             # Primary underlying
      delta_target: 0.20    # 20 delta short strike
      min_credit: 30        # Min $30 credit per spread
      min_dte: 30           # 30-45 DTE entry window
      max_dte: 45
      rsi_oversold: 45      # RSI ≤45 = bullish signal
      rsi_overbought: 55    # RSI ≥55 = bearish signal
```

**Strategy Flow**:
1. Engine initializes `VerticalSpreadStrategy` on startup
2. Strategy registers for QQQ data feed
3. On each market data update:
   - Calculate RSI from price history
   - Store indicator values by symbol
4. On option chain update:
   - Check RSI stored earlier
   - If RSI ≤45 (oversold) → look for bull put spread
   - If RSI ≥55 (overbought) → look for bear call spread
   - If conditions met → generate OptionSignal
5. Signal sent to engine for execution

### ✅ Screener Enabled

From `config/paper_trading.yaml`:

```yaml
screener:
  enabled: true                     # ✅ ACTIVE
  mode: "hybrid"                    # Technical + Options analysis
  universe: "options_friendly"      # QQQ, SPY, and liquid options stocks
  max_results: 10
  min_combined_score: 60.0          # Minimum 60/100 score to qualify

  technical_weight: 0.6             # 60% weight on RSI, MA, volume
  options_weight: 0.4               # 40% weight on IV, liquidity

  auto_refresh_seconds: 300         # Scan every 5 minutes

  technical_criteria:
    rsi_oversold: 45                # Match strategy thresholds
    rsi_overbought: 55
    min_volume: 1000000

  options_criteria:
    min_iv_rank: 30
    min_open_interest: 100
    max_bid_ask_spread: 0.05
    min_dte: 30
    max_dte: 45
```

**Screener Flow**:
1. Engine starts screener integration on startup (if `screener.enabled = true`)
2. Screener scans universe every 5 minutes:
   - Technical analysis: RSI, moving averages, volume
   - Options analysis: IV rank, open interest, bid-ask spread
   - Combines scores: `total = (0.6 * technical) + (0.4 * options)`
   - Filters results where `total ≥ 60.0`
3. For each qualifying opportunity:
   - Adds symbol to `_screener_symbols` set
   - Publishes `SCREENER_OPPORTUNITY` event
   - Engine processes symbol through active strategies
4. Strategies receive option chains for screener symbols
5. If conditions met → generate signals

## How to Verify It's Working

### 1. Check Logs on Startup

```bash
uv run python scripts/run_paper_trading.py -d -s -u options_friendly
```

**Expected Log Messages**:

```
INFO - Starting trading engine...
INFO - Connected to Alpaca - Account Equity: $5,000.00, Trading Capital Capped at: $5,000.00
INFO - Initialized strategy: vertical_spread
INFO - Starting screener integration...
INFO - Screener integration started successfully
INFO - Trading engine started
```

### 2. Monitor Screener Activity

The dashboard shows screener status every 60 seconds:

```
[10:15:30] Screener: 12 scans, Trading queue: 0, Total found: 45
Discovered symbols: QQQ, SPY, AAPL, MSFT, TSLA...
```

**What this means**:
- `12 scans`: Screener has run 12 times (12 scans × 5 min = 60 minutes)
- `Trading queue: 0`: No pending opportunities in queue (being processed)
- `Total found: 45`: Screener has discovered 45 symbols total since start
- `Discovered symbols`: Top symbols currently in screener set

### 3. Watch for Signals

When conditions are met, you'll see:

```
INFO - Screener opportunity: QQQ (BULLISH_PUT_CREDIT) Score: 67.5, Priority: MEDIUM
INFO - Processing screener symbol: QQQ through strategies
INFO - vertical_spread: Analyzing QQQ (RSI: 43.2, IV Rank: 35%)
INFO - vertical_spread: Generated SELL_PUT_SPREAD signal for QQQ
INFO - Executing signal: SELL_PUT_SPREAD on QQQ, legs: 2
INFO - Order placed successfully: QQQ 420/415 Put Spread
```

### 4. Check Active Positions

```bash
# In another terminal
uv run python -c "
from alpaca_options.core.config import load_config
from alpaca_options.alpaca.client import AlpacaClient

settings = load_config('config/paper_trading.yaml')
settings.alpaca.paper = True
client = AlpacaClient(settings)
positions = client.trading.get_all_positions()

for pos in positions:
    print(f'{pos.symbol}: {pos.qty} @ ${pos.avg_entry_price}')
"
```

## Troubleshooting

### Issue: "No screener results"

**Symptom**: `Screener scan complete: 0 opportunities found`

**Likely Cause**:
- Market conditions are neutral (RSI between 45-55 for all symbols)
- IV rank < 30% across the board
- No strong technical signals currently

**Action**: Wait for market conditions to change. This is normal during calm markets.

### Issue: "Strategy not generating signals"

**Symptom**: Screener finds opportunities but no orders placed

**Diagnosis**:
1. Check if strategy is enabled:
   ```bash
   grep "enabled:" config/paper_trading.yaml
   ```

2. Check risk manager rejections in logs:
   ```bash
   tail -f data/logs/paper_trading.log | grep -i "rejected\|violation"
   ```

3. Common rejections:
   - Max concurrent positions (3) already reached
   - Position size exceeds 25% of equity
   - Buying power insufficient
   - DTE out of range (must be 30-45 for entry)

### Issue: "Screener not running"

**Symptom**: No screener status messages in logs

**Check**:
```bash
grep "screener.enabled" config/paper_trading.yaml
```

Should show: `enabled: true`

**Fix**: Ensure you're starting with screener flag:
```bash
uv run python scripts/run_paper_trading.py -d -s -u options_friendly
```

## Key Code Locations

If you need to debug or modify behavior:

1. **Engine initialization**: `src/alpaca_options/core/engine.py:149` (`async def start`)
2. **Strategy loading**: `src/alpaca_options/core/engine.py:279` (`async def _initialize_strategies`)
3. **Screener setup**: `src/alpaca_options/core/engine.py:976` (`async def _start_screener_integration`)
4. **Opportunity processing**: `src/alpaca_options/core/engine.py:1104` (`async def _process_screener_opportunities`)
5. **Vertical spread logic**: `src/alpaca_options/strategies/vertical_spread.py`

## Summary

**The paper trading engine is properly configured to**:

✅ Load and initialize the vertical spread strategy
✅ Start the screener integration (if `-s` flag used)
✅ Scan for opportunities every 5 minutes
✅ Feed opportunities to active strategies
✅ Generate signals when conditions met
✅ Execute orders through risk management
✅ Monitor positions for profit/loss exits

**Current setup**:
- Strategy: Vertical Spread (credit spreads)
- Underlyings: QQQ + screener discoveries
- Screener: Hybrid mode, options_friendly universe
- Scan frequency: Every 5 minutes
- Min score: 60/100 to qualify

**Launch command**:
```bash
uv run python scripts/run_paper_trading.py -d -s -u options_friendly
```

The system is ready to deploy!
