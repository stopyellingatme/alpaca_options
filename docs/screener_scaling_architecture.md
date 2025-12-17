# Screener Scaling Architecture

## Design for 500-1000 Symbol Universe

### 1. Tiered Scanning Strategy

```python
# Priority tiers with different scan frequencies
TIER_CONFIG = {
    1: {"symbols": 20, "frequency_sec": 300},   # 5 min - highest priority
    2: {"symbols": 80, "frequency_sec": 600},   # 10 min - medium priority
    3: {"symbols": 400, "frequency_sec": 900},  # 15 min - low priority
}

# Example implementation
class TieredScanner:
    async def run_continuous(self):
        while True:
            # Tier 1: Quick scan of highest priority
            await self.scan_tier(1)
            await asyncio.sleep(60)  # Check every minute

            # Tier 2: Every 10 minutes
            if self.should_scan_tier(2):
                await self.scan_tier(2)

            # Tier 3: Every 15 minutes
            if self.should_scan_tier(3):
                await self.scan_tier(3)
```

### 2. Batch API Requests

```python
# Alpaca supports up to 100 symbols per request
async def batch_fetch_bars(symbols: list[str]) -> dict:
    """Fetch bars for multiple symbols in single request."""
    batches = [symbols[i:i+100] for i in range(0, len(symbols), 100)]

    results = {}
    for batch in batches:
        # Single API call for 100 symbols
        bars = await client.get_stock_bars(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Hour,
            limit=50
        )
        results.update(bars)

    return results

# 1000 symbols = 10 API calls instead of 1000
# Scan time: 10 calls × 0.3 sec = 3 seconds instead of 5 minutes
```

### 3. Advanced Caching

```python
class MultiLevelCache:
    """Three-level caching for efficiency."""

    def __init__(self):
        # L1: In-memory (5 min TTL)
        self._memory_cache = {}

        # L2: Redis (15 min TTL) - optional
        self._redis_cache = None

        # L3: Disk (1 day TTL)
        self._disk_cache = {}

    async def get_with_fallback(self, symbol: str):
        # Try L1 (instant)
        if data := self._memory_cache.get(symbol):
            return data

        # Try L2 (fast)
        if self._redis_cache and (data := await self._redis_cache.get(symbol)):
            self._memory_cache[symbol] = data
            return data

        # Try L3 (slow)
        if data := self._load_from_disk(symbol):
            self._memory_cache[symbol] = data
            return data

        # Fetch from API (slowest)
        data = await self._fetch_from_api(symbol)
        self._save_all_levels(symbol, data)
        return data
```

### 4. Async Concurrent Processing

```python
async def parallel_screen(symbols: list[str], max_concurrent: int = 50):
    """Screen multiple symbols concurrently with rate limiting."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def screen_with_limit(symbol: str):
        async with semaphore:
            return await screen_symbol(symbol)

    # Process 50 symbols at a time
    tasks = [screen_with_limit(s) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in results if not isinstance(r, Exception)]
```

### 5. Dynamic Universe Adjustment

```python
class AdaptiveUniverse:
    """Automatically adjust universe based on performance."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.symbol_scores = {}  # Track success rates

    def update_performance(self, symbol: str, passed: bool, filled: bool):
        """Track which symbols produce good signals."""
        if symbol not in self.symbol_scores:
            self.symbol_scores[symbol] = {"attempts": 0, "fills": 0}

        self.symbol_scores[symbol]["attempts"] += 1
        if filled:
            self.symbol_scores[symbol]["fills"] += 1

    def get_best_universe(self, size: int) -> list[str]:
        """Return top N symbols by fill rate."""
        scored = [
            (symbol, data["fills"] / max(data["attempts"], 1))
            for symbol, data in self.symbol_scores.items()
            if data["attempts"] >= 5  # Min sample size
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:size]]
```

### 6. Performance Monitoring

```python
@dataclass
class ScanMetrics:
    """Track scanner performance metrics."""
    total_symbols: int
    scan_duration_sec: float
    api_calls_made: int
    cache_hit_rate: float
    opportunities_found: int
    symbols_filtered_sec: int
    symbols_filtered_liquidity: int

    @property
    def symbols_per_second(self) -> float:
        return self.total_symbols / self.scan_duration_sec

    @property
    def opportunity_rate(self) -> float:
        return self.opportunities_found / self.total_symbols * 100

# Example metrics
"""
Universe: 1000 symbols
Scan Duration: 2.5 minutes
API Calls: 15 (batched)
Cache Hit Rate: 78%
Opportunities Found: 23
Filtered by SEC: 127
Filtered by Liquidity: 214
Processing Rate: 6.7 symbols/sec
Opportunity Rate: 2.3%
"""
```

## Scalability Limits

### Hardware Requirements
| Universe Size | RAM Usage | CPU Cores | Scan Time |
|--------------|-----------|-----------|-----------|
| 300          | 250 MB    | 1-2       | 30 sec    |
| 500          | 400 MB    | 2-4       | 50 sec    |
| 1000         | 830 MB    | 4-8       | 2.5 min   |

### API Rate Limits
| Data Feed | Rate Limit | Max Symbols (5 min scan) |
|-----------|-----------|-------------------------|
| IEX Free  | 200/min   | ~600 (batched)         |
| SIP Paid  | 300/min   | ~900 (batched)         |

### Practical Limits
- **Position capacity**: 10 max positions = only need 30-50 opportunities
- **Quality threshold**: Only 2-3% of symbols pass all filters
- **Optimal size**: 500 symbols = ~10-15 quality opportunities per scan

## Recommended Implementation Path

### Phase 1: Current (300 symbols) ✅
- Already implemented
- Fast, reliable, sufficient for most accounts

### Phase 2: Optimize Current (Optional)
1. Add batched API requests
2. Implement L1 caching (5 min TTL)
3. Enable tiered scanning

**Benefit**: Reduce 3-min scans to 30 seconds

### Phase 3: Expand to 500 (If Needed)
1. Upgrade to SIP data ($50/mo)
2. Add EXTENDED_500 universe
3. Implement adaptive universe tracking

**Use Case**: $50k+ accounts needing more diversity

### Phase 4: Scale to 1000 (Advanced)
1. Full tiered scanning
2. Multi-level caching (memory + Redis + disk)
3. Concurrent async processing
4. Performance monitoring dashboard

**Use Case**: $100k+ accounts, institutional users

## Cost-Benefit Analysis

| Universe | Monthly Cost | Opportunities/Scan | Scan Time | Recommendation |
|----------|-------------|-------------------|-----------|----------------|
| 300      | $0 (IEX)    | 8-12              | 3 min     | ✅ Best for most |
| 500      | $50 (SIP)   | 10-15             | 1.5 min   | Consider if $50k+ account |
| 1000     | $50 (SIP)   | 15-25             | 2.5 min   | Only if 10+ concurrent positions |

## Conclusion

**For most users**: 300 symbols is optimal
- Covers 95% of liquid options
- Fast scans with free data
- Sufficient opportunities for 3-10 positions
- Lower complexity

**For advanced users**: 500 symbols with SIP data
- Better diversity
- Faster scans (batching)
- Justifies cost at $50k+ account size

**1000+ symbols**: Diminishing returns
- Slower scans
- Higher costs
- Same quality opportunities (most filtered out)
- Adds complexity without proportional benefit
