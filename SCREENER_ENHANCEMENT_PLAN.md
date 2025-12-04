# Screener Enhancement Implementation Plan

**Date**: 2025-12-04
**Status**: PLANNING
**Priority Enhancements**: IV Rank, Technical Indicators, Symbol Expansion

---

## Overview

This document outlines the implementation plan for three major screener enhancements:

1. **IV Rank Calculation** - Calculate historical implied volatility rank for better premium selling opportunities
2. **Additional Technical Indicators** - Add MACD, Bollinger Bands, and more for better signal quality
3. **Symbol Universe Expansion** - Maximize market coverage while respecting API rate limits

---

## Current State Analysis

### Current Capabilities

**Technical Screening**:
- ✅ RSI (14-period)
- ✅ SMA 50/200
- ✅ ATR (Average True Range)
- ✅ Volume analysis (20-day average)
- ✅ Dollar volume

**Options Screening**:
- ✅ Bid-ask spread percentage
- ✅ Open interest
- ✅ Expiration analysis
- ✅ Implied volatility (current)
- ❌ **IV Rank** (not implemented)

**Symbol Coverage**:
- Current: `options_friendly` universe = **~147 symbols**
  - 25 major ETFs
  - Top 50 high-volume options stocks
- Available universes:
  - `sp500`: 100 most liquid S&P 500 (SP500_LIQUID)
  - `nasdaq100`: 101 Nasdaq 100 components
  - `high_volume_options`: 181 high-volume options stocks
  - `sector_etfs`: 20 sector ETFs
  - `etfs`: 25 major ETFs

**Scan Frequency**: Every 5 minutes (300 seconds)

**API Limits** (Alpaca Paper Trading):
- Stock data: 200 requests/minute
- Options data: 200 requests/minute
- No explicit daily limits documented

---

## Enhancement 1: IV Rank Calculation

### What is IV Rank?

**Formula**:
```
IV Rank = (Current IV - 52-week Low IV) / (52-week High IV - 52-week Low IV) × 100
```

**Interpretation**:
- IV Rank = 0: Current IV at 52-week low
- IV Rank = 50: Current IV at midpoint
- IV Rank = 100: Current IV at 52-week high

**Trading Significance**:
- IV Rank > 50: Good for selling premium (credit spreads)
- IV Rank < 50: Good for buying options (debit spreads)
- IV Rank > 70: Excellent for premium selling (high probability of IV contraction)

### Current Limitation

From `src/screener/options.py:153-164`:
```python
# IV rank filters (if we have IV data)
iv_ok = True
iv_rank = None  # Would need historical IV to calculate

if self.criteria.min_iv_rank is not None and iv_rank is not None:
    if iv_rank < self.criteria.min_iv_rank:
        iv_ok = False
```

**Problem**: We don't store or calculate historical IV data.

### Implementation Plan

#### Step 1: Historical IV Data Collection

**New Module**: `src/alpaca_options/screener/iv_data.py`

```python
class IVDataManager:
    """Manages historical implied volatility data for IV rank calculations."""

    def __init__(self, options_data_client, cache_dir: str = "./data/iv_cache"):
        self._client = options_data_client
        self._cache_dir = Path(cache_dir)
        self._iv_history: dict[str, pd.DataFrame] = {}  # symbol → IV history

    async def fetch_historical_iv(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Fetch 1 year of ATM option IV data for a symbol.

        Returns:
            DataFrame with columns: date, implied_volatility
        """
        # Fetch historical option snapshots for ATM options
        # Sample weekly (52 data points per year)
        # Cache results to disk

    def calculate_iv_rank(self, symbol: str, current_iv: float) -> Optional[float]:
        """Calculate IV rank from historical data.

        Args:
            symbol: Stock symbol
            current_iv: Current implied volatility (e.g., 0.32 for 32%)

        Returns:
            IV rank (0-100) or None if insufficient data
        """
        history = self._iv_history.get(symbol)
        if history is None or len(history) < 52:  # Need 1 year minimum
            return None

        iv_min = history['implied_volatility'].min()
        iv_max = history['implied_volatility'].max()

        if iv_max == iv_min:  # No variation
            return 50.0

        iv_rank = ((current_iv - iv_min) / (iv_max - iv_min)) * 100
        return max(0.0, min(100.0, iv_rank))

    async def update_iv_cache(self, symbols: list[str]):
        """Update IV cache for symbols (run daily)."""
        # Fetch latest IV for each symbol
        # Append to historical cache
        # Prune data older than 1 year
```

**Caching Strategy**:
- Store historical IV in SQLite database or CSV files
- File structure: `data/iv_cache/{symbol}.csv`
- Columns: `date, implied_volatility, strike, expiration, days_to_expiry`
- Update: Daily (run once per day, not every scan)
- Retention: 1 year of data

#### Step 2: Integration with OptionsScreener

**Modify**: `src/alpaca_options/screener/options.py`

```python
class OptionsScreener(BaseScreener):
    def __init__(
        self,
        trading_client,
        options_data_client,
        criteria: Optional[ScreeningCriteria] = None,
        cache_ttl_seconds: int = 300,
        iv_data_manager: Optional[IVDataManager] = None,  # NEW
    ):
        # ...
        self._iv_data_manager = iv_data_manager

    async def screen_symbol(self, symbol: str) -> ScreenerResult:
        # ... existing code ...

        # After calculating avg_iv:
        iv_rank = None
        if self._iv_data_manager and avg_iv is not None:
            iv_rank = self._iv_data_manager.calculate_iv_rank(symbol, avg_iv)

        # Use iv_rank in filters and scoring
        # ...
```

#### Step 3: API Considerations

**Historical IV Fetching**:
- Fetch once per symbol on initialization (365 API calls for 365 symbols)
- Daily updates (1 API call per symbol per day)
- Use weekly sampling to reduce data size (52 data points per year)

**Initial Backfill**:
```python
# Run once to populate cache
async def backfill_iv_data(symbols: list[str]):
    for symbol in symbols:
        # Fetch 1 year of weekly ATM option snapshots
        # ~52 API calls per symbol
        # For 300 symbols: ~15,600 API calls (one-time cost)
        # Spread over multiple days if needed
```

**Daily Updates**:
```python
# Run daily at market close
async def update_daily_iv():
    for symbol in tracked_symbols:
        # Fetch today's ATM option snapshot
        # 1 API call per symbol
        # For 300 symbols: 300 API calls/day
```

#### Step 4: Scoring Integration

**Enhance**: `src/alpaca_options/screener/filters.py`

```python
def score_options_setup(
    iv_rank: Optional[float],
    open_interest: int,
    bid_ask_spread_pct: Optional[float],
    num_expirations: int,
) -> float:
    """Score options setup quality (0-100).

    Factors:
    - IV rank (40% weight): Higher rank = better for selling premium
    - Liquidity (30%): Open interest and spreads
    - Availability (30%): Number of expirations
    """
    score = 0.0

    # IV rank scoring (0-40 points)
    if iv_rank is not None:
        if iv_rank >= 70:
            score += 40  # Excellent for premium selling
        elif iv_rank >= 50:
            score += 30  # Good for premium selling
        elif iv_rank >= 30:
            score += 20  # Moderate
        else:
            score += 10  # Low IV (better for buying)
    else:
        score += 20  # Neutral if no IV rank data

    # Liquidity scoring (0-30 points)
    # ...existing logic...

    # Availability scoring (0-30 points)
    # ...existing logic...

    return min(100.0, score)
```

---

## Enhancement 2: Additional Technical Indicators

### New Indicators to Add

#### 1. MACD (Moving Average Convergence Divergence)

