"""Main trading engine orchestrator."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from alpaca_options.core.config import Settings
from alpaca_options.core.events import Event, EventBus, EventType, get_event_bus
from alpaca_options.data.sec_filings import SECFilingsAnalyzer
from alpaca_options.strategies import BaseStrategy, OptionSignal
from alpaca_options.strategies.registry import StrategyRegistry, get_registry

logger = logging.getLogger(__name__)


@dataclass
class ManagedPosition:
    """Tracks an open position with management parameters."""

    position_id: str  # Unique ID for this managed position
    symbol: str  # Option contract symbol
    underlying: str  # Underlying symbol
    entry_time: datetime
    entry_price: float  # Average entry price per contract
    quantity: int
    side: str  # "long" or "short"

    # Spread tracking (for multi-leg positions)
    is_spread: bool = False
    spread_legs: list[str] = field(default_factory=list)  # Related position symbols
    spread_entry_credit: float = 0.0  # Net credit/debit at entry
    spread_max_risk: float = 0.0  # Max loss on the spread

    # Management parameters
    profit_target: Optional[float] = None  # Close when profit >= this
    stop_loss: Optional[float] = None  # Close when loss >= this
    close_dte: int = 7  # Close when DTE <= this
    expiration: Optional[datetime] = None

    # Strategy that created this position
    strategy_name: str = ""
    signal_metadata: dict = field(default_factory=dict)

    def get_dte(self) -> int:
        """Get days to expiration."""
        if self.expiration is None:
            return 999
        return (self.expiration - datetime.now()).days

# Type hint for screener integration (avoid circular import)
ScreenerIntegration = "alpaca_options.screener.integration.ScreenerIntegration"


class TradingEngine:
    """Main trading engine that orchestrates all components.

    Responsible for:
    - Coordinating strategy execution
    - Managing market data subscriptions
    - Processing signals and executing orders
    - Risk management integration
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: Optional[EventBus] = None,
        strategy_registry: Optional[StrategyRegistry] = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus or get_event_bus()
        self.strategy_registry = strategy_registry or get_registry()

        self._running = False
        self._active_strategies: dict[str, BaseStrategy] = {}
        self._pending_signals: asyncio.Queue[OptionSignal] = asyncio.Queue()

        # Alpaca clients (lazily initialized)
        self._alpaca_client = None
        self._data_manager = None
        self._trading_manager = None
        self._risk_manager = None

        # SEC filings analyzer (initialized at startup)
        self._sec_analyzer = SECFilingsAnalyzer(cache_ttl_days=7)

        # Tasks
        self._main_task: Optional[asyncio.Task[None]] = None
        self._signal_processor_task: Optional[asyncio.Task[None]] = None
        self._strategy_loop_task: Optional[asyncio.Task[None]] = None
        self._screener_opportunity_task: Optional[asyncio.Task[None]] = None
        self._position_manager_task: Optional[asyncio.Task[None]] = None

        # Account state
        self._account_info: dict = {}
        self._positions: list = []

        # Managed positions for profit/loss/DTE tracking
        self._managed_positions: dict[str, ManagedPosition] = {}

        # Effective trading capital (may be capped by max_trading_capital)
        self._effective_capital: float = 0.0

        # Screener integration (optional)
        self._screener_integration = None
        self._screener_symbols: set[str] = set()  # Symbols discovered by screener

    @property
    def is_running(self) -> bool:
        """Check if the engine is currently running."""
        return self._running

    @property
    def effective_capital(self) -> float:
        """Get the effective trading capital (may be capped by max_trading_capital)."""
        return self._effective_capital

    @property
    def effective_buying_power(self) -> float:
        """Get the effective buying power (capped by max_trading_capital if set)."""
        account_bp = float(self._account_info.get('buying_power', 0))
        max_cap = self.settings.trading.max_trading_capital
        if max_cap is not None and max_cap > 0:
            return min(account_bp, max_cap)
        return account_bp

    @property
    def alpaca_client(self):
        """Get the Alpaca client."""
        if self._alpaca_client is None:
            from alpaca_options.alpaca.client import AlpacaClient
            self._alpaca_client = AlpacaClient(self.settings)
        return self._alpaca_client

    @property
    def data_manager(self):
        """Get the data manager."""
        if self._data_manager is None:
            from alpaca_options.data.manager import DataManager
            self._data_manager = DataManager(self.alpaca_client, self.event_bus)
        return self._data_manager

    @property
    def trading_manager(self):
        """Get the trading manager."""
        if self._trading_manager is None:
            from alpaca_options.alpaca.trading import TradingManager
            self._trading_manager = TradingManager(self.alpaca_client.trading)
        return self._trading_manager

    async def start(self) -> None:
        """Start the trading engine."""
        if self._running:
            logger.warning("Engine is already running")
            return

        logger.info("Starting trading engine...")
        self._running = True

        # Log SEC filings analyzer initialization
        logger.info("SEC filings analyzer initialized and ready for strategy injection")

        # Start event bus
        await self.event_bus.start()

        # Connect to Alpaca
        try:
            await self.alpaca_client.connect()
            self._account_info = self.alpaca_client.get_account_info()

            # Calculate effective capital (capped by max_trading_capital if set)
            account_equity = float(self._account_info.get('equity', 0))
            max_cap = self.settings.trading.max_trading_capital
            if max_cap is not None and max_cap > 0:
                self._effective_capital = min(account_equity, max_cap)
                logger.info(
                    f"Connected to Alpaca - Account Equity: ${account_equity:,.2f}, "
                    f"Trading Capital Capped at: ${self._effective_capital:,.2f}"
                )
            else:
                self._effective_capital = account_equity
                logger.info(
                    f"Connected to Alpaca - Equity: ${self._effective_capital:,.2f}"
                )
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ERROR,
                    data={"error": str(e), "location": "alpaca_connect"},
                    source="TradingEngine",
                )
            )
            # Continue anyway for paper trading/testing
            if not self.settings.alpaca.paper:
                raise

        # Start data manager
        await self.data_manager.start()

        # Initialize strategies
        await self._initialize_strategies()

        # Subscribe to data for strategy underlyings
        await self._setup_data_subscriptions()

        # Start processing tasks
        self._main_task = asyncio.create_task(self._main_loop())
        self._signal_processor_task = asyncio.create_task(self._process_signals())
        self._strategy_loop_task = asyncio.create_task(self._strategy_loop())
        self._position_manager_task = asyncio.create_task(self._position_management_loop())

        # Start screener integration if enabled
        if self.settings.screener.enabled:
            await self._start_screener_integration()

        # Publish engine started event
        await self.event_bus.publish(
            Event(
                event_type=EventType.ENGINE_STARTED,
                data={
                    "timestamp": datetime.now().isoformat(),
                    "account": self._account_info.get("account_number", ""),
                    "paper": self.settings.alpaca.paper,
                },
                source="TradingEngine",
            )
        )

        logger.info("Trading engine started")

    async def stop(self) -> None:
        """Stop the trading engine gracefully."""
        if not self._running:
            return

        logger.info("Stopping trading engine...")
        self._running = False

        # Stop screener integration
        if self._screener_integration:
            await self._screener_integration.stop()

        # Cancel tasks
        for task in [
            self._main_task,
            self._signal_processor_task,
            self._strategy_loop_task,
            self._screener_opportunity_task,
            self._position_manager_task,
        ]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop data manager
        if self._data_manager:
            await self._data_manager.stop()

        # Cleanup strategies
        await self.strategy_registry.cleanup_all()

        # Disconnect from Alpaca
        if self._alpaca_client:
            await self._alpaca_client.disconnect()

        # Stop event bus
        await self.event_bus.stop()

        # Publish engine stopped event
        await self.event_bus.publish(
            Event(
                event_type=EventType.ENGINE_STOPPED,
                data={"timestamp": datetime.now().isoformat()},
                source="TradingEngine",
            )
        )

        logger.info("Trading engine stopped")

    async def _initialize_strategies(self) -> None:
        """Initialize all enabled strategies from configuration."""
        # Register built-in strategies
        from alpaca_options.strategies.debit_spread import DebitSpreadStrategy
        from alpaca_options.strategies.wheel import WheelStrategy
        from alpaca_options.strategies.vertical_spread import VerticalSpreadStrategy
        from alpaca_options.strategies.iron_condor import IronCondorStrategy

        for strategy_class in [DebitSpreadStrategy, WheelStrategy, VerticalSpreadStrategy, IronCondorStrategy]:
            try:
                self.strategy_registry.register(strategy_class)
            except ValueError:
                pass  # Already registered

        enabled_strategies = self.settings.get_enabled_strategies()

        for name, strategy_config in enabled_strategies.items():
            try:
                instance = await self.strategy_registry.get_instance(
                    name, strategy_config.config
                )
                if instance:
                    self._active_strategies[name] = instance

                    # Inject SEC filings analyzer into strategy
                    instance.set_sec_filings_analyzer(self._sec_analyzer)
                    logger.info(f"Initialized strategy: {name} (SEC analyzer injected)")

                    await self.event_bus.publish(
                        Event(
                            event_type=EventType.STRATEGY_STARTED,
                            data={
                                "strategy": name,
                                "allocation": strategy_config.allocation,
                            },
                            source="TradingEngine",
                        )
                    )
                else:
                    logger.warning(f"Strategy not found in registry: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize strategy {name}: {e}")
                await self.event_bus.publish(
                    Event(
                        event_type=EventType.STRATEGY_ERROR,
                        data={"strategy": name, "error": str(e)},
                        source="TradingEngine",
                    )
                )

    async def _setup_data_subscriptions(self) -> None:
        """Set up data subscriptions for all active strategies."""
        all_underlyings = set()

        for name, strategy_config in self.settings.get_enabled_strategies().items():
            underlyings = strategy_config.config.get("underlyings", [])
            all_underlyings.update(underlyings)

            # Subscribe strategy to its underlyings
            self.data_manager.subscribe_market_data(underlyings, name)
            self.data_manager.subscribe_option_chain(underlyings, name)

        if all_underlyings:
            logger.info(f"Subscribed to {len(all_underlyings)} underlyings")

    async def _main_loop(self) -> None:
        """Main trading loop - handles account updates and position tracking."""
        while self._running:
            try:
                # Update account info periodically
                if self._alpaca_client and self._alpaca_client.is_connected:
                    try:
                        self._account_info = self.alpaca_client.get_account_info()
                        self._positions = self.trading_manager.get_positions()

                        # Update effective capital based on current account
                        account_equity = float(self._account_info.get('equity', 0))
                        max_cap = self.settings.trading.max_trading_capital
                        if max_cap is not None and max_cap > 0:
                            self._effective_capital = min(account_equity, max_cap)
                        else:
                            self._effective_capital = account_equity

                        await self.event_bus.publish(
                            Event(
                                event_type=EventType.ACCOUNT_UPDATE,
                                data={
                                    "equity": self._account_info.get("equity", 0),
                                    "buying_power": self._account_info.get("buying_power", 0),
                                    "effective_capital": self._effective_capital,
                                    "effective_buying_power": self.effective_buying_power,
                                    "positions_count": len(self._positions),
                                },
                                source="TradingEngine",
                            )
                        )
                    except Exception as e:
                        logger.error(f"Failed to update account info: {e}")

                await asyncio.sleep(self.settings.ui.refresh_rate * 5)  # Every 5 refresh cycles

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await self.event_bus.publish(
                    Event(
                        event_type=EventType.ERROR,
                        data={"error": str(e), "location": "main_loop"},
                        source="TradingEngine",
                    )
                )

    async def _strategy_loop(self) -> None:
        """Loop that feeds data to strategies and collects signals."""
        while self._running:
            try:
                for name, strategy in self._active_strategies.items():
                    strategy_config = self.settings.strategies.get(name)
                    if not strategy_config:
                        continue

                    underlyings = strategy_config.config.get("underlyings", [])

                    for underlying in underlyings:
                        try:
                            # Get option chain for the underlying
                            chain = await self.data_manager.get_option_chain(
                                underlying,
                                min_dte=self.settings.risk.min_days_to_expiry,
                                max_dte=self.settings.risk.max_days_to_expiry,
                            )

                            if chain:
                                # Let strategy process the chain
                                signal = await strategy.on_option_chain(chain)

                                if signal and strategy.validate_signal(signal):
                                    await self.submit_signal(signal)

                        except Exception as e:
                            logger.error(
                                f"Error in strategy {name} for {underlying}: {e}"
                            )

                # Wait before next strategy iteration
                await asyncio.sleep(30)  # Check strategies every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
                await asyncio.sleep(30)

    async def _position_management_loop(self) -> None:
        """Monitor open positions for profit targets, stop losses, and DTE exits.

        This loop runs periodically and checks all managed positions to determine
        if they should be closed based on:
        - Profit target reached (e.g., 50% of max profit)
        - Stop loss hit (e.g., 2x credit received as loss)
        - DTE threshold (e.g., close at 21 DTE to avoid gamma risk)
        """
        while self._running:
            try:
                # Sync managed positions with actual positions
                await self._sync_managed_positions()

                # Check each managed position
                positions_to_close: list[tuple[ManagedPosition, str]] = []

                for pos_id, managed_pos in self._managed_positions.items():
                    close_reason = await self._check_position_exit(managed_pos)
                    if close_reason:
                        positions_to_close.append((managed_pos, close_reason))

                # Close positions that meet exit criteria
                for managed_pos, reason in positions_to_close:
                    await self._close_managed_position(managed_pos, reason)

                # Wait before next check (check every 60 seconds)
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in position management loop: {e}")
                await asyncio.sleep(60)

    async def _sync_managed_positions(self) -> None:
        """Synchronize managed positions with actual Alpaca positions.

        Removes managed positions that no longer exist in the account.
        """
        if not self._positions:
            return

        # Get actual position symbols
        actual_symbols = {pos.symbol for pos in self._positions}

        # Remove managed positions that no longer exist
        to_remove = []
        for pos_id, managed_pos in self._managed_positions.items():
            if managed_pos.symbol not in actual_symbols:
                # If it's a spread, check if all legs are gone
                if managed_pos.is_spread:
                    legs_exist = any(leg in actual_symbols for leg in managed_pos.spread_legs)
                    if not legs_exist:
                        to_remove.append(pos_id)
                else:
                    to_remove.append(pos_id)

        for pos_id in to_remove:
            logger.info(f"Removing closed managed position: {pos_id}")
            del self._managed_positions[pos_id]

    async def _check_position_exit(self, managed_pos: ManagedPosition) -> Optional[str]:
        """Check if a position should be closed.

        Args:
            managed_pos: The managed position to check.

        Returns:
            Close reason string if position should be closed, None otherwise.
        """
        # Get current position from Alpaca
        current_position = None
        for pos in self._positions:
            if pos.symbol == managed_pos.symbol:
                current_position = pos
                break

        if not current_position:
            return None

        # Calculate current P&L
        # Position dataclass has: current_price, entry_price, quantity
        current_price = float(current_position.current_price)
        avg_entry_price = float(current_position.entry_price)
        qty = abs(int(current_position.quantity))

        # For options, calculate P&L based on position side
        if managed_pos.side == "short":
            # Short position: profit when price decreases
            pnl_per_contract = (avg_entry_price - current_price) * 100
        else:
            # Long position: profit when price increases
            pnl_per_contract = (current_price - avg_entry_price) * 100

        current_pnl = pnl_per_contract * qty

        # For spreads, use the spread's entry credit for P&L calculation
        if managed_pos.is_spread and managed_pos.spread_entry_credit > 0:
            # Approximate spread P&L (simplified - full calculation would need all leg prices)
            # For credit spreads: profit = credit received - current value of spread
            current_pnl = managed_pos.spread_entry_credit - (current_price * 100 * qty)

        # Check DTE-based exit (highest priority - gamma risk)
        dte = managed_pos.get_dte()
        if dte <= managed_pos.close_dte:
            logger.info(
                f"Position {managed_pos.symbol} DTE ({dte}) <= close_dte ({managed_pos.close_dte})"
            )
            return f"DTE exit ({dte} days remaining)"

        # Check profit target
        if managed_pos.profit_target is not None and current_pnl >= managed_pos.profit_target:
            logger.info(
                f"Position {managed_pos.symbol} hit profit target: "
                f"${current_pnl:.2f} >= ${managed_pos.profit_target:.2f}"
            )
            return f"Profit target (${current_pnl:.2f})"

        # Check stop loss
        if managed_pos.stop_loss is not None and current_pnl <= -managed_pos.stop_loss:
            logger.info(
                f"Position {managed_pos.symbol} hit stop loss: "
                f"${current_pnl:.2f} <= -${managed_pos.stop_loss:.2f}"
            )
            return f"Stop loss (${current_pnl:.2f})"

        return None

    async def _close_managed_position(
        self, managed_pos: ManagedPosition, reason: str
    ) -> None:
        """Close a managed position.

        Args:
            managed_pos: The position to close.
            reason: The reason for closing.
        """
        logger.info(f"Closing position {managed_pos.symbol}: {reason}")

        try:
            if managed_pos.is_spread:
                # Close all spread legs
                for leg_symbol in managed_pos.spread_legs:
                    await self._close_single_position(leg_symbol)
            else:
                await self._close_single_position(managed_pos.symbol)

            # Publish position closed event
            await self.event_bus.publish(
                Event(
                    event_type=EventType.POSITION_CLOSED,
                    data={
                        "symbol": managed_pos.symbol,
                        "underlying": managed_pos.underlying,
                        "reason": reason,
                        "strategy": managed_pos.strategy_name,
                        "entry_time": managed_pos.entry_time.isoformat(),
                        "close_time": datetime.now().isoformat(),
                    },
                    source="TradingEngine",
                )
            )

            # Remove from managed positions
            if managed_pos.position_id in self._managed_positions:
                del self._managed_positions[managed_pos.position_id]

        except Exception as e:
            logger.error(f"Failed to close position {managed_pos.symbol}: {e}")
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ERROR,
                    data={
                        "error": str(e),
                        "location": "close_managed_position",
                        "symbol": managed_pos.symbol,
                    },
                    source="TradingEngine",
                )
            )

    async def _close_single_position(self, symbol: str) -> None:
        """Close a single position by symbol.

        Args:
            symbol: The position symbol to close.
        """
        try:
            # Use trading manager to close position
            await self.trading_manager.close_position(symbol)
            logger.info(f"Submitted close order for {symbol}")
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            raise

    def _register_managed_position(
        self, signal: OptionSignal, order_results: list
    ) -> None:
        """Register a new managed position from a filled signal.

        Args:
            signal: The original signal that was executed.
            order_results: The order results from execution.
        """
        if not order_results:
            return

        # Get management parameters from signal metadata
        metadata = signal.metadata or {}
        profit_target = metadata.get("profit_target")
        stop_loss = metadata.get("stop_loss")
        close_dte = metadata.get("close_dte", 7)

        # For spreads, create a single managed position with all legs
        is_spread = len(signal.legs) > 1

        if is_spread:
            # Create spread managed position
            leg_symbols = [leg.contract_symbol for leg in signal.legs]
            position_id = f"spread_{signal.underlying}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Calculate entry credit for credit spreads
            entry_credit = 0.0
            for leg in signal.legs:
                if leg.side == "sell":
                    entry_credit += leg.limit_price * 100  # Credit from selling
                else:
                    entry_credit -= leg.limit_price * 100  # Debit from buying

            # Get expiration from first leg
            expiration = signal.legs[0].expiration if signal.legs else None

            managed_pos = ManagedPosition(
                position_id=position_id,
                symbol=leg_symbols[0],  # Primary leg symbol
                underlying=signal.underlying,
                entry_time=datetime.now(),
                entry_price=signal.legs[0].limit_price,
                quantity=signal.legs[0].quantity,
                side="short" if signal.legs[0].side == "sell" else "long",
                is_spread=True,
                spread_legs=leg_symbols,
                spread_entry_credit=max(0, entry_credit),
                spread_max_risk=metadata.get("max_risk", 0),
                profit_target=profit_target,
                stop_loss=stop_loss,
                close_dte=close_dte,
                expiration=expiration,
                strategy_name=signal.strategy_name,
                signal_metadata=metadata,
            )
            self._managed_positions[position_id] = managed_pos
            logger.info(
                f"Registered managed spread position: {position_id} "
                f"(profit_target=${profit_target}, stop_loss=${stop_loss}, close_dte={close_dte})"
            )
        else:
            # Single leg position
            leg = signal.legs[0]
            position_id = f"{leg.contract_symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            managed_pos = ManagedPosition(
                position_id=position_id,
                symbol=leg.contract_symbol,
                underlying=signal.underlying,
                entry_time=datetime.now(),
                entry_price=leg.limit_price,
                quantity=leg.quantity,
                side="short" if leg.side == "sell" else "long",
                profit_target=profit_target,
                stop_loss=stop_loss,
                close_dte=close_dte,
                expiration=leg.expiration,
                strategy_name=signal.strategy_name,
                signal_metadata=metadata,
            )
            self._managed_positions[position_id] = managed_pos
            logger.info(
                f"Registered managed position: {position_id} "
                f"(profit_target=${profit_target}, stop_loss=${stop_loss}, close_dte={close_dte})"
            )

    async def _process_signals(self) -> None:
        """Process signals from strategies and execute orders."""
        while self._running:
            try:
                signal = await asyncio.wait_for(
                    self._pending_signals.get(),
                    timeout=1.0,
                )

                logger.info(
                    f"Processing signal from {signal.strategy_name}: "
                    f"{signal.signal_type.value} {signal.underlying}"
                )

                # Publish signal event
                await self.event_bus.publish(
                    Event(
                        event_type=EventType.SIGNAL_GENERATED,
                        data={
                            "strategy": signal.strategy_name,
                            "signal_type": signal.signal_type.value,
                            "underlying": signal.underlying,
                            "confidence": signal.confidence,
                            "legs": len(signal.legs),
                        },
                        source="TradingEngine",
                    )
                )

                # Risk check
                if not await self._check_risk(signal):
                    logger.warning(f"Signal rejected by risk manager: {signal}")
                    continue

                # Execute the signal if trading is enabled
                if self.settings.trading.enabled:
                    await self._execute_signal(signal)
                else:
                    logger.info("Trading disabled - signal not executed")

                self._pending_signals.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing signal: {e}")

    async def _check_risk(self, signal: OptionSignal) -> bool:
        """Check if a signal passes risk checks.

        Args:
            signal: The signal to check.

        Returns:
            True if signal passes all risk checks.
        """
        risk = self.settings.risk

        # Check max positions
        current_positions = len(self._positions)
        if current_positions >= risk.max_contracts_per_trade:
            logger.warning(f"Max positions ({risk.max_contracts_per_trade}) reached")
            return False

        # Check confidence threshold
        if signal.confidence < 0.5:
            logger.warning(f"Signal confidence too low: {signal.confidence}")
            return False

        # More risk checks can be added here:
        # - Portfolio delta limits
        # - Buying power requirements
        # - Correlation limits
        # - etc.

        return True

    async def _execute_signal(self, signal: OptionSignal) -> None:
        """Execute a trading signal.

        Args:
            signal: The signal to execute.
        """
        try:
            # DRY-RUN MODE: Log what would be placed without actually submitting orders
            if self.settings.trading.dry_run:
                logger.info(
                    "[DRY-RUN] Would place order - Strategy: %s, Type: %s, Underlying: %s, Legs: %d",
                    signal.strategy_name,
                    signal.signal_type.value,
                    signal.underlying,
                    len(signal.legs)
                )

                for i, leg in enumerate(signal.legs, 1):
                    logger.info(
                        "[DRY-RUN] Leg %d: %s %d contracts of %s @ strike %s (expires %s)",
                        i,
                        leg.action.upper(),
                        leg.quantity,
                        leg.option_type.upper() if hasattr(leg, 'option_type') else leg.symbol,
                        leg.strike if hasattr(leg, 'strike') else "N/A",
                        leg.expiration.date() if hasattr(leg, 'expiration') else "N/A"
                    )

                # Publish dry-run signal event for dashboard
                await self.event_bus.publish(
                    Event(
                        event_type=EventType.SIGNAL_GENERATED,
                        data={
                            "dry_run": True,
                            "signal_type": signal.signal_type.value,
                            "underlying": signal.underlying,
                            "strategy": signal.strategy_name,
                            "legs": len(signal.legs),
                            "confidence": signal.confidence,
                        },
                        source="TradingEngine",
                    )
                )
                return  # Exit without submitting actual orders

            # LIVE MODE: Submit actual orders
            order_type = self.settings.trading.default_order_type

            results = await self.trading_manager.submit_signal(
                signal=signal,
                order_type=order_type,
                time_in_force="day",
            )

            for result in results:
                logger.info(
                    f"Order submitted: {result.order_id} - "
                    f"{result.side} {result.quantity} {result.symbol} - "
                    f"Status: {result.status.value}"
                )

                await self.event_bus.publish(
                    Event(
                        event_type=EventType.ORDER_SUBMITTED,
                        data={
                            "order_id": result.order_id,
                            "symbol": result.symbol,
                            "side": result.side,
                            "quantity": result.quantity,
                            "status": result.status.value,
                            "strategy": signal.strategy_name,
                        },
                        source="TradingEngine",
                    )
                )

            # Register the position for management (profit targets, stop losses, DTE exits)
            # This enables automatic position monitoring and exit management
            if results:
                self._register_managed_position(signal, results)

        except Exception as e:
            logger.error(f"Failed to execute signal: {e}")
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ERROR,
                    data={
                        "error": str(e),
                        "location": "execute_signal",
                        "signal": signal.signal_type.value,
                    },
                    source="TradingEngine",
                )
            )

    async def submit_signal(self, signal: OptionSignal) -> None:
        """Submit a signal for processing.

        Args:
            signal: The option signal to process.
        """
        await self._pending_signals.put(signal)

    def get_active_strategies(self) -> list[str]:
        """Get list of active strategy names.

        Returns:
            List of active strategy names.
        """
        return list(self._active_strategies.keys())

    def get_strategy_status(self) -> dict[str, dict]:
        """Get status of all active strategies.

        Returns:
            Dictionary mapping strategy names to their status.
        """
        status = {}
        for name, strategy in self._active_strategies.items():
            config = self.settings.strategies.get(name)
            status[name] = {
                "name": name,
                "description": strategy.description,
                "initialized": strategy.is_initialized,
                "allocation": config.allocation if config else 0,
            }
        return status

    def get_account_info(self) -> dict:
        """Get current account information.

        Returns:
            Account info dictionary with effective capital values.
        """
        info = self._account_info.copy()
        # Add effective values (capped by max_trading_capital)
        info['effective_capital'] = self._effective_capital
        info['effective_buying_power'] = self.effective_buying_power
        info['capital_capped'] = (
            self.settings.trading.max_trading_capital is not None
            and self.settings.trading.max_trading_capital > 0
        )
        info['max_trading_capital'] = self.settings.trading.max_trading_capital
        return info

    def get_positions(self) -> list:
        """Get current positions.

        Returns:
            List of Position objects.
        """
        return self._positions

    async def enable_strategy(self, name: str) -> bool:
        """Enable a strategy at runtime.

        Args:
            name: Name of the strategy to enable.

        Returns:
            True if successfully enabled.
        """
        if name in self._active_strategies:
            logger.warning(f"Strategy {name} is already active")
            return True

        strategy_config = self.settings.strategies.get(name)
        if not strategy_config:
            logger.error(f"No configuration found for strategy: {name}")
            return False

        instance = await self.strategy_registry.get_instance(
            name, strategy_config.config
        )
        if instance:
            self._active_strategies[name] = instance

            # Set up data subscriptions for the new strategy
            underlyings = strategy_config.config.get("underlyings", [])
            self.data_manager.subscribe_market_data(underlyings, name)
            self.data_manager.subscribe_option_chain(underlyings, name)

            await self.event_bus.publish(
                Event(
                    event_type=EventType.STRATEGY_STARTED,
                    data={"strategy": name},
                    source="TradingEngine",
                )
            )
            return True

        return False

    async def disable_strategy(self, name: str) -> bool:
        """Disable a strategy at runtime.

        Args:
            name: Name of the strategy to disable.

        Returns:
            True if successfully disabled.
        """
        if name not in self._active_strategies:
            logger.warning(f"Strategy {name} is not active")
            return False

        strategy = self._active_strategies.pop(name)
        await strategy.cleanup()

        await self.event_bus.publish(
            Event(
                event_type=EventType.STRATEGY_STOPPED,
                data={"strategy": name},
                source="TradingEngine",
            )
        )

        return True

    # -------------------------------------------------------------------------
    # Screener Integration Methods
    # -------------------------------------------------------------------------

    async def _start_screener_integration(self) -> None:
        """Initialize and start the screener integration."""
        try:
            from alpaca_options.screener.integration import (
                ScreenerIntegration,
                IntegrationConfig,
                create_integration_from_clients,
            )
            from alpaca_options.screener.scanner import ScannerConfig, ScanMode
            from alpaca_options.screener.base import ScreeningCriteria
            from alpaca_options.screener.universes import UniverseType

            logger.info("Starting screener integration...")

            # Build scanner config from settings
            mode_map = {
                "technical_only": ScanMode.TECHNICAL_ONLY,
                "options_only": ScanMode.OPTIONS_ONLY,
                "hybrid": ScanMode.HYBRID,
            }
            universe_map = {
                "sp500": UniverseType.SP500,
                "nasdaq100": UniverseType.NASDAQ100,
                "options_friendly": UniverseType.OPTIONS_FRIENDLY,
                "etfs": UniverseType.ETFS,
                "sector_etfs": UniverseType.SECTOR_ETFS,
            }

            scanner_config = ScannerConfig(
                mode=mode_map.get(self.settings.screener.mode, ScanMode.HYBRID),
                universe_type=universe_map.get(
                    self.settings.screener.universe, UniverseType.OPTIONS_FRIENDLY
                ),
                custom_symbols=self.settings.screener.custom_symbols,
                max_results=self.settings.screener.max_results,
                min_combined_score=self.settings.screener.min_combined_score,
                technical_weight=self.settings.screener.technical_weight,
                options_weight=self.settings.screener.options_weight,
                require_options=self.settings.screener.require_options,
                require_signal=self.settings.screener.require_signal,
                cache_ttl_seconds=self.settings.screener.cache_ttl_seconds,
            )

            # Build screening criteria from settings
            criteria = ScreeningCriteria(
                min_price=self.settings.screener.criteria.min_price,
                max_price=self.settings.screener.criteria.max_price,
                min_volume=self.settings.screener.criteria.min_volume,
                min_dollar_volume=self.settings.screener.criteria.min_dollar_volume,
                rsi_oversold=self.settings.screener.criteria.rsi_oversold,
                rsi_overbought=self.settings.screener.criteria.rsi_overbought,
                rsi_period=self.settings.screener.criteria.rsi_period,
                min_option_volume=self.settings.screener.criteria.min_option_volume,
                min_open_interest=self.settings.screener.criteria.min_open_interest,
                max_bid_ask_spread_percent=self.settings.screener.criteria.max_bid_ask_spread_percent,
                min_expirations=self.settings.screener.criteria.min_expirations,
            )

            # Build integration config
            integration_config = IntegrationConfig(
                scan_interval_seconds=self.settings.screener.auto_refresh_seconds,
                min_score_for_trading=self.settings.screener.min_combined_score,
                min_score_for_backtest=self.settings.screener.min_combined_score * 0.8,
                route_to_trading=True,
                route_to_backtest=True,
            )

            # Create screener integration
            self._screener_integration = await create_integration_from_clients(
                trading_client=self.alpaca_client.trading,
                stock_data_client=self.alpaca_client.stock_data,
                options_data_client=self.alpaca_client.option_data,
                scanner_config=scanner_config,
                integration_config=integration_config,
                criteria=criteria,
            )

            # Set callback for trading opportunities
            self._screener_integration.set_trading_callback(
                self._on_screener_opportunity
            )

            # Start the integration
            await self._screener_integration.start()

            # Start opportunity processing task
            self._screener_opportunity_task = asyncio.create_task(
                self._process_screener_opportunities()
            )

            logger.info("Screener integration started successfully")

            await self.event_bus.publish(
                Event(
                    event_type=EventType.SCREENER_UPDATE,
                    data={
                        "message": "Screener integration started",
                        "mode": self.settings.screener.mode,
                        "universe": self.settings.screener.universe,
                    },
                    source="TradingEngine",
                )
            )

        except Exception as e:
            logger.error(f"Failed to start screener integration: {e}")
            await self.event_bus.publish(
                Event(
                    event_type=EventType.ERROR,
                    data={"error": str(e), "location": "screener_integration"},
                    source="TradingEngine",
                )
            )

    def _on_screener_opportunity(self, opportunity) -> None:
        """Callback when screener finds a trading opportunity.

        This adds the symbol to the set of screener-discovered symbols
        so strategies can trade on them.
        """
        symbol = opportunity.symbol
        self._screener_symbols.add(symbol)

        logger.info(
            f"Screener opportunity: {symbol} ({opportunity.opportunity_type.value}) "
            f"Score: {opportunity.score:.1f}, Priority: {opportunity.priority.name}"
        )

    async def _process_screener_opportunities(self) -> None:
        """Process opportunities from the screener and feed to strategies."""
        while self._running:
            try:
                if not self._screener_integration:
                    await asyncio.sleep(5)
                    continue

                # Get next trading opportunity
                opportunity = await self._screener_integration.get_trading_opportunity(
                    timeout=2.0
                )

                if opportunity is None:
                    continue

                if opportunity.is_expired:
                    logger.debug(f"Skipping expired opportunity: {opportunity.symbol}")
                    continue

                # Add symbol to screener symbols
                self._screener_symbols.add(opportunity.symbol)

                # Publish opportunity event
                await self.event_bus.publish(
                    Event(
                        event_type=EventType.SCREENER_OPPORTUNITY,
                        data={
                            "message": "Screener opportunity",
                            "symbol": opportunity.symbol,
                            "type": opportunity.opportunity_type.value,
                            "score": opportunity.score,
                            "priority": opportunity.priority.name,
                            "rsi": opportunity.screener_result.rsi,
                            "signal": opportunity.screener_result.signal,
                        },
                        source="ScreenerIntegration",
                    )
                )

                # Process the opportunity through active strategies
                await self._process_screener_symbol(opportunity.symbol)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing screener opportunity: {e}")
                await asyncio.sleep(5)

    async def _process_screener_symbol(self, symbol: str) -> None:
        """Process a screener-discovered symbol through active strategies.

        Args:
            symbol: The symbol discovered by the screener.
        """
        for name, strategy in self._active_strategies.items():
            try:
                # Get option chain for the symbol
                chain = await self.data_manager.get_option_chain(
                    symbol,
                    min_dte=self.settings.risk.min_days_to_expiry,
                    max_dte=self.settings.risk.max_days_to_expiry,
                )

                if chain:
                    # Let strategy process the chain
                    signal = await strategy.on_option_chain(chain)

                    if signal and strategy.validate_signal(signal):
                        # Add metadata about screener source
                        signal.metadata["source"] = "screener"
                        signal.metadata["screener_symbol"] = symbol
                        await self.submit_signal(signal)

            except Exception as e:
                logger.error(
                    f"Error processing screener symbol {symbol} with {name}: {e}"
                )

    def get_screener_symbols(self) -> list[str]:
        """Get list of symbols discovered by the screener.

        Returns:
            List of symbols currently in the screener queue.
        """
        return list(self._screener_symbols)

    async def run_screener_scan(self) -> list:
        """Run an immediate screener scan.

        Returns:
            List of discovered opportunities.
        """
        if not self._screener_integration:
            logger.warning("Screener integration not enabled")
            return []

        return await self._screener_integration.run_immediate_scan()

    def get_screener_stats(self) -> dict:
        """Get screener integration statistics.

        Returns:
            Statistics dictionary or empty dict if not enabled.
        """
        if not self._screener_integration:
            return {}

        return self._screener_integration.get_stats()
