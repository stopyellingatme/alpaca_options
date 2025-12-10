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
    OptionLegRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import (
    OrderClass,
    OrderSide,
    OrderStatus,
    OrderType,
    QueryOrderStatus,
    TimeInForce,
)

from alpaca_options.strategies.base import OptionLeg, OptionSignal

logger = logging.getLogger(__name__)


class OrderRejectionError(Exception):
    """Exception raised when an order is rejected by the broker.

    Attributes:
        message: Explanation of the rejection
        error_code: Alpaca error code (if available)
        order_details: Details about the rejected order
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        order_details: Optional[dict] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.order_details = order_details or {}
        super().__init__(self.message)

    def __str__(self):
        parts = [f"Order Rejected: {self.message}"]
        if self.error_code:
            parts.append(f"Error Code: {self.error_code}")
        if self.order_details:
            parts.append(f"Details: {self.order_details}")
        return " | ".join(parts)


class InsufficientFundsError(OrderRejectionError):
    """Exception for insufficient funds/buying power."""

    def __init__(self, message: str, required: Optional[float] = None, available: Optional[float] = None):
        order_details = {}
        if required is not None:
            order_details["required"] = required
        if available is not None:
            order_details["available"] = available
        super().__init__(message, error_code="INSUFFICIENT_FUNDS", order_details=order_details)


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

    def _parse_api_error(self, error: Exception) -> tuple[str, Optional[str], dict]:
        """Parse API error to extract useful information.

        Args:
            error: The exception raised by Alpaca API.

        Returns:
            Tuple of (error_message, error_code, additional_details).
        """
        error_msg = str(error)
        error_code = None
        details = {}

        # Try to extract error code from common Alpaca error formats
        if "insufficient" in error_msg.lower() and "buying power" in error_msg.lower():
            error_code = "INSUFFICIENT_BUYING_POWER"
        elif "insufficient" in error_msg.lower() and "fund" in error_msg.lower():
            error_code = "INSUFFICIENT_FUNDS"
        elif "forbidden" in error_msg.lower():
            error_code = "FORBIDDEN"
        elif "not found" in error_msg.lower():
            error_code = "NOT_FOUND"
        elif "invalid" in error_msg.lower():
            error_code = "INVALID_REQUEST"
        elif "rate limit" in error_msg.lower():
            error_code = "RATE_LIMIT"
        elif "market closed" in error_msg.lower():
            error_code = "MARKET_CLOSED"
        elif "symbol" in error_msg.lower() and "not tradable" in error_msg.lower():
            error_code = "SYMBOL_NOT_TRADABLE"

        # Extract additional details from the error message
        if hasattr(error, 'status_code'):
            details['status_code'] = error.status_code
        if hasattr(error, 'response'):
            details['response'] = str(error.response)

        return error_msg, error_code, details

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
            error_msg, error_code, details = self._parse_api_error(e)
            logger.error(f"Failed to submit market order for {symbol}: {error_msg}")

            if error_code in ("INSUFFICIENT_BUYING_POWER", "INSUFFICIENT_FUNDS"):
                raise InsufficientFundsError(f"Insufficient funds: {error_msg}") from e
            else:
                raise OrderRejectionError(error_msg, error_code, details) from e

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
            error_msg, error_code, details = self._parse_api_error(e)
            logger.error(f"Failed to submit limit order for {symbol}: {error_msg}")

            if error_code in ("INSUFFICIENT_BUYING_POWER", "INSUFFICIENT_FUNDS"):
                raise InsufficientFundsError(f"Insufficient funds: {error_msg}") from e
            else:
                raise OrderRejectionError(error_msg, error_code, details) from e

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
            error_msg, error_code, details = self._parse_api_error(e)
            logger.error(f"Failed to submit stop order for {symbol}: {error_msg}")

            if error_code in ("INSUFFICIENT_BUYING_POWER", "INSUFFICIENT_FUNDS"):
                raise InsufficientFundsError(f"Insufficient funds: {error_msg}") from e
            else:
                raise OrderRejectionError(error_msg, error_code, details) from e

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
            error_msg, error_code, details = self._parse_api_error(e)
            logger.error(f"Failed to submit stop-limit order for {symbol}: {error_msg}")

            if error_code in ("INSUFFICIENT_BUYING_POWER", "INSUFFICIENT_FUNDS"):
                raise InsufficientFundsError(f"Insufficient funds: {error_msg}") from e
            else:
                raise OrderRejectionError(error_msg, error_code, details) from e

    async def submit_multi_leg_order(
        self,
        signal: OptionSignal,
        order_type: str = "market",
        net_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit a multi-leg options order (spread) atomically.

        This is the CORRECT way to submit spreads - all legs execute together
        as a single atomic order with a net credit/debit price.

        Args:
            signal: The option signal with multiple legs.
            order_type: "market" or "limit".
            net_price: Net credit (positive) or debit (negative) for limit orders.
                      For credit spreads, this is the premium received.
                      For debit spreads, this is the premium paid.
            time_in_force: Order duration ("day" is the only valid option for options).

        Returns:
            OrderResult with order details.

        Raises:
            ValueError: If invalid parameters provided.
            Exception: If order submission fails.

        Note:
            - All legs are executed together atomically
            - No partial fills - either all legs fill or none do
            - For limit orders, net_price sets the total credit/debit for the spread
            - TimeInForce.DAY is the only supported TIF for options orders
        """
        if not signal.legs:
            raise ValueError("Signal must have at least one leg")

        # Validate time_in_force (only DAY is supported for options)
        if time_in_force.lower() != "day":
            logger.warning(
                f"Time in force '{time_in_force}' may not be supported for options. "
                "Using 'day' instead."
            )
            time_in_force = "day"

        tif = self._parse_time_in_force(time_in_force)

        # Build legs using OptionLegRequest
        option_legs = []
        for leg in signal.legs:
            order_side = OrderSide.BUY if leg.side.lower() == "buy" else OrderSide.SELL
            option_legs.append(
                OptionLegRequest(
                    symbol=leg.contract_symbol,
                    side=order_side,
                    ratio_qty=leg.quantity,
                )
            )

        # Submit as MLEG order
        try:
            if order_type.lower() == "market":
                request = MarketOrderRequest(
                    qty=1,  # Number of spreads (usually 1)
                    order_class=OrderClass.MLEG,
                    time_in_force=tif,
                    legs=option_legs,
                )
                logger.info(
                    f"Submitting multi-leg MARKET order: {signal.strategy_name} "
                    f"on {signal.underlying} with {len(option_legs)} legs"
                )
            else:
                # Limit order with net price
                if net_price is None:
                    raise ValueError(
                        "net_price required for limit orders. "
                        "For credit spreads, use positive value (premium received). "
                        "For debit spreads, use positive value (premium paid)."
                    )

                request = LimitOrderRequest(
                    qty=1,
                    order_class=OrderClass.MLEG,
                    time_in_force=tif,
                    limit_price=abs(net_price),  # Alpaca expects positive value
                    legs=option_legs,
                )
                logger.info(
                    f"Submitting multi-leg LIMIT order: {signal.strategy_name} "
                    f"on {signal.underlying} with {len(option_legs)} legs @ net ${net_price:.2f}"
                )

            order = self._client.submit_order(request)
            result = self._create_order_result(order)
            self._pending_orders[result.order_id] = result

            logger.info(
                f"Multi-leg order submitted successfully: {result.order_id} "
                f"({signal.signal_type.value})"
            )
            return result

        except Exception as e:
            # Parse the error to provide better feedback
            error_msg, error_code, details = self._parse_api_error(e)

            logger.error(
                f"Failed to submit multi-leg order for {signal.strategy_name}: "
                f"{error_msg} (code: {error_code})"
            )

            # Provide specific exceptions for common error types
            if error_code in ("INSUFFICIENT_BUYING_POWER", "INSUFFICIENT_FUNDS"):
                raise InsufficientFundsError(
                    f"Insufficient funds to place {signal.strategy_name} order: {error_msg}"
                ) from e
            elif error_code == "MARKET_CLOSED":
                raise OrderRejectionError(
                    f"Cannot place order while market is closed: {error_msg}",
                    error_code=error_code,
                ) from e
            elif error_code == "SYMBOL_NOT_TRADABLE":
                symbols = [leg.contract_symbol for leg in signal.legs]
                raise OrderRejectionError(
                    f"One or more option contracts not tradable: {symbols}",
                    error_code=error_code,
                    order_details={"symbols": symbols},
                ) from e
            else:
                # Generic order rejection error
                raise OrderRejectionError(
                    error_msg,
                    error_code=error_code,
                    order_details=details,
                ) from e

    async def submit_option_order(
        self,
        leg: OptionLeg,
        order_type: str = "limit",
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit an order for a single option leg.

        WARNING: For spreads (multiple legs), use submit_multi_leg_order() instead.
        This method should only be used for single-leg strategies like buying a call/put.

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
        order_type: str = "market",
        net_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> OrderResult:
        """Submit orders for an option signal.

        For multi-leg strategies (spreads), this uses atomic multi-leg orders.
        For single-leg strategies, this submits a single option order.

        Args:
            signal: The option signal with legs to execute.
            order_type: "market" or "limit".
            net_price: For multi-leg limit orders, the net credit/debit price.
                      For credit spreads, use positive value (premium received).
                      For debit spreads, use positive value (premium paid).
            time_in_force: Order duration (only "day" is supported for options).

        Returns:
            OrderResult with order details.

        Raises:
            ValueError: If invalid parameters provided.
            Exception: If order submission fails.

        Note:
            Multi-leg orders are submitted atomically - all legs execute together
            or none execute. This prevents adverse fills and naked positions.
        """
        if len(signal.legs) > 1:
            # Multi-leg strategy - use atomic MLEG order
            logger.info(
                f"Submitting multi-leg signal: {signal.strategy_name} "
                f"({signal.signal_type.value}) with {len(signal.legs)} legs"
            )
            return await self.submit_multi_leg_order(
                signal=signal,
                order_type=order_type,
                net_price=net_price,
                time_in_force=time_in_force,
            )
        elif len(signal.legs) == 1:
            # Single-leg strategy - submit single option order
            logger.info(
                f"Submitting single-leg signal: {signal.strategy_name} "
                f"({signal.signal_type.value})"
            )
            return await self.submit_option_order(
                leg=signal.legs[0],
                order_type=order_type,
                time_in_force=time_in_force,
            )
        else:
            raise ValueError("Signal must have at least one leg")

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

    def check_multi_leg_order_status(self, order_id: str) -> dict:
        """Check the status of a multi-leg order and its individual legs.

        This is useful for monitoring multi-leg orders, though they should
        execute atomically (all legs fill together or none fill).

        Args:
            order_id: The order ID to check.

        Returns:
            Dictionary with order status and leg details.

        Example:
            {
                "order_id": "abc123",
                "status": "filled",
                "order_class": "mleg",
                "legs": [
                    {"symbol": "SPY240315P00500000", "side": "sell", "status": "filled"},
                    {"symbol": "SPY240315P00495000", "side": "buy", "status": "filled"}
                ],
                "is_atomic": True,  # All legs have same status
                "filled_qty": 1,
                "message": "All legs filled successfully"
            }
        """
        try:
            order = self._client.get_order_by_id(order_id)

            # Check if this is a multi-leg order
            is_mleg = hasattr(order, 'order_class') and order.order_class == OrderClass.MLEG

            result = {
                "order_id": str(order.id),
                "status": order.status.value if order.status else "unknown",
                "order_class": order.order_class.value if hasattr(order, 'order_class') and order.order_class else "simple",
                "legs": [],
                "is_atomic": True,
                "filled_qty": int(order.filled_qty) if order.filled_qty else 0,
            }

            # Check individual legs if this is a multi-leg order
            if is_mleg and hasattr(order, 'legs') and order.legs:
                leg_statuses = set()
                for leg in order.legs:
                    leg_info = {
                        "symbol": leg.symbol,
                        "side": leg.side.value if leg.side else "unknown",
                        "status": leg.status.value if leg.status else "unknown",
                        "filled_qty": int(leg.filled_qty) if leg.filled_qty else 0,
                    }
                    result["legs"].append(leg_info)
                    leg_statuses.add(leg_info["status"])

                # Check if all legs have the same status (atomic)
                result["is_atomic"] = len(leg_statuses) == 1

                if not result["is_atomic"]:
                    result["message"] = (
                        "WARNING: Legs have different statuses! "
                        "This should not happen with MLEG orders. "
                        f"Statuses: {leg_statuses}"
                    )
                    logger.error(
                        f"Multi-leg order {order_id} has non-atomic status: {leg_statuses}"
                    )
                elif result["status"] == "filled":
                    result["message"] = "All legs filled successfully"
                elif result["status"] == "rejected":
                    result["message"] = "Order rejected (all legs)"
                elif result["status"] == "canceled":
                    result["message"] = "Order canceled (all legs)"
                else:
                    result["message"] = f"Order {result['status']}"
            else:
                result["message"] = f"Order {result['status']}"

            return result

        except Exception as e:
            logger.error(f"Failed to check multi-leg order status for {order_id}: {e}")
            return {
                "order_id": order_id,
                "status": "error",
                "message": str(e),
                "legs": [],
                "is_atomic": False,
            }

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