**Formula**:
```
MACD Line = 12-period EMA - 26-period EMA
Signal Line = 9-period EMA of MACD
Histogram = MACD - Signal
```

**Signals**:
- MACD crosses above Signal → Bullish
- MACD crosses below Signal → Bearish
- Histogram expanding → Trend strengthening

**Implementation**:
```python
def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> tuple[float, float, float]:
    """Calculate MACD, signal, and histogram.

    Returns:
        (macd_line, signal_line, histogram)
    """
    ema_fast = prices.ewm(span=fast).mean().iloc[-1]
    ema_slow = prices.ewm(span=slow).mean().iloc[-1]
    macd_line = ema_fast - ema_slow

    # Calculate signal line (9-period EMA of MACD)
    macd_series = prices.ewm(span=fast).mean() - prices.ewm(span=slow).mean()
    signal_line = macd_series.ewm(span=signal).mean().iloc[-1]

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
```

#### 2. Bollinger Bands

**Formula**:
```
Middle Band = 20-period SMA
Upper Band = Middle Band + (2 × std dev)
Lower Band = Middle Band - (2 × std dev)
```

**Signals**:
- Price near Lower Band → Oversold (bullish)
- Price near Upper Band → Overbought (bearish)
- Bandwidth: (Upper - Lower) / Middle → Volatility measure

**Implementation**:
```python
def calculate_bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> tuple[float, float, float, float]:
    """Calculate Bollinger Bands.

    Returns:
        (middle, upper, lower, bandwidth_pct)
    """
    middle = prices.rolling(period).mean().iloc[-1]
    std = prices.rolling(period).std().iloc[-1]

    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    bandwidth_pct = ((upper - lower) / middle) * 100

    return middle, upper, lower, bandwidth_pct
```

#### 3. Stochastic Oscillator

**Formula**:
```
%K = ((Close - Low14) / (High14 - Low14)) × 100
%D = 3-period SMA of %K
```

**Signals**:
- %K > 80 → Overbought
- %K < 20 → Oversold
- %K crosses above %D → Bullish
- %K crosses below %D → Bearish

**Implementation**:
```python
def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> tuple[float, float]:
    """Calculate Stochastic Oscillator.

    Returns:
        (k_value, d_value)
    """
    lowest_low = low.rolling(k_period).min().iloc[-1]
    highest_high = high.rolling(k_period).max().iloc[-1]

    k_value = ((close.iloc[-1] - lowest_low) / (highest_high - lowest_low)) * 100

    # Calculate %D (SMA of %K)
    k_series = ((close - low.rolling(k_period).min()) /
                (high.rolling(k_period).max() - low.rolling(k_period).min())) * 100
    d_value = k_series.rolling(d_period).mean().iloc[-1]

    return k_value, d_value
```

#### 4. Rate of Change (ROC)

**Formula**:
```
ROC = ((Close - Close_n) / Close_n) × 100
```

**Signals**:
- ROC > 0 → Upward momentum
- ROC < 0 → Downward momentum
- Extreme values → Potential reversal

**Implementation**:
```python
def calculate_roc(prices: pd.Series, period: int = 12) -> float:
    """Calculate Rate of Change.

    Returns:
        ROC percentage
    """
    current = prices.iloc[-1]
    past = prices.iloc[-period]
    return ((current - past) / past) * 100
```

### Integration Plan

**Modify**: `src/alpaca_options/screener/filters.py`

Add all indicator calculation functions.

**Modify**: `src/alpaca_options/screener/technical.py`

