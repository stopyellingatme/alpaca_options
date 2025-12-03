"""Capital-based strategy selection and management.

This module provides:
- Capital tier definitions
- Strategy recommendations based on account size
- Dynamic strategy enabling/disabling based on buying power
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from alpaca_options.core.config import Settings, StrategyConfig


class CapitalTier(Enum):
    """Capital tier classifications."""

    MICRO = "micro"  # < $2,000
    LOW = "low"  # $2,000 - $10,000
    MEDIUM = "medium"  # $10,000 - $50,000
    HIGH = "high"  # $50,000 - $100,000
    PREMIUM = "premium"  # > $100,000


@dataclass
class StrategyCapitalRequirements:
    """Capital requirements for a strategy."""

    strategy_name: str
    min_capital: float
    recommended_capital: float
    max_allocation_percent: float
    tier: CapitalTier
    description: str

    def is_suitable_for_capital(self, capital: float) -> bool:
        """Check if strategy is suitable for given capital."""
        return capital >= self.min_capital


# Default capital requirements for each strategy
STRATEGY_CAPITAL_REQUIREMENTS: dict[str, StrategyCapitalRequirements] = {
    "debit_spread": StrategyCapitalRequirements(
        strategy_name="debit_spread",
        min_capital=1500,
        recommended_capital=3000,
        max_allocation_percent=40,
        tier=CapitalTier.LOW,
        description="Lower capital than credit spreads ($50-$250 vs $500). Better risk/reward (150% vs 25%). Best in low IV.",
    ),
    "vertical_spread": StrategyCapitalRequirements(
        strategy_name="vertical_spread",
        min_capital=2000,
        recommended_capital=5000,
        max_allocation_percent=30,
        tier=CapitalTier.LOW,
        description="Best for small accounts. Limited max loss equals spread width.",
    ),
    "iron_condor": StrategyCapitalRequirements(
        strategy_name="iron_condor",
        min_capital=10000,
        recommended_capital=25000,
        max_allocation_percent=25,
        tier=CapitalTier.MEDIUM,
        description="Requires margin for both spreads. Good for neutral markets.",
    ),
    "wheel": StrategyCapitalRequirements(
        strategy_name="wheel",
        min_capital=50000,
        recommended_capital=100000,
        max_allocation_percent=40,
        tier=CapitalTier.HIGH,
        description="Must be able to buy 100 shares if assigned. Best for quality stocks.",
    ),
    "cash_secured_put": StrategyCapitalRequirements(
        strategy_name="cash_secured_put",
        min_capital=25000,
        recommended_capital=50000,
        max_allocation_percent=30,
        tier=CapitalTier.MEDIUM,
        description="Requires cash to cover assignment. Good for accumulating shares.",
    ),
    "covered_call": StrategyCapitalRequirements(
        strategy_name="covered_call",
        min_capital=25000,
        recommended_capital=50000,
        max_allocation_percent=40,
        tier=CapitalTier.MEDIUM,
        description="Requires owning 100 shares. Good for income generation.",
    ),
}


class CapitalManager:
    """Manages strategy selection and allocation based on account capital.

    This class helps users select appropriate strategies based on their
    account size and manages allocations to ensure proper risk management.
    """

    def __init__(
        self,
        capital: float,
        settings: Optional[Settings] = None,
    ):
        """Initialize the capital manager.

        Args:
            capital: Available trading capital.
            settings: Optional settings to override defaults.
        """
        self._capital = capital
        self._settings = settings
        self._requirements = STRATEGY_CAPITAL_REQUIREMENTS.copy()

    @property
    def capital(self) -> float:
        """Current trading capital."""
        return self._capital

    @capital.setter
    def capital(self, value: float) -> None:
        """Update trading capital."""
        self._capital = value

    def get_capital_tier(self) -> CapitalTier:
        """Determine the capital tier based on current capital.

        Returns:
            CapitalTier enum value.
        """
        if self._capital < 2000:
            return CapitalTier.MICRO
        elif self._capital < 10000:
            return CapitalTier.LOW
        elif self._capital < 50000:
            return CapitalTier.MEDIUM
        elif self._capital < 100000:
            return CapitalTier.HIGH
        else:
            return CapitalTier.PREMIUM

    def get_suitable_strategies(self) -> list[str]:
        """Get list of strategies suitable for current capital.

        Returns:
            List of strategy names that are appropriate for the capital level.
        """
        suitable = []
        for name, req in self._requirements.items():
            if req.is_suitable_for_capital(self._capital):
                suitable.append(name)
        return suitable

    def get_recommended_strategies(self) -> list[str]:
        """Get recommended strategies for current capital tier.

        Returns prioritized list based on capital tier.

        Returns:
            List of strategy names, prioritized by recommendation.
        """
        tier = self.get_capital_tier()

        # Recommendations by tier (in priority order)
        recommendations: dict[CapitalTier, list[str]] = {
            CapitalTier.MICRO: [],  # Not enough capital for options trading
            CapitalTier.LOW: ["debit_spread", "vertical_spread"],
            CapitalTier.MEDIUM: ["vertical_spread", "iron_condor", "debit_spread"],
            CapitalTier.HIGH: ["vertical_spread", "iron_condor", "wheel", "cash_secured_put", "debit_spread"],
            CapitalTier.PREMIUM: ["wheel", "iron_condor", "vertical_spread", "cash_secured_put", "covered_call", "debit_spread"],
        }

        return recommendations.get(tier, [])

    def get_strategy_recommendation(self, strategy_name: str) -> dict:
        """Get detailed recommendation for a specific strategy.

        Args:
            strategy_name: Name of the strategy to analyze.

        Returns:
            Dict with recommendation details.
        """
        req = self._requirements.get(strategy_name)
        if not req:
            return {
                "strategy": strategy_name,
                "suitable": False,
                "reason": "Unknown strategy",
            }

        suitable = req.is_suitable_for_capital(self._capital)
        capital_shortfall = max(0, req.min_capital - self._capital)
        recommended_allocation = 0.0

        if suitable:
            # Calculate recommended allocation based on capital
            if self._capital >= req.recommended_capital:
                recommended_allocation = req.max_allocation_percent
            else:
                # Scale down allocation proportionally
                scale = self._capital / req.recommended_capital
                recommended_allocation = req.max_allocation_percent * scale * 0.8

        return {
            "strategy": strategy_name,
            "suitable": suitable,
            "min_capital": req.min_capital,
            "recommended_capital": req.recommended_capital,
            "current_capital": self._capital,
            "capital_shortfall": capital_shortfall,
            "recommended_allocation_percent": round(recommended_allocation, 1),
            "max_allocation_percent": req.max_allocation_percent,
            "tier": req.tier.value,
            "description": req.description,
        }

    def calculate_optimal_allocations(self) -> dict[str, float]:
        """Calculate optimal allocations across suitable strategies.

        Returns:
            Dict mapping strategy name to allocation percentage.
        """
        suitable = self.get_suitable_strategies()
        if not suitable:
            return {}

        tier = self.get_capital_tier()

        # Allocation weights by tier
        allocation_weights: dict[CapitalTier, dict[str, float]] = {
            CapitalTier.LOW: {
                "debit_spread": 0.5,
                "vertical_spread": 0.5,
            },
            CapitalTier.MEDIUM: {
                "vertical_spread": 0.4,
                "iron_condor": 0.4,
                "debit_spread": 0.2,
            },
            CapitalTier.HIGH: {
                "vertical_spread": 0.3,
                "iron_condor": 0.3,
                "wheel": 0.4,
            },
            CapitalTier.PREMIUM: {
                "vertical_spread": 0.2,
                "iron_condor": 0.3,
                "wheel": 0.4,
                "cash_secured_put": 0.1,
            },
        }

        weights = allocation_weights.get(tier, {})

        # Filter to only suitable strategies and normalize
        allocations = {}
        total_weight = sum(weights.get(s, 0) for s in suitable)

        if total_weight > 0:
            for strategy in suitable:
                weight = weights.get(strategy, 0)
                if weight > 0:
                    # Normalize and apply max allocation from requirements
                    max_alloc = self._requirements[strategy].max_allocation_percent
                    allocations[strategy] = min(
                        (weight / total_weight) * 80,  # Use 80% of capital max
                        max_alloc,
                    )

        return allocations

    def get_capital_summary(self) -> dict:
        """Get a comprehensive capital and strategy summary.

        Returns:
            Dict with full capital analysis.
        """
        tier = self.get_capital_tier()
        suitable = self.get_suitable_strategies()
        recommended = self.get_recommended_strategies()
        allocations = self.calculate_optimal_allocations()

        return {
            "capital": self._capital,
            "tier": tier.value,
            "tier_description": self._get_tier_description(tier),
            "suitable_strategies": suitable,
            "recommended_strategies": recommended,
            "optimal_allocations": allocations,
            "strategy_details": {
                name: self.get_strategy_recommendation(name)
                for name in STRATEGY_CAPITAL_REQUIREMENTS.keys()
            },
        }

    def _get_tier_description(self, tier: CapitalTier) -> str:
        """Get human-readable description for a capital tier."""
        descriptions = {
            CapitalTier.MICRO: "Account size too small for most options strategies. Consider paper trading first.",
            CapitalTier.LOW: "Suitable for defined-risk spread strategies. Focus on vertical spreads.",
            CapitalTier.MEDIUM: "Can trade most spread strategies. Good for iron condors and verticals.",
            CapitalTier.HIGH: "Full access to all strategies including wheel. Focus on quality underlyings.",
            CapitalTier.PREMIUM: "Premium account. Can run multiple strategies simultaneously with diversification.",
        }
        return descriptions.get(tier, "Unknown tier")

    def create_capital_aware_config(self) -> dict[str, StrategyConfig]:
        """Create strategy configs optimized for current capital.

        Returns:
            Dict of strategy configs with appropriate allocations.
        """
        allocations = self.calculate_optimal_allocations()
        configs = {}

        for strategy_name, allocation in allocations.items():
            req = self._requirements[strategy_name]
            configs[strategy_name] = StrategyConfig(
                enabled=True,
                allocation=allocation / 100,  # Convert to decimal
                config={},
            )

        # Disable strategies that aren't suitable
        for strategy_name in STRATEGY_CAPITAL_REQUIREMENTS.keys():
            if strategy_name not in configs:
                configs[strategy_name] = StrategyConfig(
                    enabled=False,
                    allocation=0.0,
                    config={},
                )

        return configs


def recommend_strategies_for_capital(capital: float) -> None:
    """Print strategy recommendations for a given capital amount.

    Args:
        capital: Available trading capital.
    """
    manager = CapitalManager(capital)
    summary = manager.get_capital_summary()

    print(f"\n{'='*60}")
    print(f"Capital Analysis: ${capital:,.2f}")
    print(f"{'='*60}")
    print(f"\nCapital Tier: {summary['tier'].upper()}")
    print(f"{summary['tier_description']}")

    print(f"\n{'Suitable Strategies':}")
    if summary["suitable_strategies"]:
        for name in summary["suitable_strategies"]:
            details = summary["strategy_details"][name]
            print(f"  - {name}: {details['description']}")
    else:
        print("  None - account size too small")

    print(f"\n{'Recommended Allocations':}")
    if summary["optimal_allocations"]:
        for name, alloc in summary["optimal_allocations"].items():
            dollar_amount = capital * (alloc / 100)
            print(f"  - {name}: {alloc:.1f}% (${dollar_amount:,.2f})")
    else:
        print("  None")

    print(f"\n{'Strategy Details':}")
    for name, details in summary["strategy_details"].items():
        status = "Suitable" if details["suitable"] else f"Need ${details['capital_shortfall']:,.0f} more"
        print(f"  {name}:")
        print(f"    Status: {status}")
        print(f"    Min Capital: ${details['min_capital']:,.0f}")
        print(f"    Recommended: ${details['recommended_capital']:,.0f}")

    print()
