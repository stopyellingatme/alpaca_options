"""Screener integration module for trading and backtesting engines.

This module provides:
- ScreenerIntegration: Bridges screener results with trading/backtest engines
- OpportunityQueue: Thread-safe queue for discovered opportunities
- Automatic routing of opportunities to appropriate engines
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

from alpaca_options.screener.scanner import Scanner, ScannerConfig, CombinedResult, ScanMode
from alpaca_options.screener.base import ScreeningCriteria

logger = logging.getLogger(__name__)


class OpportunityType(Enum):
    """Type of opportunity discovered."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    HIGH_IV = "high_iv"
    LOW_IV = "low_iv"
    HIGH_VOLUME = "high_volume"
    GENERAL = "general"


class OpportunityPriority(Enum):
    """Priority level for opportunities."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4  # Time-sensitive opportunities


@dataclass
class Opportunity:
    """Represents a discovered trading opportunity."""

    symbol: str
    opportunity_type: OpportunityType
    priority: OpportunityPriority
    score: float
    screener_result: CombinedResult
    discovered_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "Opportunity") -> bool:
        """Compare opportunities for sorting in priority queue.

        Higher priority and higher scores should come first.
        """
        if not isinstance(other, Opportunity):
            return NotImplemented
        # Primary: priority (higher priority = lower value after negation)
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        # Secondary: score (higher score comes first)
        if self.score != other.score:
            return self.score > other.score
        # Tertiary: discovery time (older first)
        return self.discovered_at < other.discovered_at

    def __eq__(self, other: object) -> bool:
        """Check equality based on symbol and discovery time."""
        if not isinstance(other, Opportunity):
            return NotImplemented
        return (self.symbol == other.symbol and
                self.discovered_at == other.discovered_at)

    @property
    def is_expired(self) -> bool:
        """Check if opportunity has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def time_remaining(self) -> Optional[timedelta]:
        """Get time remaining before expiration."""
        if self.expires_at is None:
            return None
        return self.expires_at - datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "opportunity_type": self.opportunity_type.value,
            "priority": self.priority.value,
            "score": self.score,
            "discovered_at": self.discovered_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "price": self.screener_result.price,
            "rsi": self.screener_result.rsi,
            "signal": self.screener_result.signal,
            "iv": self.screener_result.implied_volatility,
            "metadata": self.metadata,
        }


class OpportunityQueue:
    """Thread-safe priority queue for opportunities."""

    def __init__(self, max_size: int = 100) -> None:
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._opportunities: dict[str, Opportunity] = {}
        self._lock = asyncio.Lock()

    async def add(self, opportunity: Opportunity) -> bool:
        """Add an opportunity to the queue.

        Returns:
            True if added, False if duplicate or queue full.
        """
        async with self._lock:
            # Check for duplicate
            if opportunity.symbol in self._opportunities:
                existing = self._opportunities[opportunity.symbol]
                # Only replace if higher priority or better score
                if (opportunity.priority.value <= existing.priority.value and
                    opportunity.score <= existing.score):
                    return False

            # Remove expired entries
            await self._cleanup_expired()

            if self._queue.full():
                return False

            # Priority queue sorts by first element (lower is higher priority)
            # Negate priority so urgent (4) becomes -4 and gets processed first
            priority_key = (-opportunity.priority.value, -opportunity.score)
            await self._queue.put((priority_key, opportunity))
            self._opportunities[opportunity.symbol] = opportunity

            return True

    async def get(self, timeout: float = 1.0) -> Optional[Opportunity]:
        """Get highest priority opportunity.

        Returns:
            Opportunity or None if timeout/empty.
        """
        try:
            _, opportunity = await asyncio.wait_for(
                self._queue.get(),
                timeout=timeout,
            )
            async with self._lock:
                if opportunity.symbol in self._opportunities:
                    del self._opportunities[opportunity.symbol]
            return opportunity
        except asyncio.TimeoutError:
            return None

    async def peek(self) -> list[Opportunity]:
        """Get all opportunities without removing them."""
        async with self._lock:
            return list(self._opportunities.values())

    async def _cleanup_expired(self) -> None:
        """Remove expired opportunities."""
        expired = [
            symbol for symbol, opp in self._opportunities.items()
            if opp.is_expired
        ]
        for symbol in expired:
            del self._opportunities[symbol]

    @property
    def size(self) -> int:
        """Get current queue size."""
        return len(self._opportunities)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._opportunities) == 0