```python
async def screen_symbol(self, symbol: str) -> ScreenerResult:
    # ... existing code to fetch bars ...

    # Calculate existing indicators
    rsi = calculate_rsi(close_prices, 14)
    sma_50 = calculate_sma(close_prices, 50)
    sma_200 = calculate_sma(close_prices, 200)
    atr = calculate_atr(high_prices, low_prices, close_prices)

    # NEW: Calculate additional indicators
    macd, macd_signal, macd_hist = calculate_macd(close_prices)
    bb_mid, bb_upper, bb_lower, bb_width = calculate_bollinger_bands(close_prices)
    stoch_k, stoch_d = calculate_stochastic(high_prices, low_prices, close_prices)
    roc_12 = calculate_roc(close_prices, 12)

    # Enhanced signal determination
    signal = self._determine_signal(
        rsi=rsi,
        macd_hist=macd_hist,
        stoch_k=stoch_k,
        bb_position=(current_price - bb_lower) / (bb_upper - bb_lower),
        roc=roc_12,
    )

    # Enhanced scoring
    score = self._calculate_technical_score(
        rsi=rsi,
        macd_hist=macd_hist,
        stoch_k=stoch_k,
        bb_width=bb_width,
        volume_ratio=volume_ratio,
        # ...
    )
```

**New Method**: `_determine_signal()`

```python
def _determine_signal(
    self,
    rsi: float,
    macd_hist: float,
    stoch_k: float,
    bb_position: float,
    roc: float,
) -> str:
    """Determine trading signal from multiple indicators.

    Uses consensus approach: majority of indicators must agree.
    """
    bullish_votes = 0
    bearish_votes = 0

    # RSI vote
    if rsi <= self.criteria.rsi_oversold:
        bullish_votes += 2  # Strong weight
    elif rsi >= self.criteria.rsi_overbought:
        bearish_votes += 2

    # MACD vote
    if macd_hist > 0 and abs(macd_hist) > 0.5:  # Histogram expanding up
        bullish_votes += 1
    elif macd_hist < 0 and abs(macd_hist) > 0.5:  # Histogram expanding down
        bearish_votes += 1

    # Stochastic vote
    if stoch_k < 20:  # Oversold
        bullish_votes += 1
    elif stoch_k > 80:  # Overbought
        bearish_votes += 1

    # Bollinger Bands vote
    if bb_position < 0.2:  # Near lower band
        bullish_votes += 1
    elif bb_position > 0.8:  # Near upper band
        bearish_votes += 1

    # ROC vote
    if roc > 5:  # Strong upward momentum
        bearish_votes += 1  # Potential reversal
    elif roc < -5:  # Strong downward momentum
        bullish_votes += 1  # Potential reversal

    # Consensus: need 3+ votes
    if bullish_votes >= 3:
        return "bullish"
    elif bearish_votes >= 3:
        return "bearish"
    else:
        return "neutral"
```

### Configuration Updates

**Add to**: `src/alpaca_options/core/config.py`

```python
@dataclass
class ScreenerCriteriaConfig:
    """Criteria for technical screening."""

    # Existing
    rsi_period: int = 14
    rsi_oversold: Optional[float] = None
    rsi_overbought: Optional[float] = None

    # NEW: MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    use_macd: bool = True

    # NEW: Bollinger Bands
    bb_period: int = 20
    bb_std_dev: float = 2.0
    use_bollinger: bool = True

    # NEW: Stochastic
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_oversold: float = 20
    stoch_overbought: float = 80
    use_stochastic: bool = True

    # NEW: Rate of Change
    roc_period: int = 12
    use_roc: bool = True
```

---

## Enhancement 3: Symbol Universe Expansion

### Current vs Potential Coverage

| Universe | Current Size | Full Size Available | Notes |
|----------|-------------|---------------------|-------|
| options_friendly | 147 | - | Currently used |
| nasdaq100 | - | 101 | Tech-heavy index |
| sp500 | - | 100 | Most liquid S&P components |
| high_volume_options | - | 181 | Highest options volume |
| Combined (unique) | - | ~300 | After deduplication |

### API Rate Limit Analysis

