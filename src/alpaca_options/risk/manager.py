"""Risk management module for portfolio and position risk control.

This module provides comprehensive risk management including:
- Portfolio-level Greeks limits (delta, gamma, theta, vega)
- Position sizing based on account equity
- Drawdown protection
- Per-trade risk limits
- Liquidity checks
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from alpaca_options.core.config import RiskConfig
from alpaca_options.strategies.base import OptionContract, OptionLeg, OptionSignal

logger = logging.getLogger(__name__)


class RiskCheckResult(Enum):
    """Result of a risk check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class RiskViolation:
    """Details of a risk rule violation."""

    rule: str
    message: str
    current_value: float
    limit_value: float
    severity: str = "error"  # "error", "warning"


@dataclass
class RiskCheckResponse:
    """Response from a risk check."""

    result: RiskCheckResult
    violations: list[RiskViolation] = field(default_factory=list)
    warnings: list[RiskViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Check if risk check passed."""
        return self.result == RiskCheckResult.PASSED

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0


@dataclass
class PortfolioGreeks:
    """Aggregated Greeks for the portfolio."""

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0

    def __add__(self, other: "PortfolioGreeks") -> "PortfolioGreeks":
        return PortfolioGreeks(
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            theta=self.theta + other.theta,
            vega=self.vega + other.vega,
            rho=self.rho + other.rho,
        )

    def __sub__(self, other: "PortfolioGreeks") -> "PortfolioGreeks":
        return PortfolioGreeks(
            delta=self.delta - other.delta,
            gamma=self.gamma - other.gamma,
            theta=self.theta - other.theta,
            vega=self.vega - other.vega,
            rho=self.rho - other.rho,
        )


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""

    symbol: str
    quantity: int
    side: str  # "long" or "short"
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    greeks: PortfolioGreeks
    days_to_expiry: Optional[int] = None
    underlying: Optional[str] = None


@dataclass
class PortfolioRisk:
    """Risk metrics for the entire portfolio."""

    total_equity: float
    buying_power: float
    positions: list[PositionRisk]
    greeks: PortfolioGreeks
    total_unrealized_pnl: float
    daily_pnl: float
    drawdown_percent: float
    position_count: int

    @property
    def utilization(self) -> float:
        """Calculate buying power utilization percentage."""
        if self.total_equity <= 0:
            return 0.0
        used = self.total_equity - self.buying_power
        return (used / self.total_equity) * 100


class RiskManager:
    """Manages risk for the trading portfolio.

    Provides:
    - Pre-trade risk checks
    - Portfolio-level risk monitoring
    - Position sizing calculations
    - Greeks aggregation and limits
    - Drawdown protection
    """

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

        # Track portfolio state
        self._portfolio_greeks = PortfolioGreeks()
        self._position_risks: dict[str, PositionRisk] = {}
        self._daily_pnl: float = 0.0
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._buying_power: float = 0.0

        # Track daily loss
        self._daily_loss: float = 0.0
        self._last_reset_date: datetime = datetime.now().date()

    def update_account(
        self,
        equity: float,
        buying_power: float,
        daily_pnl: float,
    ) -> None:
        """Update account state for risk calculations.

        Args:
            equity: Current account equity.
            buying_power: Available buying power.
            daily_pnl: Today's P&L.
        """
        self._current_equity = equity
        self._buying_power = buying_power
        self._daily_pnl = daily_pnl

        # Track peak equity for drawdown calculation
        if equity > self._peak_equity:
            self._peak_equity = equity

        # Reset daily tracking at market open
        today = datetime.now().date()
        if today != self._last_reset_date:
            self._daily_loss = 0.0
            self._last_reset_date = today

        # Track daily loss
        if daily_pnl < 0:
            self._daily_loss = abs(daily_pnl)

    def update_position_greeks(
        self,
        symbol: str,
        delta: float,
        gamma: float,
        theta: float,
        vega: float,
        quantity: int,
        side: str,
    ) -> None:
        """Update Greeks for a specific position.

        Args:
            symbol: Position symbol.
            delta: Per-contract delta.
            gamma: Per-contract gamma.
            theta: Per-contract theta.
            vega: Per-contract vega.
            quantity: Number of contracts.
            side: "long" or "short".
        """
        # Multiply by quantity and adjust for position side
        multiplier = quantity if side == "long" else -quantity

        greeks = PortfolioGreeks(
            delta=delta * multiplier * 100,  # Options represent 100 shares
            gamma=gamma * multiplier * 100,
            theta=theta * multiplier * 100,
            vega=vega * multiplier * 100,
        )

        # Update position risk entry
        if symbol in self._position_risks:
            old_greeks = self._position_risks[symbol].greeks
            self._portfolio_greeks = self._portfolio_greeks - old_greeks + greeks
            self._position_risks[symbol].greeks = greeks
        else:
            self._portfolio_greeks = self._portfolio_greeks + greeks
            self._position_risks[symbol] = PositionRisk(
                symbol=symbol,
                quantity=quantity,
                side=side,
                market_value=0.0,
                cost_basis=0.0,
                unrealized_pnl=0.0,
                greeks=greeks,
            )

    def remove_position(self, symbol: str) -> None:
        """Remove a position from risk tracking.

        Args:
            symbol: Position symbol to remove.
        """
        if symbol in self._position_risks:
            old_greeks = self._position_risks[symbol].greeks
            self._portfolio_greeks = self._portfolio_greeks - old_greeks
            del self._position_risks[symbol]

    def check_signal_risk(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> RiskCheckResponse:
        """Perform pre-trade risk checks on a signal.

        Args:
            signal: The trading signal to check.
            contracts: Map of contract symbols to OptionContract data.

        Returns:
            RiskCheckResponse with result and any violations.
        """
        violations = []
        warnings = []

        # Check position count limit
        pos_violation = self._check_position_limit(signal)
        if pos_violation:
            violations.append(pos_violation)

        # Check portfolio Greeks limits
        greek_violations = self._check_greeks_limits(signal, contracts)
        violations.extend(greek_violations)

        # Check position sizing
        size_violation = self._check_position_sizing(signal, contracts)
        if size_violation:
            violations.append(size_violation)

        # Check daily loss limit
        loss_violation = self._check_daily_loss_limit()
        if loss_violation:
            violations.append(loss_violation)

        # Check drawdown
        drawdown_violation = self._check_drawdown_limit()
        if drawdown_violation:
            violations.append(drawdown_violation)

        # Check DTE limits
        dte_violations = self._check_dte_limits(signal, contracts)
        violations.extend(dte_violations)

        # Check liquidity (warnings only)
        liquidity_warnings = self._check_liquidity(contracts)
        warnings.extend(liquidity_warnings)

        # Determine overall result
        if violations:
            return RiskCheckResponse(
                result=RiskCheckResult.FAILED,
                violations=violations,
                warnings=warnings,
            )
        elif warnings:
            return RiskCheckResponse(
                result=RiskCheckResult.WARNING,
                violations=[],
                warnings=warnings,
            )
        else:
            return RiskCheckResponse(result=RiskCheckResult.PASSED)

    def _check_position_limit(self, signal: OptionSignal) -> Optional[RiskViolation]:
        """Check if adding this position exceeds max position count."""
        # Count existing positions (each spread counts as 1 position)
        current_positions = len(self._position_risks)

        # A multi-leg spread counts as 1 new position, not multiple
        # max_contracts_per_trade limits contracts PER LEG, not total legs
        max_contracts = self._config.max_contracts_per_trade
        for leg in signal.legs:
            if leg.quantity > max_contracts:
                return RiskViolation(
                    rule="max_contracts_per_trade",
                    message=f"Leg quantity ({leg.quantity}) exceeds max contracts per trade ({max_contracts})",
                    current_value=leg.quantity,
                    limit_value=max_contracts,
                )
        return None

    def _check_greeks_limits(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> list[RiskViolation]:
        """Check if trade would exceed portfolio Greeks limits."""
        violations = []

        # Calculate signal's Greeks contribution
        signal_greeks = PortfolioGreeks()
        for leg in signal.legs:
            contract = contracts.get(leg.contract_symbol)
            if not contract:
                continue

            multiplier = leg.quantity if leg.side == "buy" else -leg.quantity
            if contract.delta is not None:
                signal_greeks.delta += contract.delta * multiplier * 100
            if contract.gamma is not None:
                signal_greeks.gamma += contract.gamma * multiplier * 100
            if contract.theta is not None:
                signal_greeks.theta += contract.theta * multiplier * 100
            if contract.vega is not None:
                signal_greeks.vega += contract.vega * multiplier * 100

        # Check delta limit
        new_delta = self._portfolio_greeks.delta + signal_greeks.delta
        if abs(new_delta) > self._config.max_portfolio_delta:
            violations.append(
                RiskViolation(
                    rule="max_portfolio_delta",
                    message=f"Portfolio delta would exceed limit",
                    current_value=abs(new_delta),
                    limit_value=self._config.max_portfolio_delta,
                )
            )

        # Check gamma limit
        new_gamma = self._portfolio_greeks.gamma + signal_greeks.gamma
        if abs(new_gamma) > self._config.max_portfolio_gamma:
            violations.append(
                RiskViolation(
                    rule="max_portfolio_gamma",
                    message=f"Portfolio gamma would exceed limit",
                    current_value=abs(new_gamma),
                    limit_value=self._config.max_portfolio_gamma,
                )
            )

        # Check vega limit
        new_vega = self._portfolio_greeks.vega + signal_greeks.vega
        if abs(new_vega) > self._config.max_portfolio_vega:
            violations.append(
                RiskViolation(
                    rule="max_portfolio_vega",
                    message=f"Portfolio vega would exceed limit",
                    current_value=abs(new_vega),
                    limit_value=self._config.max_portfolio_vega,
                )
            )

        # Check theta limit (negative theta is a cost)
        new_theta = self._portfolio_greeks.theta + signal_greeks.theta
        if new_theta < self._config.min_portfolio_theta:
            violations.append(
                RiskViolation(
                    rule="min_portfolio_theta",
                    message=f"Portfolio theta would be too negative",
                    current_value=new_theta,
                    limit_value=self._config.min_portfolio_theta,
                )
            )

        return violations

    def _check_position_sizing(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> Optional[RiskViolation]:
        """Check if trade size is within limits."""
        if self._current_equity <= 0:
            return None

        # Calculate trade value based on strategy type
        trade_value = self._calculate_trade_risk(signal, contracts)

        # Check against max single position percent
        max_value = self._current_equity * (
            self._config.max_single_position_percent / 100
        )
        if trade_value > max_value:
            return RiskViolation(
                rule="max_single_position_percent",
                message=f"Trade value exceeds {self._config.max_single_position_percent}% of equity",
                current_value=trade_value,
                limit_value=max_value,
            )

        return None

    def _calculate_trade_risk(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> float:
        """Calculate the maximum risk for a trade.

        For spreads, this is the width of the spread minus credit received.
        For naked options, this uses a collateral estimate.
        """
        # Categorize legs
        buy_puts = []
        sell_puts = []
        buy_calls = []
        sell_calls = []

        for leg in signal.legs:
            contract = contracts.get(leg.contract_symbol)
            if not contract:
                continue
            if contract.option_type == "put":
                if leg.side == "buy":
                    buy_puts.append((leg, contract))
                else:
                    sell_puts.append((leg, contract))
            else:  # call
                if leg.side == "buy":
                    buy_calls.append((leg, contract))
                else:
                    sell_calls.append((leg, contract))

        # Check for spread strategies (defined risk)
        is_spread = (
            signal.signal_type.value in [
                "iron_condor", "iron_butterfly",
                "sell_put_spread", "sell_call_spread",
                "buy_put_spread", "buy_call_spread",
            ]
            or (len(buy_puts) > 0 and len(sell_puts) > 0)
            or (len(buy_calls) > 0 and len(sell_calls) > 0)
        )

        if is_spread:
            # For spreads, max risk is width of spread minus credit received
            return self._calculate_spread_risk(
                buy_puts, sell_puts, buy_calls, sell_calls
            )
        else:
            # For single legs or undefined risk, use traditional calculation
            return self._calculate_naked_risk(signal, contracts)

    def _calculate_spread_risk(
        self,
        buy_puts: list,
        sell_puts: list,
        buy_calls: list,
        sell_calls: list,
    ) -> float:
        """Calculate max risk for a spread strategy."""
        # Calculate net credit/debit
        net_premium = 0.0
        for leg, contract in buy_puts + buy_calls:
            net_premium -= contract.ask * 100 * leg.quantity  # Paying
        for leg, contract in sell_puts + sell_calls:
            net_premium += contract.bid * 100 * leg.quantity  # Receiving

        # Calculate max loss from spread widths
        put_spread_risk = 0.0
        call_spread_risk = 0.0

        # Put spread risk (short strike - long strike)
        if sell_puts and buy_puts:
            max_short_strike = max(c.strike for _, c in sell_puts)
            min_long_strike = min(c.strike for _, c in buy_puts)
            put_width = max_short_strike - min_long_strike
            if put_width > 0:
                # Max quantity from the legs
                qty = max(leg.quantity for leg, _ in sell_puts)
                put_spread_risk = put_width * 100 * qty

        # Call spread risk (long strike - short strike)
        if sell_calls and buy_calls:
            min_short_strike = min(c.strike for _, c in sell_calls)
            max_long_strike = max(c.strike for _, c in buy_calls)
            call_width = max_long_strike - min_short_strike
            if call_width > 0:
                qty = max(leg.quantity for leg, _ in sell_calls)
                call_spread_risk = call_width * 100 * qty

        # For iron condor, risk is max of put or call spread (not sum)
        # since both can't be in the money at once
        spread_width_risk = max(put_spread_risk, call_spread_risk)

        # Max risk = spread width - net credit received
        # If net_premium > 0 (credit), it reduces risk
        # If net_premium < 0 (debit), it increases risk
        max_risk = spread_width_risk - net_premium

        return max(0.0, max_risk)

    def _calculate_naked_risk(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> float:
        """Calculate risk for naked/single leg positions."""
        trade_value = 0.0
        for leg in signal.legs:
            contract = contracts.get(leg.contract_symbol)
            if contract:
                price = contract.mid_price * 100 * leg.quantity
                if leg.side == "buy":
                    trade_value += price
                else:
                    # For sold options, use collateral requirement estimate
                    # Rough estimate: underlying price * 0.2 per contract
                    trade_value += contract.strike * 20 * leg.quantity
        return trade_value

    def _check_daily_loss_limit(self) -> Optional[RiskViolation]:
        """Check if daily loss limit has been reached."""
        if self._daily_loss >= self._config.daily_loss_limit:
            return RiskViolation(
                rule="daily_loss_limit",
                message="Daily loss limit reached",
                current_value=self._daily_loss,
                limit_value=self._config.daily_loss_limit,
            )
        return None

    def _check_drawdown_limit(self) -> Optional[RiskViolation]:
        """Check if portfolio drawdown exceeds limit."""
        if self._peak_equity <= 0:
            return None

        drawdown = ((self._peak_equity - self._current_equity) / self._peak_equity) * 100

        if drawdown >= self._config.max_drawdown_percent:
            return RiskViolation(
                rule="max_drawdown_percent",
                message=f"Portfolio drawdown exceeds {self._config.max_drawdown_percent}%",
                current_value=drawdown,
                limit_value=self._config.max_drawdown_percent,
            )
        return None

    def _check_dte_limits(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> list[RiskViolation]:
        """Check DTE constraints for all legs."""
        violations = []

        for leg in signal.legs:
            contract = contracts.get(leg.contract_symbol)
            if not contract:
                continue

            dte = contract.days_to_expiry

            if dte < self._config.min_days_to_expiry:
                violations.append(
                    RiskViolation(
                        rule="min_days_to_expiry",
                        message=f"{leg.contract_symbol} DTE too low",
                        current_value=dte,
                        limit_value=self._config.min_days_to_expiry,
                    )
                )

            if dte > self._config.max_days_to_expiry:
                violations.append(
                    RiskViolation(
                        rule="max_days_to_expiry",
                        message=f"{leg.contract_symbol} DTE too high",
                        current_value=dte,
                        limit_value=self._config.max_days_to_expiry,
                    )
                )

        return violations

    def _check_liquidity(
        self,
        contracts: dict[str, OptionContract],
    ) -> list[RiskViolation]:
        """Check liquidity constraints (returns warnings)."""
        warnings = []

        for symbol, contract in contracts.items():
            # Check open interest
            if contract.open_interest < self._config.min_open_interest:
                warnings.append(
                    RiskViolation(
                        rule="min_open_interest",
                        message=f"{symbol} has low open interest",
                        current_value=contract.open_interest,
                        limit_value=self._config.min_open_interest,
                        severity="warning",
                    )
                )

            # Check bid-ask spread
            if contract.spread_percent > self._config.max_bid_ask_spread_percent:
                warnings.append(
                    RiskViolation(
                        rule="max_bid_ask_spread_percent",
                        message=f"{symbol} has wide bid-ask spread",
                        current_value=contract.spread_percent,
                        limit_value=self._config.max_bid_ask_spread_percent,
                        severity="warning",
                    )
                )

        return warnings

    def calculate_position_size(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
        risk_per_trade_percent: float = 2.0,
    ) -> int:
        """Calculate appropriate position size based on risk.

        Args:
            signal: The trading signal.
            contracts: Map of contract symbols to OptionContract data.
            risk_per_trade_percent: Max risk as percent of equity.

        Returns:
            Recommended number of contracts.
        """
        if self._current_equity <= 0:
            return 0

        # Calculate max risk per trade
        max_risk = self._current_equity * (risk_per_trade_percent / 100)

        # Estimate risk per contract based on signal type
        risk_per_contract = self._estimate_risk_per_contract(signal, contracts)

        if risk_per_contract <= 0:
            return 1  # Default to 1 contract

        # Calculate position size
        size = int(max_risk / risk_per_contract)

        # Apply limits
        size = max(1, min(size, self._config.max_contracts_per_trade))

        return size

    def _estimate_risk_per_contract(
        self,
        signal: OptionSignal,
        contracts: dict[str, OptionContract],
    ) -> float:
        """Estimate maximum risk per contract for the signal."""
        # For spreads, risk is the spread width minus credit received
        # For naked options, risk is theoretically unlimited (use a proxy)

        total_debit = 0.0
        total_credit = 0.0
        strikes = []

        for leg in signal.legs:
            contract = contracts.get(leg.contract_symbol)
            if not contract:
                continue

            price = contract.mid_price * 100
            strikes.append(contract.strike)

            if leg.side == "buy":
                total_debit += price
            else:
                total_credit += price

        # For debit spreads, max loss is the debit paid
        if total_debit > total_credit:
            return total_debit - total_credit

        # For credit spreads, max loss is spread width minus credit
        if len(strikes) >= 2:
            spread_width = (max(strikes) - min(strikes)) * 100
            return spread_width - (total_credit - total_debit)

        # For single leg sold options, estimate risk as 20% of strike
        if strikes:
            return max(strikes) * 20

        return 500.0  # Default risk estimate

    def get_portfolio_risk(self) -> PortfolioRisk:
        """Get current portfolio risk metrics.

        Returns:
            PortfolioRisk with current state.
        """
        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (
                (self._peak_equity - self._current_equity) / self._peak_equity
            ) * 100

        total_pnl = sum(p.unrealized_pnl for p in self._position_risks.values())

        return PortfolioRisk(
            total_equity=self._current_equity,
            buying_power=self._buying_power,
            positions=list(self._position_risks.values()),
            greeks=self._portfolio_greeks,
            total_unrealized_pnl=total_pnl,
            daily_pnl=self._daily_pnl,
            drawdown_percent=drawdown,
            position_count=len(self._position_risks),
        )

    def get_greek_utilization(self) -> dict[str, float]:
        """Get current Greek utilization as percentage of limits.

        Returns:
            Dict mapping Greek name to utilization percentage.
        """
        return {
            "delta": (
                abs(self._portfolio_greeks.delta) / self._config.max_portfolio_delta
            )
            * 100
            if self._config.max_portfolio_delta > 0
            else 0,
            "gamma": (
                abs(self._portfolio_greeks.gamma) / self._config.max_portfolio_gamma
            )
            * 100
            if self._config.max_portfolio_gamma > 0
            else 0,
            "vega": (
                abs(self._portfolio_greeks.vega) / self._config.max_portfolio_vega
            )
            * 100
            if self._config.max_portfolio_vega > 0
            else 0,
            "theta": (
                abs(self._portfolio_greeks.theta)
                / abs(self._config.min_portfolio_theta)
            )
            * 100
            if self._config.min_portfolio_theta != 0
            else 0,
        }

    def should_reduce_risk(self) -> tuple[bool, str]:
        """Check if risk reduction is recommended.

        Returns:
            Tuple of (should_reduce, reason).
        """
        # Check drawdown
        if self._peak_equity > 0:
            drawdown = (
                (self._peak_equity - self._current_equity) / self._peak_equity
            ) * 100
            if drawdown > self._config.max_drawdown_percent * 0.8:
                return True, f"Drawdown at {drawdown:.1f}%, approaching limit"

        # Check daily loss
        if self._daily_loss > self._config.daily_loss_limit * 0.8:
            return True, f"Daily loss at ${self._daily_loss:.0f}, approaching limit"

        # Check Greeks
        utilization = self.get_greek_utilization()
        for greek, util in utilization.items():
            if util > 80:
                return True, f"{greek.capitalize()} at {util:.0f}% of limit"

        return False, ""

    def reset_daily_tracking(self) -> None:
        """Reset daily tracking metrics (called at market open)."""
        self._daily_loss = 0.0
        self._last_reset_date = datetime.now().date()
        logger.info("Daily risk tracking reset")

    def reset_peak_equity(self) -> None:
        """Reset peak equity to current equity (after drawdown recovery)."""
        self._peak_equity = self._current_equity
        logger.info(f"Peak equity reset to ${self._current_equity:,.2f}")