@dataclass
class IntegrationConfig:
    """Configuration for screener integration."""

    # Scanning settings
    scan_interval_seconds: int = 300  # 5 minutes
    bullish_scan_enabled: bool = True
    bearish_scan_enabled: bool = True
    high_iv_scan_enabled: bool = True

    # Opportunity settings
    opportunity_ttl_minutes: int = 60  # How long opportunities are valid
    max_opportunities_per_scan: int = 10
    min_score_for_trading: float = 60.0  # Min score to send to trading engine
    min_score_for_backtest: float = 40.0  # Min score to send to backtest

    # Priority thresholds
    urgent_rsi_oversold: float = 25.0  # Very oversold = urgent
    urgent_rsi_overbought: float = 75.0  # Very overbought = urgent
    urgent_iv_rank: float = 80.0  # Very high IV = urgent

    # Routing
    route_to_trading: bool = True
    route_to_backtest: bool = True
    require_backtest_validation: bool = False  # Require backtest before trading


class ScreenerIntegration:
    """Integrates screener with trading and backtesting engines.

    Runs periodic scans and routes discovered opportunities to:
    1. Trading engine for immediate execution (if time-sensitive)
    2. Backtesting engine for historical validation
    """

    def __init__(
        self,
        scanner: Scanner,
        config: Optional[IntegrationConfig] = None,
    ) -> None:
        self.scanner = scanner
        self.config = config or IntegrationConfig()

        # Opportunity queues
        self._trading_queue = OpportunityQueue(max_size=50)
        self._backtest_queue = OpportunityQueue(max_size=100)

        # State
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._last_scan_time: Optional[datetime] = None
        self._scan_count: int = 0

        # Callbacks for engine integration
        self._on_trading_opportunity: Optional[Callable[[Opportunity], None]] = None
        self._on_backtest_opportunity: Optional[Callable[[Opportunity], None]] = None

        # Discovered opportunities history
        self._opportunity_history: list[Opportunity] = []

    def set_trading_callback(
        self,
        callback: Callable[[Opportunity], None],
    ) -> None:
        """Set callback for trading opportunities."""
        self._on_trading_opportunity = callback

    def set_backtest_callback(
        self,
        callback: Callable[[Opportunity], None],
    ) -> None:
        """Set callback for backtest opportunities."""
        self._on_backtest_opportunity = callback

    async def start(self) -> None:
        """Start the integration service."""
        if self._running:
            logger.warning("Integration already running")
            return

        logger.info("Starting screener integration service")
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())

    async def stop(self) -> None:
        """Stop the integration service."""
        if not self._running:
            return

        logger.info("Stopping screener integration service")
        self._running = False

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass

    async def _scan_loop(self) -> None:
        """Main scanning loop."""
        while self._running:
            try:
                await self._run_scans()
                self._last_scan_time = datetime.now()
                self._scan_count += 1

                # Wait for next scan interval
                await asyncio.sleep(self.config.scan_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scan loop: {e}")
                await asyncio.sleep(30)  # Wait before retry

    async def _run_scans(self) -> None:
        """Run all enabled scans."""
        opportunities: list[Opportunity] = []

        # Run scans in parallel
        tasks = []

        if self.config.bullish_scan_enabled:
            tasks.append(self._scan_bullish())

        if self.config.bearish_scan_enabled:
            tasks.append(self._scan_bearish())

        if self.config.high_iv_scan_enabled:
            tasks.append(self._scan_high_iv())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Scan failed: {result}")
            elif result:
                opportunities.extend(result)

        # Process discovered opportunities
        await self._process_opportunities(opportunities)

    async def _scan_bullish(self) -> list[Opportunity]:
        """Scan for bullish opportunities."""
        opportunities = []

        try:
            results = await self.scanner.scan_bullish(
                max_results=self.config.max_opportunities_per_scan
            )

            for result in results:
                priority = self._determine_priority(result, OpportunityType.BULLISH)

                opp = Opportunity(
                    symbol=result.symbol,
                    opportunity_type=OpportunityType.BULLISH,
                    priority=priority,
                    score=result.combined_score,
                    screener_result=result,
                    expires_at=datetime.now() + timedelta(
                        minutes=self.config.opportunity_ttl_minutes
                    ),
                    metadata={
                        "scan_type": "bullish",
                        "rsi": result.rsi,
                        "signal": result.signal,
                    },
                )
                opportunities.append(opp)

        except Exception as e:
            logger.error(f"Bullish scan failed: {e}")

        return opportunities

    async def _scan_bearish(self) -> list[Opportunity]:
        """Scan for bearish opportunities."""
        opportunities = []

        try:
            results = await self.scanner.scan_bearish(
                max_results=self.config.max_opportunities_per_scan
            )

            for result in results:
                priority = self._determine_priority(result, OpportunityType.BEARISH)

                opp = Opportunity(
                    symbol=result.symbol,
                    opportunity_type=OpportunityType.BEARISH,
                    priority=priority,
                    score=result.combined_score,
                    screener_result=result,
                    expires_at=datetime.now() + timedelta(
                        minutes=self.config.opportunity_ttl_minutes
                    ),
                    metadata={
                        "scan_type": "bearish",
                        "rsi": result.rsi,
                        "signal": result.signal,
                    },
                )
                opportunities.append(opp)

        except Exception as e:
            logger.error(f"Bearish scan failed: {e}")

        return opportunities

    async def _scan_high_iv(self) -> list[Opportunity]:
        """Scan for high IV opportunities."""
        opportunities = []

        try:
            results = await self.scanner.scan_high_iv(
                max_results=self.config.max_opportunities_per_scan
            )

            for result in results:
                priority = self._determine_priority(result, OpportunityType.HIGH_IV)

                opp = Opportunity(
                    symbol=result.symbol,
                    opportunity_type=OpportunityType.HIGH_IV,
                    priority=priority,
                    score=result.combined_score,
                    screener_result=result,
                    expires_at=datetime.now() + timedelta(
                        minutes=self.config.opportunity_ttl_minutes
                    ),
                    metadata={
                        "scan_type": "high_iv",
                        "iv": result.implied_volatility,
                        "iv_rank": result.options_result.iv_rank if result.options_result else None,
                    },
                )
                opportunities.append(opp)

        except Exception as e:
            logger.error(f"High IV scan failed: {e}")

        return opportunities

    def _determine_priority(
        self,
        result: CombinedResult,
        opp_type: OpportunityType,
    ) -> OpportunityPriority:
        """Determine priority for an opportunity."""
        # Check for urgent conditions
        if opp_type == OpportunityType.BULLISH:
            if result.rsi and result.rsi <= self.config.urgent_rsi_oversold:
                return OpportunityPriority.URGENT

        elif opp_type == OpportunityType.BEARISH:
            if result.rsi and result.rsi >= self.config.urgent_rsi_overbought:
                return OpportunityPriority.URGENT

        elif opp_type == OpportunityType.HIGH_IV:
            if (result.options_result and
                result.options_result.iv_rank and
                result.options_result.iv_rank >= self.config.urgent_iv_rank):
                return OpportunityPriority.URGENT

        # Score-based priority
        if result.combined_score >= 80:
            return OpportunityPriority.HIGH
        elif result.combined_score >= 60:
            return OpportunityPriority.MEDIUM
        else:
            return OpportunityPriority.LOW

    async def _process_opportunities(
        self,
        opportunities: list[Opportunity],
    ) -> None:
        """Process and route discovered opportunities."""
        for opp in opportunities:
            # Add to history
            self._opportunity_history.append(opp)

            # Trim history
            if len(self._opportunity_history) > 1000:
                self._opportunity_history = self._opportunity_history[-500:]

            # Route to appropriate queues
            if self.config.route_to_backtest:
                if opp.score >= self.config.min_score_for_backtest:
                    await self._backtest_queue.add(opp)

                    if self._on_backtest_opportunity:
                        try:
                            self._on_backtest_opportunity(opp)
                        except Exception as e:
                            logger.error(f"Backtest callback error: {e}")

            if self.config.route_to_trading:
                if opp.score >= self.config.min_score_for_trading:
                    # Check if backtest validation is required
                    if self.config.require_backtest_validation:
                        # Add to backtest queue first, trading after validation
                        opp.metadata["pending_trading"] = True
                    else:
                        await self._trading_queue.add(opp)

                        if self._on_trading_opportunity:
                            try:
                                self._on_trading_opportunity(opp)
                            except Exception as e:
                                logger.error(f"Trading callback error: {e}")

            logger.info(
                f"Opportunity: {opp.symbol} ({opp.opportunity_type.value}) "
                f"Score: {opp.score:.1f}, Priority: {opp.priority.name}"
            )

    async def get_trading_opportunity(
        self,
        timeout: float = 1.0,
    ) -> Optional[Opportunity]:
        """Get next opportunity for trading engine."""
        return await self._trading_queue.get(timeout=timeout)

    async def get_backtest_opportunity(
        self,
        timeout: float = 1.0,
    ) -> Optional[Opportunity]:
        """Get next opportunity for backtest engine."""
        return await self._backtest_queue.get(timeout=timeout)

    async def get_pending_trading_opportunities(self) -> list[Opportunity]:
        """Get all pending trading opportunities."""
        return await self._trading_queue.peek()

    async def get_pending_backtest_opportunities(self) -> list[Opportunity]:
        """Get all pending backtest opportunities."""
        return await self._backtest_queue.peek()

    def get_opportunity_history(
        self,
        limit: int = 100,
        opp_type: Optional[OpportunityType] = None,
    ) -> list[Opportunity]:
        """Get recent opportunity history."""
        history = self._opportunity_history

        if opp_type:
            history = [o for o in history if o.opportunity_type == opp_type]

        return history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get integration statistics."""
        return {
            "running": self._running,
            "last_scan_time": self._last_scan_time.isoformat() if self._last_scan_time else None,
            "scan_count": self._scan_count,
            "trading_queue_size": self._trading_queue.size,
            "backtest_queue_size": self._backtest_queue.size,
            "total_opportunities_found": len(self._opportunity_history),
        }

    async def run_immediate_scan(
        self,
        symbols: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        """Run an immediate scan outside the regular schedule.

        Args:
            symbols: Optional specific symbols to scan.

        Returns:
            List of discovered opportunities.
        """
        opportunities = []

        # Run a general scan
        try:
            results = await self.scanner.scan(symbols=symbols)

            for result in results:
                # Determine opportunity type from signal
                if result.signal == "bullish":
                    opp_type = OpportunityType.BULLISH
                elif result.signal == "bearish":
                    opp_type = OpportunityType.BEARISH
                elif result.implied_volatility and result.implied_volatility > 0.5:
                    opp_type = OpportunityType.HIGH_IV
                else:
                    opp_type = OpportunityType.GENERAL

                priority = self._determine_priority(result, opp_type)

                opp = Opportunity(
                    symbol=result.symbol,
                    opportunity_type=opp_type,
                    priority=priority,
                    score=result.combined_score,
                    screener_result=result,
                    expires_at=datetime.now() + timedelta(
                        minutes=self.config.opportunity_ttl_minutes
                    ),
                    metadata={"scan_type": "immediate"},
                )
                opportunities.append(opp)

        except Exception as e:
            logger.error(f"Immediate scan failed: {e}")

        # Process opportunities
        await self._process_opportunities(opportunities)

        return opportunities


async def create_integration_from_clients(
    trading_client,
    stock_data_client,
    options_data_client,
    scanner_config: Optional[ScannerConfig] = None,
    integration_config: Optional[IntegrationConfig] = None,
    criteria: Optional[ScreeningCriteria] = None,
) -> ScreenerIntegration:
    """Factory function to create ScreenerIntegration from Alpaca clients.

    Args:
        trading_client: Alpaca TradingClient.
        stock_data_client: Alpaca StockHistoricalDataClient.
        options_data_client: Alpaca OptionHistoricalDataClient.
        scanner_config: Optional scanner configuration.
        integration_config: Optional integration configuration.
        criteria: Optional screening criteria.

    Returns:
        Configured ScreenerIntegration instance.
    """
    scanner = Scanner(
        trading_client=trading_client,
        stock_data_client=stock_data_client,
        options_data_client=options_data_client,
        config=scanner_config,
        criteria=criteria,
    )

    return ScreenerIntegration(
        scanner=scanner,
        config=integration_config,
    )
