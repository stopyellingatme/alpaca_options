"""Trading operations for order execution and position management."""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    QueryOrderStatus,
    TimeInForce,
)

from alpaca_options.strategies.base import OptionLeg, OptionSignal

logger = logging.getLogger(__name__)


class OrderState(Enum):
    """Order state enumeration."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class OrderResult:
    """Result of an order submission."""

    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    status: OrderState
    filled_qty: int
    filled_avg_price: Optional[float]
    submitted_at: datetime
    message: str = ""


@dataclass
class Position:
    """Represents a trading position."""

    symbol: str
    quantity: int
    side: str  # "long" or "short"
    entry_price: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    asset_class: str  # "us_equity" or "us_option"


class TradingManager:
    """Manages order execution and position tracking.

    Handles:
    - Order submission (market, limit, stop)
    - Order status tracking
    - Position management
    - Options-specific order handling
    """

    def __init__(self, trading_client: TradingClient) -> None:
        self._client = trading_client
        self._pending_orders: dict[str, OrderResult] = {}

    def _map_order_status(self, status: OrderStatus) -> OrderState:
        """Map Alpaca order status to our OrderState."""
        mapping = {
            OrderStatus.NEW: OrderState.SUBMITTED,
            OrderStatus.ACCEPTED: OrderState.SUBMITTED,
            OrderStatus.PENDING_NEW: OrderState.PENDING,
            OrderStatus.ACCEPTED_FOR_BIDDING: OrderState.SUBMITTED,
            OrderStatus.FILLED: OrderState.FILLED,
            OrderStatus.PARTIALLY_FILLED: OrderState.PARTIALLY_FILLED,
            OrderStatus.CANCELED: OrderState.CANCELLED,
            OrderStatus.EXPIRED: OrderState.EXPIRED,
            OrderStatus.REJECTED: OrderState.REJECTED,
            OrderStatus.PENDING_CANCEL: OrderState.SUBMITTED,
            OrderStatus.PENDING_REPLACE: OrderState.SUBMITTED,
            OrderStatus.STOPPED: OrderState.SUBMITTED,
            OrderStatus.SUSPENDED: OrderState.SUBMITTED,
            OrderStatus.CALCULATED: OrderState.SUBMITTED,
            OrderStatus.HELD: OrderState.PENDING,
            OrderStatus.DONE_FOR_DAY: OrderState.FILLED,
            OrderStatus.REPLACED: OrderState.SUBMITTED,
        }
        return mapping.get(status, OrderState.PENDING)

    async def submit_market_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit a market order.

        Args:
            symbol: The symbol to trade (stock or option contract).
            quantity: Number of shares/contracts.
            side: "buy" or "sell".
            time_in_force: Order duration ("day", "gtc", "ioc", "fok").

        Returns:
            OrderResult with order details.
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = self._parse_time_in_force(time_in_force)

        request = MarketOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            time_in_force=tif,
        )

        try:
            order = self._client.submit_order(request)
            result = self._create_order_result(order)
            self._pending_orders[result.order_id] = result
            logger.info(f"Market order submitted: {result.order_id} {side} {quantity} {symbol}")
            return result
        except Exception as e:
            logger.error(f"Failed to submit market order: {e}")
            raise

    async def submit_limit_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        limit_price: float,
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit a limit order.

        Args:
            symbol: The symbol to trade.
            quantity: Number of shares/contracts.
            side: "buy" or "sell".
            limit_price: Limit price for the order.
            time_in_force: Order duration.

        Returns:
            OrderResult with order details.
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = self._parse_time_in_force(time_in_force)

        request = LimitOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            time_in_force=tif,
            limit_price=limit_price,
        )

        try:
            order = self._client.submit_order(request)
            result = self._create_order_result(order)
            self._pending_orders[result.order_id] = result
            logger.info(
                f"Limit order submitted: {result.order_id} {side} {quantity} {symbol} @ ${limit_price}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to submit limit order: {e}")
            raise

    async def submit_stop_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        stop_price: float,
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit a stop order.

        Args:
            symbol: The symbol to trade.
            quantity: Number of shares/contracts.
            side: "buy" or "sell".
            stop_price: Stop trigger price.
            time_in_force: Order duration.

        Returns:
            OrderResult with order details.
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = self._parse_time_in_force(time_in_force)

        request = StopOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            time_in_force=tif,
            stop_price=stop_price,
        )

        try:
            order = self._client.submit_order(request)
            result = self._create_order_result(order)
            self._pending_orders[result.order_id] = result
            logger.info(
                f"Stop order submitted: {result.order_id} {side} {quantity} {symbol} stop @ ${stop_price}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to submit stop order: {e}")
            raise

    async def submit_stop_limit_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        stop_price: float,
        limit_price: float,
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit a stop-limit order.

        Args:
            symbol: The symbol to trade.
            quantity: Number of shares/contracts.
            side: "buy" or "sell".
            stop_price: Stop trigger price.
            limit_price: Limit price after stop triggers.
            time_in_force: Order duration.

        Returns:
            OrderResult with order details.
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = self._parse_time_in_force(time_in_force)

        request = StopLimitOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            time_in_force=tif,
            stop_price=stop_price,
            limit_price=limit_price,
        )

        try:
            order = self._client.submit_order(request)
            result = self._create_order_result(order)
            self._pending_orders[result.order_id] = result
            logger.info(
                f"Stop-limit order submitted: {result.order_id} {side} {quantity} {symbol}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to submit stop-limit order: {e}")
            raise

    async def submit_option_order(
        self,
        leg: OptionLeg,
        order_type: str = "limit",
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit an order for a single option leg.

        Args:
            leg: The option leg to trade.
            order_type: "market" or "limit".
            time_in_force: Order duration.

        Returns:
            OrderResult with order details.
        """
        if order_type == "market":
            return await self.submit_market_order(
                symbol=leg.contract_symbol,
                quantity=leg.quantity,
                side=leg.side,
                time_in_force=time_in_force,
            )
        else:
            if leg.limit_price is None:
                raise ValueError("Limit price required for limit orders")
            return await self.submit_limit_order(
                symbol=leg.contract_symbol,
                quantity=leg.quantity,
                side=leg.side,
                limit_price=leg.limit_price,
                time_in_force=time_in_force,
            )

    async def submit_signal(
        self,
        signal: OptionSignal,
        order_type: str = "limit",
        time_in_force: str = "day",
    ) -> list[OrderResult]:
        """Submit orders for all legs in an option signal.

        Args:
            signal: The option signal with legs to execute.
            order_type: "market" or "limit".
            time_in_force: Order duration.

        Returns:
            List of OrderResults for each leg.
        """
        results = []
        for leg in signal.legs:
            try:
                result = await self.submit_option_order(
                    leg=leg,
                    order_type=order_type,
                    time_in_force=time_in_force,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to submit leg {leg.contract_symbol}: {e}")
                # Cancel previously submitted orders on failure
                for prev_result in results:
                    try:
                        await self.cancel_order(prev_result.order_id)
                    except Exception:
                        pass
                raise

        return results

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: The order ID to cancel.

        Returns:
            True if cancellation was successful.
        """
        try:
            self._client.cancel_order_by_id(order_id)
            if order_id in self._pending_orders:
                self._pending_orders[order_id].status = OrderState.CANCELLED
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders.

        Returns:
            Number of orders cancelled.
        """
        try:
            cancelled = self._client.cancel_orders()
            count = len(cancelled) if cancelled else 0
            logger.info(f"Cancelled {count} orders")
            return count
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0

    def get_order(self, order_id: str) -> Optional[OrderResult]:
        """Get the current status of an order.

        Args:
            order_id: The order ID to look up.

        Returns:
            OrderResult with current order status.
        """
        try:
            order = self._client.get_order_by_id(order_id)
            return self._create_order_result(order)
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> list[OrderResult]:
        """Get all open orders.

        Args:
            symbol: Optional symbol filter.

        Returns:
            List of open OrderResults.
        """
        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[symbol] if symbol else None,
        )

        try:
            orders = self._client.get_orders(request)
            return [self._create_order_result(o) for o in orders]
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def get_positions(self) -> list[Position]:
        """Get all current positions.

        Returns:
            List of Position objects.
        """
        try:
            positions = self._client.get_all_positions()
            return [self._create_position(p) for p in positions]
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.

        Args:
            symbol: The symbol to look up.

        Returns:
            Position if exists, None otherwise.
        """
        try:
            pos = self._client.get_open_position(symbol)
            return self._create_position(pos)
        except Exception:
            return None

    async def close_position(
        self,
        symbol: str,
        quantity: Optional[int] = None,
    ) -> Optional[OrderResult]:
        """Close a position.

        Args:
            symbol: The symbol to close.
            quantity: Optional partial quantity to close.

        Returns:
            OrderResult if order submitted, None on failure.
        """
        try:
            if quantity:
                order = self._client.close_position(symbol, qty=str(quantity))
            else:
                order = self._client.close_position(symbol)
            return self._create_order_result(order)
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return None

    async def close_all_positions(self) -> list[OrderResult]:
        """Close all positions.

        Returns:
            List of OrderResults for close orders.
        """
        try:
            orders = self._client.close_all_positions(cancel_orders=True)
            return [self._create_order_result(o) for o in orders if o]
        except Exception as e:
            logger.error(f"Failed to close all positions: {e}")
            return []

    def _parse_time_in_force(self, tif: str) -> TimeInForce:
        """Parse time in force string to enum."""
        mapping = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
            "opg": TimeInForce.OPG,
            "cls": TimeInForce.CLS,
        }
        return mapping.get(tif.lower(), TimeInForce.DAY)

    def _create_order_result(self, order) -> OrderResult:
        """Create OrderResult from Alpaca order object."""
        return OrderResult(
            order_id=str(order.id),
            client_order_id=order.client_order_id or "",
            symbol=order.symbol,
            side=order.side.value if order.side else "unknown",
            quantity=int(order.qty) if order.qty else 0,
            order_type=order.order_type.value if order.order_type else "unknown",
            status=self._map_order_status(order.status),
            filled_qty=int(order.filled_qty) if order.filled_qty else 0,
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            submitted_at=order.submitted_at or datetime.now(),
        )

    def _create_position(self, pos) -> Position:
        """Create Position from Alpaca position object."""
        qty = int(pos.qty)
        return Position(
            symbol=pos.symbol,
            quantity=abs(qty),
            side="long" if qty > 0 else "short",
            entry_price=float(pos.avg_entry_price),
            current_price=float(pos.current_price),
            market_value=float(pos.market_value),
            cost_basis=float(pos.cost_basis),
            unrealized_pnl=float(pos.unrealized_pl),
            unrealized_pnl_percent=float(pos.unrealized_plpc) * 100,
            asset_class=pos.asset_class.value if pos.asset_class else "unknown",
        )