**Current Scan (every 5 minutes)**:
- 147 symbols
- Stock bars: 147 API calls
- Option contracts: 147 API calls
- Option snapshots: ~20-30 API calls (batched, sample contracts)
- **Total per scan**: ~320 API calls
- **Per hour**: ~3,840 API calls (12 scans × 320)
- **Per day**: ~92,160 API calls

**Alpaca Limits** (Paper Trading):
- **200 requests/minute** per endpoint
- No explicit daily limit documented
- Recommendation: Stay under 10,000 requests/hour

**Proposed Expansion**:
- Target: 300 symbols (2x current)
- Per scan: ~640 API calls
- Per hour: ~7,680 API calls
- **Result**: Still within limits ✅

### Tiered Scanning Strategy

To maximize coverage while staying efficient, implement tiered scanning:

**Tier 1: High Priority** (Every scan - 5 min)
- Major ETFs (25 symbols)
- Mega-cap tech (20 symbols)
- Symbols with recent signals (dynamic)
- **Total**: ~50 symbols

**Tier 2: Medium Priority** (Every other scan - 10 min)
- High-volume options stocks (100 symbols)
- Recent movers (top 20 by volume)
- **Total**: ~120 symbols

**Tier 3: Low Priority** (Every 3rd scan - 15 min)
- Extended S&P 500 liquid (100 symbols)
- Nasdaq 100 remainder (80 symbols)
- **Total**: ~180 symbols

**Dynamic Priority Adjustment**:
```python
class TieredScanStrategy:
    def __init__(self):
        self._tier1: set[str] = set(MAJOR_ETFS + MEGA_CAP_TECH)
        self._tier2: set[str] = set(HIGH_VOLUME_OPTIONS_STOCKS)
        self._tier3: set[str] = set(SP500_LIQUID + NASDAQ_100)
        self._scan_count = 0

    def get_symbols_for_scan(self) -> list[str]:
        """Get symbols for current scan based on tier priority."""
        symbols = list(self._tier1)  # Always scan tier 1

        if self._scan_count % 2 == 0:  # Every other scan
            symbols.extend(self._tier2)

        if self._scan_count % 3 == 0:  # Every 3rd scan
            symbols.extend(self._tier3)

        self._scan_count += 1
        return symbols

    def promote_symbol(self, symbol: str, duration_minutes: int = 30):
        """Promote a symbol to tier 1 temporarily (e.g., after finding signal)."""
        # Move to tier 1 for more frequent scanning
        self._tier1.add(symbol)
        # Set expiration timer to demote back later
```

### Implementation Plan

**Step 1: Create Merged Universe**

```python
# In universes.py
def get_expanded_universe() -> SymbolUniverse:
    """Get expanded universe for maximum coverage."""
    nasdaq = get_nasdaq100_symbols()
    sp500 = get_sp500_symbols()
    high_vol = HIGH_VOLUME_OPTIONS_STOCKS
    etfs = get_major_etfs()

    # Combine and deduplicate
    all_symbols = list(set(nasdaq + sp500 + high_vol + etfs))

    return SymbolUniverse(
        name="Expanded Universe",
        universe_type=UniverseType.CUSTOM,
        symbols=all_symbols,
        description=f"Comprehensive coverage: {len(all_symbols)} symbols",
    )
```

**Step 2: Add Tiered Scanning**

```python
# New file: src/alpaca_options/screener/tiered_scan.py
class TieredScanStrategy:
    # Implementation as shown above
```

**Step 3: Integration with Scanner**

```python
# Modify integration.py
class ScreenerIntegration:
    def __init__(self, ..., tiered_strategy: Optional[TieredScanStrategy] = None):
        self._tiered_strategy = tiered_strategy

    async def _scan_loop(self):
        while self._running:
            # Get symbols for this scan
            if self._tiered_strategy:
                symbols = self._tiered_strategy.get_symbols_for_scan()
            else:
                symbols = self.scanner.get_universe()

            # Run scans with subset
            await self._run_scans(symbols)
```

**Step 4: Configuration**

