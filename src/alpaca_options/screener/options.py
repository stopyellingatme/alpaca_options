"""Options-based stock screener."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from alpaca_options.screener.base import (
    BaseScreener,
    ScreenerResult,
    ScreenerType,
    ScreeningCriteria,
)
from alpaca_options.screener.filters import (
    calculate_bid_ask_spread_percent,
    is_tight_spread,
    score_options_setup,
)

logger = logging.getLogger(__name__)


class OptionsScreener(BaseScreener):
    """Screen stocks based on options-specific criteria.

    Uses options chain data to find stocks with:
    - Good options liquidity (volume, open interest)
    - Tight bid-ask spreads
    - High/low IV rank
    - Multiple expirations available

    Requires access to both trading and options data clients.
    """

    def __init__(
        self,
        trading_client,
        options_data_client,
        criteria: Optional[ScreeningCriteria] = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Initialize the options screener.

        Args:
            trading_client: Alpaca TradingClient for contract info.
            options_data_client: Alpaca OptionHistoricalDataClient for quotes.
            criteria: Screening criteria to apply.
            cache_ttl_seconds: Cache TTL in seconds.
        """
        super().__init__(criteria, cache_ttl_seconds)
        self._trading_client = trading_client
        self._data_client = options_data_client

    @property
    def screener_type(self) -> ScreenerType:
        return ScreenerType.OPTIONS

    async def screen_symbol(self, symbol: str) -> ScreenerResult:
        """Screen a single symbol for options trading suitability.

        Args:
            symbol: Stock symbol to screen.

        Returns:
            ScreenerResult with pass/fail and metrics.
        """
        try:
            # Get option contracts for this underlying
            contracts = await self._fetch_contracts(symbol)

            if not contracts:
                return ScreenerResult(
                    symbol=symbol,
                    passed=False,
                    score=0.0,
                    filter_results={"has_options": False},
                )

            # Count unique expirations
            expirations = set()
            for c in contracts:
                if c.get("expiration"):
                    expirations.add(c["expiration"])

            num_expirations = len(expirations)

            # Check for weekly expirations (7 days apart or less)
            has_weeklies = self._check_weekly_expirations(list(expirations))

            # Get snapshots for a sample of contracts to check liquidity
            sample_contracts = self._select_sample_contracts(contracts, max_contracts=20)

            if not sample_contracts:
                return ScreenerResult(
                    symbol=symbol,
                    passed=False,
                    score=0.0,
                    num_expirations=num_expirations,
                    has_weeklies=has_weeklies,
                    filter_results={"has_options": True, "has_quotes": False},
                )

            # Fetch snapshots for sample contracts
            snapshots = await self._fetch_snapshots(
                [c["symbol"] for c in sample_contracts]
            )

            # Calculate aggregate metrics
            total_open_interest = 0
            total_volume = 0
            spreads = []
            ivs = []

            for contract_symbol, snap in snapshots.items():
                if snap:
                    # Note: Using what's available from Alpaca snapshot
                    if snap.get("bid") and snap.get("ask"):
                        spread_pct = calculate_bid_ask_spread_percent(
                            snap["bid"], snap["ask"]
                        )
                        spreads.append(spread_pct)

                    if snap.get("implied_volatility"):
                        ivs.append(snap["implied_volatility"])

            avg_spread = sum(spreads) / len(spreads) if spreads else 100.0
            avg_iv = sum(ivs) / len(ivs) if ivs else None

            # Apply filters
            filter_results = {
                "has_options": True,
                "has_quotes": len(snapshots) > 0,
            }

            # Open interest filter
            oi_ok = total_open_interest >= self.criteria.min_open_interest
            filter_results["min_open_interest"] = oi_ok

            # Bid-ask spread filter
            spread_ok = avg_spread <= self.criteria.max_bid_ask_spread_percent
            filter_results["max_spread"] = spread_ok

            # Expirations filter
            exp_ok = num_expirations >= self.criteria.min_expirations
            filter_results["min_expirations"] = exp_ok

            # Weekly options filter (optional)
            weeklies_ok = True
            if self.criteria.has_weekly_options:
                weeklies_ok = has_weeklies
                filter_results["has_weeklies"] = has_weeklies

            # IV rank filters (if we have IV data)
            iv_ok = True
            iv_rank = None  # Would need historical IV to calculate

            if self.criteria.min_iv_rank is not None and iv_rank is not None:
                if iv_rank < self.criteria.min_iv_rank:
                    iv_ok = False
                filter_results["min_iv_rank"] = iv_rank >= self.criteria.min_iv_rank

            if self.criteria.max_iv_rank is not None and iv_rank is not None:
                if iv_rank > self.criteria.max_iv_rank:
                    iv_ok = False
                filter_results["max_iv_rank"] = iv_rank <= self.criteria.max_iv_rank

            # Determine if passed all required filters
            passed = all([
                oi_ok or total_open_interest == 0,  # Allow if no OI data
                spread_ok or len(spreads) == 0,  # Allow if no spread data
                exp_ok,
                weeklies_ok,
                iv_ok,
            ])

            # Calculate score
            score = score_options_setup(
                iv_rank=iv_rank,
                open_interest=total_open_interest,
                bid_ask_spread_pct=avg_spread if spreads else None,
                num_expirations=num_expirations,
            )

            return ScreenerResult(
                symbol=symbol,
                passed=passed,
                score=score,
                timestamp=datetime.now(),
                total_open_interest=total_open_interest,
                avg_bid_ask_spread=avg_spread if spreads else None,
                implied_volatility=avg_iv,
                iv_rank=iv_rank,
                num_expirations=num_expirations,
                has_weeklies=has_weeklies,
                filter_results=filter_results,
            )

        except Exception as e:
            logger.error(f"Error screening options for {symbol}: {e}")
            return ScreenerResult(
                symbol=symbol,
                passed=False,
                score=0.0,
                filter_results={"error": str(e)},
            )

    async def _fetch_contracts(self, symbol: str) -> list[dict]:
        """Fetch option contracts for an underlying.

        Args:
            symbol: Underlying symbol.

        Returns:
            List of contract dictionaries.
        """
        from alpaca.trading.requests import GetOptionContractsRequest
        from datetime import date

        try:
            today = date.today()
            exp_gte = today + timedelta(days=7)  # At least 1 week out
            exp_lte = today + timedelta(days=60)  # Up to 60 days

            request = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date_gte=exp_gte,
                expiration_date_lte=exp_lte,
                limit=1000,
            )

            result = self._trading_client.get_option_contracts(request)
            contracts = result.option_contracts or []

            return [
                {
                    "symbol": c.symbol,
                    "underlying": c.underlying_symbol,
                    "option_type": c.type.value if hasattr(c.type, 'value') else str(c.type),
                    "strike": float(c.strike_price),
                    "expiration": c.expiration_date,
                }
                for c in contracts
            ]

        except Exception as e:
            logger.warning(f"Failed to fetch contracts for {symbol}: {e}")
            return []

    async def _fetch_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch option snapshots for contracts.

        Args:
            symbols: List of option contract symbols.

        Returns:
            Dictionary mapping symbols to snapshot data.
        """
        from alpaca.data.requests import OptionSnapshotRequest

        if not symbols:
            return {}

        results = {}

        try:
            # Batch into chunks of 100
            chunk_size = 100
            for i in range(0, len(symbols), chunk_size):
                chunk = symbols[i:i + chunk_size]

                request = OptionSnapshotRequest(symbol_or_symbols=chunk)
                snapshots = self._data_client.get_option_snapshot(request)

                for sym in chunk:
                    snap = snapshots.get(sym)
                    if snap:
                        quote = snap.latest_quote
                        results[sym] = {
                            "bid": float(quote.bid_price) if quote and quote.bid_price else 0,
                            "ask": float(quote.ask_price) if quote and quote.ask_price else 0,
                            "implied_volatility": float(snap.implied_volatility) if snap.implied_volatility else None,
                        }

        except Exception as e:
            logger.warning(f"Failed to fetch option snapshots: {e}")

        return results

    def _select_sample_contracts(
        self,
        contracts: list[dict],
        max_contracts: int = 20,
    ) -> list[dict]:
        """Select a representative sample of contracts for analysis.

        Prioritizes ATM options across multiple expirations.

        Args:
            contracts: All available contracts.
            max_contracts: Maximum contracts to sample.

        Returns:
            Sample of contracts.
        """
        if len(contracts) <= max_contracts:
            return contracts

        # Group by expiration
        by_expiration: dict[str, list[dict]] = {}
        for c in contracts:
            exp = str(c.get("expiration", ""))
            if exp not in by_expiration:
                by_expiration[exp] = []
            by_expiration[exp].append(c)

        # Take contracts from each expiration
        sample = []
        expirations = sorted(by_expiration.keys())[:4]  # First 4 expirations

        contracts_per_exp = max_contracts // len(expirations) if expirations else max_contracts

        for exp in expirations:
            exp_contracts = by_expiration[exp]
            # Sort by strike and take middle ones (ATM)
            exp_contracts.sort(key=lambda x: x.get("strike", 0))
            mid = len(exp_contracts) // 2
            start = max(0, mid - contracts_per_exp // 2)
            end = min(len(exp_contracts), start + contracts_per_exp)
            sample.extend(exp_contracts[start:end])

        return sample[:max_contracts]

    def _check_weekly_expirations(self, expirations: list) -> bool:
        """Check if there are weekly expirations available.

        Args:
            expirations: List of expiration dates.

        Returns:
            True if weekly expirations exist.
        """
        if len(expirations) < 2:
            return False

        sorted_exp = sorted(expirations)

        for i in range(1, len(sorted_exp)):
            prev = sorted_exp[i - 1]
            curr = sorted_exp[i]

            # Handle both date and datetime
            if hasattr(prev, 'date'):
                prev = prev.date()
            if hasattr(curr, 'date'):
                curr = curr.date()

            if isinstance(prev, str):
                from datetime import datetime
                prev = datetime.strptime(prev, "%Y-%m-%d").date()
            if isinstance(curr, str):
                from datetime import datetime
                curr = datetime.strptime(curr, "%Y-%m-%d").date()

            diff = (curr - prev).days

            # Weekly = 7 days apart or less
            if diff <= 7:
                return True

        return False

    async def scan_high_iv(
        self,
        symbols: list[str],
        min_iv_rank: float = 50.0,
        max_results: int = 10,
    ) -> list[ScreenerResult]:
        """Scan for stocks with high IV rank (good for selling premium).

        Args:
            symbols: List of symbols to scan.
            min_iv_rank: Minimum IV rank threshold.
            max_results: Maximum results to return.

        Returns:
            List of ScreenerResults sorted by IV rank (highest first).
        """
        original_min_iv = self.criteria.min_iv_rank
        self.criteria.min_iv_rank = min_iv_rank

        try:
            results = await self.scan(symbols, max_results=None)

            high_iv = [
                r for r in results.results
                if r.passed and r.iv_rank is not None and r.iv_rank >= min_iv_rank
            ]
            high_iv.sort(key=lambda x: x.iv_rank or 0, reverse=True)

            return high_iv[:max_results]

        finally:
            self.criteria.min_iv_rank = original_min_iv

    async def scan_tight_spreads(
        self,
        symbols: list[str],
        max_spread: float = 2.0,
        max_results: int = 10,
    ) -> list[ScreenerResult]:
        """Scan for stocks with tight option bid-ask spreads.

        Args:
            symbols: List of symbols to scan.
            max_spread: Maximum bid-ask spread percentage.
            max_results: Maximum results to return.

        Returns:
            List of ScreenerResults sorted by spread (tightest first).
        """
        original_spread = self.criteria.max_bid_ask_spread_percent
        self.criteria.max_bid_ask_spread_percent = max_spread

        try:
            results = await self.scan(symbols, max_results=None)

            tight = [
                r for r in results.results
                if r.passed and r.avg_bid_ask_spread is not None
            ]
            tight.sort(key=lambda x: x.avg_bid_ask_spread or 100)

            return tight[:max_results]

        finally:
            self.criteria.max_bid_ask_spread_percent = original_spread

    async def scan_liquid_options(
        self,
        symbols: list[str],
        min_open_interest: int = 1000,
        max_results: int = 10,
    ) -> list[ScreenerResult]:
        """Scan for stocks with high options liquidity.

        Args:
            symbols: List of symbols to scan.
            min_open_interest: Minimum total open interest.
            max_results: Maximum results to return.

        Returns:
            List of ScreenerResults sorted by open interest.
        """
        original_oi = self.criteria.min_open_interest
        self.criteria.min_open_interest = min_open_interest

        try:
            results = await self.scan(symbols, max_results=None)

            liquid = [
                r for r in results.results
                if r.passed and r.total_open_interest is not None
            ]
            liquid.sort(key=lambda x: x.total_open_interest or 0, reverse=True)

            return liquid[:max_results]

        finally:
            self.criteria.min_open_interest = original_oi
