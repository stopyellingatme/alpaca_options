"""Data caching layer for screener performance optimization.

Provides efficient caching of market data (bars, quotes, snapshots) to reduce
API calls and improve scan performance.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry with timestamp."""

    data: Any
    timestamp: datetime

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if entry has expired."""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age >= ttl_seconds


class DataCache:
    """In-memory cache for market data with TTL expiration.

    Caches raw API responses (bars, quotes, etc.) to avoid redundant
    requests during scanning. Separate from result caching in BaseScreener.
    """

    def __init__(self, default_ttl_seconds: int = 300):
        """Initialize the data cache.

        Args:
            default_ttl_seconds: Default time-to-live in seconds (5 minutes).
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: str, ttl_seconds: Optional[int] = None) -> Optional[Any]:
        """Get data from cache if not expired.

        Args:
            key: Cache key.
            ttl_seconds: Optional TTL override.

        Returns:
            Cached data or None if expired/missing.
        """
        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        if entry.is_expired(ttl):
            # Remove expired entry
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.data

    def set(self, key: str, data: Any) -> None:
        """Store data in cache with current timestamp.

        Args:
            key: Cache key.
            data: Data to cache.
        """
        self._cache[key] = CacheEntry(data=data, timestamp=datetime.now())

    def get_multi(
        self,
        keys: List[str],
        ttl_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get multiple keys from cache.

        Args:
            keys: List of cache keys.
            ttl_seconds: Optional TTL override.

        Returns:
            Dictionary of key -> data for non-expired entries.
        """
        results = {}
        for key in keys:
            data = self.get(key, ttl_seconds)
            if data is not None:
                results[key] = data
        return results

    def set_multi(self, data_dict: Dict[str, Any]) -> None:
        """Store multiple key-value pairs.

        Args:
            data_dict: Dictionary of key -> data to cache.
        """
        timestamp = datetime.now()
        for key, data in data_dict.items():
            self._cache[key] = CacheEntry(data=data, timestamp=timestamp)

    def delete(self, key: str) -> None:
        """Remove a key from cache.

        Args:
            key: Cache key to remove.
        """
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.debug("Data cache cleared")

    def clear_expired(self, ttl_seconds: Optional[int] = None) -> int:
        """Remove all expired entries from cache.

        Args:
            ttl_seconds: Optional TTL override.

        Returns:
            Number of entries removed.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired(ttl)
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleared {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    @property
    def size(self) -> int:
        """Get number of entries in cache."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return (self._hits / total) * 100

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache metrics.
        """
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "total_requests": self._hits + self._misses,
        }

    def reset_stats(self) -> None:
        """Reset cache statistics counters."""
        self._hits = 0
        self._misses = 0


class BarsDataCache:
    """Specialized cache for stock bars data.

    Uses symbol + timeframe + lookback as composite key.
    """

    def __init__(self, ttl_seconds: int = 300):
        """Initialize bars cache.

        Args:
            ttl_seconds: Cache TTL in seconds.
        """
        self._cache = DataCache(ttl_seconds)

    def _make_key(self, symbol: str, timeframe: str, lookback_days: int) -> str:
        """Create cache key from parameters.

        Args:
            symbol: Stock symbol.
            timeframe: Timeframe string (e.g., 'Day', '1Hour').
            lookback_days: Number of days of historical data.

        Returns:
            Cache key string.
        """
        return f"bars:{symbol}:{timeframe}:{lookback_days}"

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "Day",
        lookback_days: int = 60
    ) -> Optional[List]:
        """Get cached bars for a symbol.

        Args:
            symbol: Stock symbol.
            timeframe: Bar timeframe.
            lookback_days: Days of historical data.

        Returns:
            List of bar objects or None if not cached.
        """
        key = self._make_key(symbol, timeframe, lookback_days)
        return self._cache.get(key)

    def set_bars(
        self,
        symbol: str,
        bars: List,
        timeframe: str = "Day",
        lookback_days: int = 60
    ) -> None:
        """Cache bars for a symbol.

        Args:
            symbol: Stock symbol.
            bars: List of bar objects.
            timeframe: Bar timeframe.
            lookback_days: Days of historical data.
        """
        key = self._make_key(symbol, timeframe, lookback_days)
        self._cache.set(key, bars)

    def get_bars_batch(
        self,
        symbols: List[str],
        timeframe: str = "Day",
        lookback_days: int = 60
    ) -> Dict[str, List]:
        """Get cached bars for multiple symbols.

        Args:
            symbols: List of stock symbols.
            timeframe: Bar timeframe.
            lookback_days: Days of historical data.

        Returns:
            Dictionary of symbol -> bars for cached entries.
        """
        keys = [self._make_key(s, timeframe, lookback_days) for s in symbols]
        cached = self._cache.get_multi(keys)

        # Map back to symbol keys
        result = {}
        for symbol in symbols:
            key = self._make_key(symbol, timeframe, lookback_days)
            if key in cached:
                result[symbol] = cached[key]

        return result

    def set_bars_batch(
        self,
        bars_dict: Dict[str, List],
        timeframe: str = "Day",
        lookback_days: int = 60
    ) -> None:
        """Cache bars for multiple symbols at once.

        Args:
            bars_dict: Dictionary of symbol -> bars.
            timeframe: Bar timeframe.
            lookback_days: Days of historical data.
        """
        cache_dict = {}
        for symbol, bars in bars_dict.items():
            key = self._make_key(symbol, timeframe, lookback_days)
            cache_dict[key] = bars

        self._cache.set_multi(cache_dict)

    def clear(self) -> None:
        """Clear all cached bars."""
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()