```yaml
# config/paper_trading.yaml
screener:
  enabled: true
  mode: "hybrid"

  # Universe selection
  universe: "expanded"  # NEW: Use expanded universe
  use_tiered_scanning: true  # NEW: Enable tiered strategy

  # Tiered scanning config
  tier1_interval_seconds: 300   # 5 minutes
  tier2_interval_seconds: 600   # 10 minutes
  tier3_interval_seconds: 900   # 15 minutes
```

---

## Machine Learning Enhancement (Future)

### Concept: ML-Based Opportunity Scoring

**Goal**: Train a model to predict which screener results are most likely to result in profitable trades.

**Approach**:

#### 1. Data Collection

Collect historical data for each screener result:
```python
@dataclass
class ScreenerResultHistorical:
    # Input features
    symbol: str
    timestamp: datetime
    combined_score: float
    technical_score: float
    options_score: float
    rsi: float
    macd_hist: float
    stoch_k: float
    iv_rank: float
    volume_ratio: float
    # ... all other indicators

    # Target label (set after 5 days)
    outcome: str  # "profitable", "loss", "no_trade"
    profit_pct: float  # Actual P&L if traded
```

#### 2. Feature Engineering

Create features from raw indicators:
- RSI divergence from mean
- MACD momentum strength
- IV rank percentile
- Volume spike magnitude
- Combined indicator consensus score
- Time-based features (day of week, market regime)

#### 3. Model Training

**Model Options**:
- Random Forest (good for tabular data, interpretable)
- Gradient Boosting (XGBoost, LightGBM)
- Neural Network (if dataset is large enough)

**Training**:
```python
from sklearn.ensemble import RandomForestClassifier

# Features
X = historical_data[[
    'combined_score', 'rsi', 'macd_hist', 'stoch_k',
    'iv_rank', 'volume_ratio', 'bb_position', 'roc'
]]

# Target: Will this be profitable?
y = historical_data['outcome']  # "profitable" or "not_profitable"

# Train
model = RandomForestClassifier(n_estimators=100)
model.fit(X, y)

# Feature importance
print(model.feature_importances_)
```

#### 4. Integration

```python
class MLScreenerScorer:
    def __init__(self, model_path: str):
        self.model = load_model(model_path)

    def predict_opportunity_quality(self, result: CombinedResult) -> float:
        """Predict probability of profitable trade.

        Returns:
            Probability (0-1) that this opportunity will be profitable.
        """
        features = self._extract_features(result)
        prob = self.model.predict_proba([features])[0][1]  # Prob of "profitable"
        return prob

    def _extract_features(self, result: CombinedResult) -> list[float]:
        return [
            result.combined_score,
            result.rsi or 50,
            result.technical_result.macd_hist if result.technical_result else 0,
            # ... all features
        ]
```

**Use in Screener**:
```python
# After getting screener results
for result in results:
    # Calculate ML-based probability
    ml_score = ml_scorer.predict_opportunity_quality(result)

    # Boost/penalize combined score
    result.combined_score = (
        result.combined_score * 0.7 +  # 70% original score
        ml_score * 100 * 0.3  # 30% ML score
    )
```

#### 5. Continuous Learning

- Collect outcome data for every signal generated
- Retrain model monthly with new data
- A/B test: Compare ML-enhanced vs traditional scoring
- Track metrics: Win rate improvement, Sharpe ratio, max drawdown

---

## Implementation Timeline

### Phase 1: IV Rank (Week 1-2)

**Week 1**:
- [ ] Create `IVDataManager` class
- [ ] Implement historical IV fetching
- [ ] Set up caching infrastructure (SQLite or CSV)
- [ ] Write unit tests

**Week 2**:
- [ ] Integrate with `OptionsScreener`
- [ ] Backfill IV data for current universe (147 symbols)
- [ ] Update scoring logic to use IV rank
- [ ] Test with paper trading

