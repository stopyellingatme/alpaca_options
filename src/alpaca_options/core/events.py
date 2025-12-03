"""Event bus for decoupled component communication."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events in the trading system."""

    # Market data events
    MARKET_DATA_UPDATE = auto()
    OPTION_CHAIN_UPDATE = auto()
    QUOTE_UPDATE = auto()
    TRADE_UPDATE = auto()

    # Strategy events
    SIGNAL_GENERATED = auto()
    STRATEGY_STARTED = auto()
    STRATEGY_STOPPED = auto()
    STRATEGY_ERROR = auto()

    # Order events
    ORDER_SUBMITTED = auto()
    ORDER_FILLED = auto()
    ORDER_PARTIALLY_FILLED = auto()
    ORDER_CANCELLED = auto()
    ORDER_REJECTED = auto()
    ORDER_EXPIRED = auto()

    # Position events
    POSITION_OPENED = auto()
    POSITION_CLOSED = auto()
    POSITION_UPDATED = auto()
    POSITION_ASSIGNED = auto()  # Options assignment

    # Risk events
    RISK_LIMIT_WARNING = auto()
    RISK_LIMIT_BREACH = auto()
    MARGIN_CALL = auto()
    STOP_LOSS_TRIGGERED = auto()
    TAKE_PROFIT_TRIGGERED = auto()

    # System events
    ENGINE_STARTED = auto()
    ENGINE_STOPPED = auto()
    CONNECTION_ESTABLISHED = auto()
    CONNECTION_LOST = auto()
    ERROR = auto()

    # Account events
    ACCOUNT_UPDATE = auto()
    BUYING_POWER_UPDATE = auto()

    # Screener events
    SCREENER_UPDATE = auto()
    SCREENER_OPPORTUNITY = auto()


@dataclass
class Event:
    """Event object passed through the event bus."""

    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.correlation_id is None:
            self.correlation_id = f"{self.event_type.name}_{self.timestamp.timestamp()}"


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Asynchronous event bus for pub/sub communication.

    Allows components to subscribe to specific event types and
    publish events without direct coupling.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._all_handlers: list[EventHandler] = []
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._process_task: Optional[asyncio.Task[None]] = None
        self._event_history: list[Event] = []
        self._max_history_size = 1000

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """Subscribe a handler to a specific event type.

        Args:
            event_type: Type of event to subscribe to.
            handler: Async function to call when event occurs.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.name}")

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe a handler to all events.

        Args:
            handler: Async function to call for any event.
        """
        self._all_handlers.append(handler)
        logger.debug("Handler subscribed to all events")

    def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: Type of event to unsubscribe from.
            handler: Handler function to remove.
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(f"Handler unsubscribed from {event_type.name}")
            except ValueError:
                pass

    def unsubscribe_all(self, handler: EventHandler) -> None:
        """Unsubscribe a handler from all events.

        Args:
            handler: Handler function to remove.
        """
        try:
            self._all_handlers.remove(handler)
        except ValueError:
            pass

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus.

        Args:
            event: Event to publish.
        """
        await self._event_queue.put(event)
        logger.debug(f"Event published: {event.event_type.name}")

    def publish_sync(self, event: Event) -> None:
        """Synchronously add an event to the queue.

        Useful for non-async contexts.

        Args:
            event: Event to publish.
        """
        self._event_queue.put_nowait(event)

    async def start(self) -> None:
        """Start the event processing loop."""
        if self._running:
            return

        self._running = True
        self._process_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop the event processing loop."""
        self._running = False

        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        logger.info("Event bus stopped")

    async def _process_events(self) -> None:
        """Main event processing loop."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1,
                )
            except asyncio.TimeoutError:
                continue

            # Store in history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history_size:
                self._event_history = self._event_history[-self._max_history_size:]

            # Dispatch to specific handlers
            handlers = self._handlers.get(event.event_type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(
                        f"Error in event handler for {event.event_type.name}: {e}"
                    )

            # Dispatch to all-event handlers
            for handler in self._all_handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Error in all-event handler: {e}")

            self._event_queue.task_done()

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get recent event history.

        Args:
            event_type: Filter by event type. None for all events.
            limit: Maximum number of events to return.

        Returns:
            List of recent events, newest first.
        """
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return list(reversed(events[-limit:]))

    def clear_history(self) -> None:
        """Clear the event history."""
        self._event_history.clear()

    @property
    def queue_size(self) -> int:
        """Get current size of the event queue."""
        return self._event_queue.qsize()


# Global event bus instance
_default_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the default event bus instance.

    Returns:
        The global EventBus instance.
    """
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus
