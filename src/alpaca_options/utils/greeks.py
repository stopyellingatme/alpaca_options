"""Greeks calculation utilities using Black-Scholes model."""

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from scipy.stats import norm


class OptionType(Enum):
    """Option type enumeration."""

    CALL = "call"
    PUT = "put"


@dataclass
class Greeks:
    """Container for option Greeks."""

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass
class OptionPricing:
    """Complete option pricing result."""

    price: float
    greeks: Greeks
    implied_volatility: Optional[float] = None


class BlackScholes:
    """Black-Scholes option pricing model.

    Calculates theoretical option prices and Greeks for European options.
    Can be used as an approximation for American options on non-dividend
    paying stocks.
    """

    @staticmethod
    def d1(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate d1 parameter for Black-Scholes.

        Args:
            spot: Current underlying price.
            strike: Option strike price.
            time_to_expiry: Time to expiration in years.
            risk_free_rate: Risk-free interest rate (annualized).
            volatility: Implied volatility (annualized).
            dividend_yield: Continuous dividend yield.

        Returns:
            d1 value.
        """
        if time_to_expiry <= 0 or volatility <= 0:
            return 0.0

        numerator = (
            math.log(spot / strike)
            + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry
        )
        denominator = volatility * math.sqrt(time_to_expiry)

        return numerator / denominator

    @staticmethod
    def d2(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate d2 parameter for Black-Scholes.

        Args:
            spot: Current underlying price.
            strike: Option strike price.
            time_to_expiry: Time to expiration in years.
            risk_free_rate: Risk-free interest rate (annualized).
            volatility: Implied volatility (annualized).
            dividend_yield: Continuous dividend yield.

        Returns:
            d2 value.
        """
        d1_val = BlackScholes.d1(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        return d1_val - volatility * math.sqrt(time_to_expiry)

    @staticmethod
    def price(
        option_type: OptionType,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate theoretical option price.

        Args:
            option_type: CALL or PUT.
            spot: Current underlying price.
            strike: Option strike price.
            time_to_expiry: Time to expiration in years.
            risk_free_rate: Risk-free interest rate (annualized).
            volatility: Implied volatility (annualized).
            dividend_yield: Continuous dividend yield.

        Returns:
            Theoretical option price.
        """
        if time_to_expiry <= 0:
            # At expiration, return intrinsic value
            if option_type == OptionType.CALL:
                return max(0, spot - strike)
            else:
                return max(0, strike - spot)

        d1_val = BlackScholes.d1(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        d2_val = BlackScholes.d2(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )

        discount = math.exp(-risk_free_rate * time_to_expiry)
        dividend_discount = math.exp(-dividend_yield * time_to_expiry)

        if option_type == OptionType.CALL:
            price = (
                spot * dividend_discount * norm.cdf(d1_val)
                - strike * discount * norm.cdf(d2_val)
            )
        else:
            price = (
                strike * discount * norm.cdf(-d2_val)
                - spot * dividend_discount * norm.cdf(-d1_val)
            )

        return max(0, price)

    @staticmethod
    def delta(
        option_type: OptionType,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate option delta.

        Delta measures the rate of change of option price with respect
        to the underlying price.

        Returns:
            Delta value (-1 to 1).
        """
        if time_to_expiry <= 0:
            if option_type == OptionType.CALL:
                return 1.0 if spot > strike else 0.0
            else:
                return -1.0 if spot < strike else 0.0

        d1_val = BlackScholes.d1(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        dividend_discount = math.exp(-dividend_yield * time_to_expiry)

        if option_type == OptionType.CALL:
            return dividend_discount * norm.cdf(d1_val)
        else:
            return dividend_discount * (norm.cdf(d1_val) - 1)

    @staticmethod
    def gamma(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate option gamma.

        Gamma measures the rate of change of delta with respect to
        the underlying price. Same for calls and puts.

        Returns:
            Gamma value.
        """
        if time_to_expiry <= 0 or volatility <= 0:
            return 0.0

        d1_val = BlackScholes.d1(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        dividend_discount = math.exp(-dividend_yield * time_to_expiry)

        return (
            dividend_discount
            * norm.pdf(d1_val)
            / (spot * volatility * math.sqrt(time_to_expiry))
        )

    @staticmethod
    def theta(
        option_type: OptionType,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate option theta (per day).

        Theta measures the rate of change of option price with respect
        to time (time decay).

        Returns:
            Theta value (negative for long options).
        """
        if time_to_expiry <= 0 or volatility <= 0:
            return 0.0

        d1_val = BlackScholes.d1(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        d2_val = BlackScholes.d2(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )

        discount = math.exp(-risk_free_rate * time_to_expiry)
        dividend_discount = math.exp(-dividend_yield * time_to_expiry)

        # Common term
        term1 = (
            -spot * dividend_discount * norm.pdf(d1_val) * volatility
            / (2 * math.sqrt(time_to_expiry))
        )

        if option_type == OptionType.CALL:
            theta = (
                term1
                + dividend_yield * spot * dividend_discount * norm.cdf(d1_val)
                - risk_free_rate * strike * discount * norm.cdf(d2_val)
            )
        else:
            theta = (
                term1
                - dividend_yield * spot * dividend_discount * norm.cdf(-d1_val)
                + risk_free_rate * strike * discount * norm.cdf(-d2_val)
            )

        # Return per-day theta (divide by 365)
        return theta / 365

    @staticmethod
    def vega(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate option vega.

        Vega measures the rate of change of option price with respect
        to volatility. Same for calls and puts.

        Returns:
            Vega value (per 1% change in volatility).
        """
        if time_to_expiry <= 0:
            return 0.0

        d1_val = BlackScholes.d1(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        dividend_discount = math.exp(-dividend_yield * time_to_expiry)

        # Return per 1% (0.01) change in volatility
        return (
            spot * dividend_discount * norm.pdf(d1_val) * math.sqrt(time_to_expiry)
        ) / 100

    @staticmethod
    def rho(
        option_type: OptionType,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate option rho.

        Rho measures the rate of change of option price with respect
        to the risk-free interest rate.

        Returns:
            Rho value (per 1% change in rate).
        """
        if time_to_expiry <= 0:
            return 0.0

        d2_val = BlackScholes.d2(
            spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield
        )
        discount = math.exp(-risk_free_rate * time_to_expiry)

        # Return per 1% (0.01) change in rate
        if option_type == OptionType.CALL:
            return strike * time_to_expiry * discount * norm.cdf(d2_val) / 100
        else:
            return -strike * time_to_expiry * discount * norm.cdf(-d2_val) / 100

    @staticmethod
    def calculate_greeks(
        option_type: OptionType,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        dividend_yield: float = 0.0,
    ) -> Greeks:
        """Calculate all Greeks for an option.

        Args:
            option_type: CALL or PUT.
            spot: Current underlying price.
            strike: Option strike price.
            time_to_expiry: Time to expiration in years.
            risk_free_rate: Risk-free interest rate (annualized).
            volatility: Implied volatility (annualized).
            dividend_yield: Continuous dividend yield.

        Returns:
            Greeks dataclass with all values.
        """
        return Greeks(
            delta=BlackScholes.delta(
                option_type, spot, strike, time_to_expiry,
                risk_free_rate, volatility, dividend_yield
            ),
            gamma=BlackScholes.gamma(
                spot, strike, time_to_expiry,
                risk_free_rate, volatility, dividend_yield
            ),
            theta=BlackScholes.theta(
                option_type, spot, strike, time_to_expiry,
                risk_free_rate, volatility, dividend_yield
            ),
            vega=BlackScholes.vega(
                spot, strike, time_to_expiry,
                risk_free_rate, volatility, dividend_yield
            ),
            rho=BlackScholes.rho(
                option_type, spot, strike, time_to_expiry,
                risk_free_rate, volatility, dividend_yield
            ),
        )

    @staticmethod
    def implied_volatility(
        option_type: OptionType,
        market_price: float,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        dividend_yield: float = 0.0,
        precision: float = 0.0001,
        max_iterations: int = 100,
    ) -> Optional[float]:
        """Calculate implied volatility using Newton-Raphson method.

        Args:
            option_type: CALL or PUT.
            market_price: Current market price of the option.
            spot: Current underlying price.
            strike: Option strike price.
            time_to_expiry: Time to expiration in years.
            risk_free_rate: Risk-free interest rate (annualized).
            dividend_yield: Continuous dividend yield.
            precision: Desired precision for IV.
            max_iterations: Maximum iterations for convergence.

        Returns:
            Implied volatility or None if not converged.
        """
        if market_price <= 0 or time_to_expiry <= 0:
            return None

        # Initial guess using Brenner-Subrahmanyam approximation
        iv = math.sqrt(2 * math.pi / time_to_expiry) * market_price / spot

        for _ in range(max_iterations):
            price = BlackScholes.price(
                option_type, spot, strike, time_to_expiry,
                risk_free_rate, iv, dividend_yield
            )
            vega = BlackScholes.vega(
                spot, strike, time_to_expiry,
                risk_free_rate, iv, dividend_yield
            ) * 100  # Convert back from per-1%

            diff = market_price - price

            if abs(diff) < precision:
                return iv

            if vega < 1e-10:
                return None

            iv = iv + diff / vega

            # Keep IV in reasonable bounds
            if iv <= 0.001:
                iv = 0.001
            if iv > 5.0:
                iv = 5.0

        return iv if abs(diff) < precision * 10 else None


def days_to_years(days: int) -> float:
    """Convert days to years (trading days basis).

    Args:
        days: Number of calendar days.

    Returns:
        Time in years.
    """
    return days / 365.0


def calculate_probability_otm(
    option_type: OptionType,
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float = 0.05,
) -> float:
    """Calculate probability of option expiring out of the money.

    Args:
        option_type: CALL or PUT.
        spot: Current underlying price.
        strike: Option strike price.
        time_to_expiry: Time to expiration in years.
        volatility: Implied volatility.
        risk_free_rate: Risk-free rate.

    Returns:
        Probability (0 to 1).
    """
    if time_to_expiry <= 0:
        if option_type == OptionType.CALL:
            return 0.0 if spot > strike else 1.0
        else:
            return 0.0 if spot < strike else 1.0

    d2 = BlackScholes.d2(spot, strike, time_to_expiry, risk_free_rate, volatility)

    if option_type == OptionType.CALL:
        return norm.cdf(-d2)  # Prob(S < K)
    else:
        return norm.cdf(d2)  # Prob(S > K)


def calculate_probability_itm(
    option_type: OptionType,
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float = 0.05,
) -> float:
    """Calculate probability of option expiring in the money.

    Args:
        option_type: CALL or PUT.
        spot: Current underlying price.
        strike: Option strike price.
        time_to_expiry: Time to expiration in years.
        volatility: Implied volatility.
        risk_free_rate: Risk-free rate.

    Returns:
        Probability (0 to 1).
    """
    return 1.0 - calculate_probability_otm(
        option_type, spot, strike, time_to_expiry, volatility, risk_free_rate
    )


def calculate_expected_move(
    spot: float,
    volatility: float,
    time_to_expiry: float,
    confidence: float = 0.68,
) -> tuple[float, float]:
    """Calculate expected move range for the underlying.

    Args:
        spot: Current underlying price.
        volatility: Implied volatility (annualized).
        time_to_expiry: Time to expiration in years.
        confidence: Confidence level (0.68 for 1 std dev).

    Returns:
        Tuple of (lower_bound, upper_bound).
    """
    # Calculate standard deviation for the period
    std_dev = spot * volatility * math.sqrt(time_to_expiry)

    # Get z-score for confidence level
    z = norm.ppf((1 + confidence) / 2)

    move = std_dev * z

    return (spot - move, spot + move)