**Deliverables**:
- ✅ IV rank calculated for all symbols
- ✅ Enhanced options scoring
- ✅ Daily IV update process

### Phase 2: Technical Indicators (Week 3-4)

**Week 3**:
- [ ] Implement indicator calculations (MACD, BB, Stochastic, ROC)
- [ ] Add to `filters.py`
- [ ] Update `TechnicalScreener.screen_symbol()`
- [ ] Write unit tests for each indicator

**Week 4**:
- [ ] Implement consensus signal logic
- [ ] Update scoring to use all indicators
- [ ] Backtest with historical data to validate
- [ ] Fine-tune indicator thresholds

**Deliverables**:
- ✅ 4 new indicators (MACD, BB, Stoch, ROC)
- ✅ Multi-indicator consensus signals
- ✅ Improved technical scoring

### Phase 3: Symbol Expansion (Week 5)

**Tasks**:
- [ ] Create expanded universe (300 symbols)
- [ ] Implement tiered scanning strategy
- [ ] Update configuration
- [ ] Monitor API usage
- [ ] Optimize batch requests

**Deliverables**:
- ✅ 300 symbol coverage (2x current)
- ✅ Tiered scanning to manage API limits
- ✅ Dynamic priority adjustment

### Phase 4: Integration & Testing (Week 6)

**Tasks**:
- [ ] Integration testing all three enhancements
- [ ] Paper trading validation (1 week live)
- [ ] Performance monitoring (API usage, scan times)
- [ ] Documentation updates
- [ ] User guide for new features

**Deliverables**:
- ✅ All enhancements working together
- ✅ Validated performance metrics
- ✅ Updated documentation

---

## Success Metrics

### IV Rank Enhancement

- [ ] IV rank calculated for 95%+ of symbols
- [ ] Cache hit rate > 90% (reduces API calls)
- [ ] Screener preferentially finds high IV rank opportunities (>70)

### Technical Indicators

- [ ] Signal quality improved (measured by backtest win rate)
- [ ] Consensus approach reduces false signals by 20%+
- [ ] Indicator diversity improves market regime adaptability

### Symbol Expansion

- [ ] 300 symbols scanned regularly
- [ ] API usage stays under 8,000 requests/hour
- [ ] Average scan time < 30 seconds
- [ ] Opportunity discovery rate increases 50%+

---

## Risk Mitigation

### API Rate Limits

**Risk**: Exceeding Alpaca rate limits (200/min per endpoint)

**Mitigation**:
- Implement request batching (100 symbols per batch)
- Add exponential backoff on rate limit errors
- Monitor API usage in real-time
- Circuit breaker: Pause scans if approaching limits

### Data Quality

**Risk**: Stale or missing IV data affects IV rank accuracy

**Mitigation**:
- Validate IV data on fetch (check for nulls, outliers)
- Fall back to graceful degradation (skip IV rank if data missing)
- Alert on data staleness (>3 days old)
- Manual review of IV cache weekly

### Performance Degradation

**Risk**: Scanning 300 symbols takes too long (>5 minutes)

**Mitigation**:
- Parallel processing (asyncio concurrent requests)
- Optimize indicator calculations (vectorized pandas)
- Cache technical analysis results (TTL: 5 minutes)
- Profile and optimize slow code paths

### Signal Noise

**Risk**: More symbols = more noise, lower quality signals

**Mitigation**:
- Raise minimum combined score (60 → 70)
- Require multiple indicators to agree (consensus)
- Use IV rank to filter (only high IV opportunities)
- Implement signal quality tracking (win rate per symbol)

---

## Configuration Changes

### New Config File: `config/screener_advanced.yaml`

```yaml
screener:
  enabled: true
  mode: "hybrid"

  # Universe
  universe: "expanded"  # 300 symbols
  use_tiered_scanning: true

  # Scoring weights
  technical_weight: 0.5  # Reduced (more indicators now)
  options_weight: 0.3
  iv_rank_weight: 0.2    # NEW: IV rank gets dedicated weight

  # Filtering
  max_results: 20        # Increased (more symbols)
  min_combined_score: 70.0  # Raised (higher quality)

  # IV Rank
  iv_rank:
    enabled: true
    cache_dir: "./data/iv_cache"
    update_daily: true
    update_hour: 17  # 5 PM ET (after market close)
    min_history_days: 252  # Require 1 year
    min_iv_rank_for_credit: 50  # Min IV rank for premium selling

  # Technical indicators
  technical:
    use_macd: true
    use_bollinger: true
    use_stochastic: true
    use_roc: true
    consensus_votes_required: 3  # Need 3+ indicators to agree

  # Tiered scanning
  tiers:
    tier1_symbols:  # Always scan (every 5 min)
      - major_etfs
      - mega_cap_tech
    tier1_interval: 300

    tier2_symbols:  # Every other scan (10 min)
      - high_volume_options
    tier2_interval: 600

    tier3_symbols:  # Every 3rd scan (15 min)
      - sp500
      - nasdaq100
    tier3_interval: 900
```

---

## Testing Plan

### Unit Tests

```python
# test_iv_data.py
def test_calculate_iv_rank():
    manager = IVDataManager(mock_client)
    manager._iv_history['AAPL'] = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=365),
        'implied_volatility': np.random.uniform(0.2, 0.5, 365)
    })

    iv_rank = manager.calculate_iv_rank('AAPL', 0.45)
    assert 0 <= iv_rank <= 100

# test_indicators.py
def test_macd_calculation():
    prices = pd.Series([...])  # Sample data
    macd, signal, hist = calculate_macd(prices)
    assert isinstance(macd, float)
    assert isinstance(signal, float)
    assert hist == macd - signal
```

### Integration Tests

```python
# test_enhanced_screener.py
async def test_screener_with_all_enhancements():
    # Set up screener with IV data, new indicators, expanded universe
    scanner = Scanner(...)
    results = await scanner.scan()

    # Verify results have all new fields
    assert all(r.iv_rank is not None for r in results)
    assert all(hasattr(r.technical_result, 'macd_hist') for r in results)
    assert len(results) > 0  # Found opportunities
```

### Backtesting Validation

```python
# Backtest with enhanced screener vs baseline
baseline_results = backtest_with_baseline_screener()
enhanced_results = backtest_with_enhanced_screener()

print(f"Baseline Win Rate: {baseline_results.win_rate}")
print(f"Enhanced Win Rate: {enhanced_results.win_rate}")
print(f"Improvement: {enhanced_results.win_rate - baseline_results.win_rate}")
```

---

## Documentation Updates

1. **SCREENER_INTEGRATION_VERIFIED.md**: Update with new components
2. **CLAUDE.md**: Add new indicator explanations
3. **PAPER_TRADING_QUICKSTART.md**: Update with new config options
4. **New file**: `IV_RANK_GUIDE.md` - Explain IV rank and usage
5. **New file**: `TECHNICAL_INDICATORS_REFERENCE.md` - Document all indicators

---

## Next Steps

1. Review this plan and approve enhancements
2. Create feature branch: `feature/screener-enhancements`
3. Begin Phase 1: IV Rank implementation
4. Test incrementally after each phase
5. Deploy to paper trading after Phase 3
6. Monitor for 1 week before proceeding to Phase 4

---

**Questions for Discussion**:

1. Should we implement all 3 enhancements, or prioritize certain ones?
2. For symbol expansion: 300 symbols or start smaller (200)?
3. IV Rank caching: SQLite database or CSV files?
4. Should we implement ML scoring in Phase 1 or defer to later?
5. Any other indicators you'd like to see added?

---

*Last Updated: 2025-12-04*
*Status: READY FOR REVIEW*
