# Technical Planning: Low Capital Strategy Research & Implementation

**Created**: 2025-12-03
**Status**: Planning Complete
**Prerequisites**: Completed business specification (Spec.md)

---

## Research & Analysis

### Research Scope

This research phase focused on four critical areas:

1. **Codebase Integration Analysis**: Understanding the existing BaseStrategy architecture, integration points, and patterns for implementing new strategies
2. **Low-Capital Options Strategies Research**: Identifying viable strategies requiring less than $300 capital per trade (vs current $500 for vertical spreads)
3. **Backtesting Best Practices**: Statistical comparison methods, performance metrics, and market regime analysis techniques
4. **Alpaca Options Data API**: Historical data availability, capabilities, and limitations for realistic backtesting

### Key Findings Summary

**Critical Discovery - Data Limitation**: Alpaca historical options data only available from February 2024 forward. Pre-2024 backtesting requires synthetic data generation (already implemented in project).

**Strategy Selection**: Research identified **debit spreads** (bull call/bear put) as the optimal low-capital strategy based on:
- Capital requirements: $50-$250 per trade (60-80% reduction vs credit spreads)
- No margin requirements (debit paid upfront is total capital at risk)
- Better risk/reward than credit spreads (150% profit potential vs 25%)
- Straightforward integration with existing BaseStrategy architecture

**Architecture Insight**: Existing BaseStrategy interface is well-designed for new strategies - minimal code changes required (single new file + registration)

### Codebase Integration Analysis

**Existing Architecture Patterns**:

All strategies inherit from `BaseStrategy` abstract base class (src/alpaca_options/strategies/base.py) with required methods:
- `initialize(config: dict)`: Load strategy configuration from YAML
- `on_market_data(data: MarketData)`: Process market updates (price, indicators, IV)
- `on_option_chain(chain: OptionChain)`: Generate signals from options chains
- `get_criteria()`: Return filtering criteria (IV, DTE, liquidity constraints)
- `cleanup()`: Resource cleanup on shutdown

Data structures: `OptionSignal` (multi-leg signals), `MarketData` (price + indicators), `OptionChain` (contracts with Greeks)

**Related Existing Components**:
- **Models**: `BaseStrategy`, `OptionSignal`, `OptionLeg`, `OptionChain`, `OptionContract` in strategies/base.py
- **Strategy Implementations**: `VerticalSpreadStrategy` (reference implementation), `IronCondorStrategy`, `WheelStrategy`
- **Core Engine**: `TradingEngine` in core/engine.py (strategy loading, signal execution, position management)
- **Risk Management**: `RiskManager` in risk/manager.py (position limits, Greeks constraints, DTE validation)
- **Backtesting**: `BacktestEngine` in backtesting/engine.py (historical simulation with realistic costs)
- **Configuration**: YAML-based config in config/default.yaml with per-strategy parameters

**Integration Requirements**:
- **Files to Modify**:
  - `src/alpaca_options/core/engine.py` (line 282): Add new strategy to registration list
  - `config/default.yaml` (line 100+): Add strategy configuration block
  - `src/alpaca_options/core/capital_manager.py` (line 43): Add capital requirements [OPTIONAL]

- **New Files to Create**:
  - `src/alpaca_options/strategies/debit_spread.py`: New DebitSpreadStrategy class implementing BaseStrategy

- **API Integration Points**:
  - Strategy automatically receives MarketData via on_market_data() from engine
  - OptionChain provided via on_option_chain() with helper methods (filter_by_delta, filter_by_dte, get_calls/puts)
  - Signals returned as OptionSignal objects picked up by engine for execution
  - Risk checks automatically performed by RiskManager before order placement

- **Data Flow**:
  1. Engine loads strategy via registry and calls initialize() with YAML config
  2. Market data streamed → engine → strategy.on_market_data() [cache indicators]
  3. Option chains fetched → engine → strategy.on_option_chain() [generate signal]
  4. Signal returned → RiskManager validation → TradingClient execution
  5. Position management loop monitors positions using signal metadata (profit_target, stop_loss, close_dte)

**Implementation Considerations**:
- **Consistency Requirements**:
  - Follow VerticalSpreadStrategy pattern: cache market data in on_market_data(), generate signals in on_option_chain()
  - Use StrategyCriteria for pre-filtering (IV rank, DTE range, liquidity)
  - Include position management metadata in signals (profit_target, stop_loss, close_dte)
  - Calculate risk/reward before generating signals (min_credit, min_return_on_risk checks)

- **Potential Conflicts**:
  - None identified - architecture cleanly separates strategies from execution/risk management
  - Strategy registration is manual list (not auto-discovered) - must add to engine.py

- **Refactoring Needs**:
  - None required - BaseStrategy interface is stable and well-designed
  - Existing code doesn't need modification except registration and config

### Low-Capital Options Strategy Research

#### Debit Spreads (Bull Call / Bear Put) - **SELECTED STRATEGY**

**Research Date**: 2025-12-03
**Documentation**: optionseducation.org, optionalpha.com, schwab.com

**Capital Requirements**:
- Typical range: $50-$250 per spread
- Example: $5 wide bull call spread costing $2.00 = $200 max risk, $300 max profit
- **Key advantage**: Debit paid is ONLY capital requirement - no margin, funds unlocked after entry

**Mechanics**:
- Bull Call Spread: Buy lower strike call + sell higher strike call (bullish)
- Bear Put Spread: Buy higher strike put + sell lower strike put (bearish)
- Both are directional plays with defined risk

**Profit/Loss Profile**:
- Maximum loss: Net debit paid (e.g., $200)
- Maximum profit: Spread width minus debit (e.g., $500 - $200 = $300)
- Better risk/reward than credit spreads: 150% potential vs 25% for credit spreads

**Delta Selection Guidelines**:
- Common: Buy 60-70 delta, sell 30-40 delta (30-delta width spreads)
- Conservative: Buy 70-80 delta, sell 50-60 delta (tighter, lower cost)
- Aggressive: Buy 50-60 delta, sell 20-30 delta (wider, higher cost but better R:R)

**When Debit Spreads Outperform**:
1. Low volatility environments (cheaper to buy options)
2. Strong directional conviction (profits from large moves)
3. Capital constraints (no margin requirements)
4. Expected IV expansion (long options benefit from vega)

**Decision Rationale**: Selected as primary low-capital strategy due to:
- 60-80% capital reduction vs vertical credit spreads
- No margin requirements (capital efficiency)
- Better risk/reward profile (1.5:1 vs 0.25:1 for credit spreads)
- Straightforward implementation (similar to existing vertical spread logic)
- Works in low IV environments where credit spreads struggle

**Key Sources**:
- [Options Education: Bull Call Spread](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread)
- [Optional Alpha: Debit vs Credit Spreads](https://optionalpha.com/learn/credit-spreads-vs-debit-spreads)
- [Schwab: Credit vs Debit Spreads](https://www.schwab.com/learn/story/credit-vs-debit-spreads-let-volatility-guide-you)

#### Calendar Spreads - ALTERNATIVE OPTION

**Capital Requirements**: $50-$200 per spread (lowest capital requirement)
**Mechanics**: Sell near-term (15-30 DTE), buy far-term (45-90 DTE) at same strike
**Win Rate**: 60-70% (higher than debit spreads)

**Why Not Selected for Initial Implementation**:
- More complex management (rolling front-month leg)
- Requires understanding of time decay arbitrage
- Less intuitive than directional spreads
- Better suited for neutral/range-bound markets (not all conditions)

**Future Consideration**: Could add as second LOW tier strategy after debit spreads proven

#### Poor Man's Covered Call (PMCC) - HIGHER CAPITAL

**Capital Requirements**: $200-$2,500 (too high for initial "low capital" focus)
**Mechanics**: Buy deep ITM LEAPS (delta 0.75-0.85), sell short-term OTM calls
**Capital Efficiency**: 70-85% reduction vs buying 100 shares

**Why Not Selected**:
- Still requires $200+ minimum (higher than debit spreads)
- More suitable for MEDIUM capital tier ($3k-$7k accounts)
- Complexity of managing LEAPS position

**Future Consideration**: Excellent candidate for future capital tier expansion

#### Single-Leg Options - HIGHEST RISK

**Capital Requirements**: $50-$500 per contract
**Win Rate**: 30-45% (lowest of all strategies)
**Risk**: 100% loss possible (options can expire worthless)

**Why Not Selected**:
- High risk of total loss (unlike spreads with defined risk)
- Time decay works against you
- Lower win rates
- Not suitable for systematic trading

**Use Case**: Only for high-conviction event-driven plays (limited use)

### API & Service Research

#### Alpaca Historical Options Data API

**Documentation**: https://docs.alpaca.markets/docs/historical-option-data
**API Version**: v1beta1
**SDK Version**: alpaca-py >= 0.21.0
**Research Date**: 2025-12-03

**Capabilities**:
- **Historical Bars**: Aggregated OHLCV data with custom timeframes (1Min, 5Min, 1Hour, 1Day, etc.)
- **Historical Trades**: Individual trade prints with price, size, exchange, conditions
- **Historical Quotes**: Bid/ask quotes with sizes and exchange information
- **Option Chains**: Real-time/latest chains with all contracts for underlying
- **Snapshots**: Latest trade, quote, Greeks, and implied volatility per contract

**Critical Constraints**:
- **Data Availability**: **Only from February 2024 forward** - major limitation for backtesting
- **Rate Limits (Free Plan)**: 200 API calls/minute (insufficient for serious backtesting)
- **Rate Limits (Paid Plan)**: 10,000 API calls/minute ($99/month Algo Trader Plus)
- **Data Quality (Free)**: Indicative feed only (15-min delayed, not accurate for backtesting)
- **Data Quality (Paid)**: OPRA feed required for real-time accurate data

**Integration Requirements**:
- **SDK**: alpaca-py library already integrated in project
- **Authentication**: API keys (ALPACA_API_KEY, ALPACA_SECRET_KEY) via environment variables
- **Caching**: Local caching critical to minimize API calls (already implemented in project)
- **Fallback**: Synthetic data generation for pre-Feb 2024 periods (already implemented)

**Data Format Example**:
```python
# OptionBarsRequest for historical bars
request = OptionBarsRequest(
    symbol_or_symbols=["AAPL250117C00150000"],
    timeframe=TimeFrame.Day,
    start=datetime(2024, 2, 1),  # Must be Feb 2024+
    end=datetime(2024, 3, 1),
    limit=1000
)
bars = option_client.get_option_bars(request)
```

**Decision Rationale**:
- Alpaca already integrated in project - no new dependencies
- Historical data since Feb 2024 provides ~10 months for initial backtesting
- Project's existing synthetic data generator handles pre-2024 limitation
- For production: Budget $99/month for Algo Trader Plus (OPRA feed + higher rate limits)

**Key Sources**:
- [Alpaca Historical Option Data](https://docs.alpaca.markets/docs/historical-option-data)
- [alpaca-py SDK Reference](https://alpaca.markets/sdks/python/api_reference/data/option/historical.html)
- [Alpaca Forum: Data Availability](https://forum.alpaca.markets/t/does-historical-options-data-starts-from-2024-or-my-script-is-wrong/13976)

### Architecture Pattern Research

#### Options Backtesting Best Practices

**Research Sources**: ORATS University, Option Alpha, QuantStart, SciPy
**Research Date**: 2025-12-03

**Slippage Modeling (ORATS Methodology)**:
- **Single-leg options**: 75% of bid-ask width as slippage
- **Two-leg spreads**: 65% of bid-ask width
- **Four-leg spreads**: 56% of bid-ask width (iron condors)
- Rationale: Multi-leg orders as single transactions achieve better fills

**Cost Modeling**:
- Commission: $0.65 per contract (project already uses this)
- Regulatory fees: $0.03 per contract
- Assignment fees: $5-$10 per assignment
- Track costs separately: gross P&L, commissions, slippage, net P&L

**Early Assignment Simulation**:
- Check short options hourly for assignment risk
- Assign if 5% ITM within 4 days of expiration
- Higher probability approaching ex-dividend dates (short calls)
- Use Monte Carlo + Longstaff-Schwartz algorithm for American options

**Greeks Tracking**:
- Calculate and monitor portfolio-level Greeks: net Delta, Gamma, Theta, Vega
- Enforce constraints (e.g., |Delta| < 0.30, |Gamma| < 0.20)
- Project already has Greeks calculator in utils/greeks.py

**Implementation Considerations**:
- Project's BacktestEngine already implements realistic execution simulation
- Need to add ORATS slippage model (currently uses percentage-based)
- Assignment probability model needs enhancement
- Portfolio Greeks tracking needs to be added to backtest results

**Key Sources**:
- [ORATS Backtesting Methodology](https://orats.com/university/backtesting-methodology)
- [Option Alpha Backtesting Guide](https://optionalpha.com/help/backtesting)
- [QuantConnect Options Assignment](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/options-models/assignment)

#### Statistical Comparison Methods

**Research Sources**: SciPy, SEC API, QuantStart, statsmodels
**Research Date**: 2025-12-03

**Test Selection Strategy**:
1. **Check normality** (Shapiro-Wilk test)
2. **If both strategies normal**: Use independent t-test
3. **If non-normal**: Use Mann-Whitney U test (more robust for options)

**Mann-Whitney U Test (Recommended)**:
```python
from scipy.stats import mannwhitneyu

statistic, p_value = mannwhitneyu(
    strategy_a_returns,
    strategy_b_returns,
    alternative='two-sided'
)

significant = p_value < 0.05  # Reject null if p < 0.05
```

**Bootstrap Confidence Intervals**:
- Generate 10,000 bootstrap samples with replacement
- Calculate metric (mean, Sharpe, profit factor) for each sample
- 95% CI = [2.5th percentile, 97.5th percentile]
- Advantage: No normality assumption, works with any metric

**Multiple Comparison Correction**:
- **Bonferroni**: Divide α by number of tests (conservative)
- **FDR (Benjamini-Hochberg)**: Less conservative, recommended for exploratory analysis
- Apply when comparing 3+ strategies simultaneously

**Effect Size (Cohen's d)**:
```python
cohens_d = (mean_a - mean_b) / pooled_std_dev
```
- Small effect: d = 0.2
- Medium effect: d = 0.5
- Large effect: d = 0.8

**Sample Size Requirements**:
- Minimum 30-50 trades per strategy for statistical power
- Use power analysis to determine required N given expected effect size

**Implementation Considerations**:
- Use scipy.stats for all statistical tests (already in dependencies)
- Implement StrategyComparator class for systematic comparison
- Generate comparison reports with p-values, confidence intervals, effect sizes

**Key Sources**:
- [SciPy Mann-Whitney U](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html)
- [SEC API: Statistical Testing in Finance](https://sec-api.io/resources/testing-statistical-significance-in-financial-data-with-python)
- [QuantStart: Sharpe Ratio](https://www.quantstart.com/articles/Sharpe-Ratio-for-Algorithmic-Trading-Performance-Measurement/)

#### Market Regime Classification

**Research Sources**: QuantInsti, Medium, Macrosynergy
**Research Date**: 2025-12-03

**VIX-Based Thresholds** (Simple Method):
- Low Volatility: VIX < 15
- Normal: VIX 15-20
- Elevated: VIX 20-30
- High Volatility: VIX > 30

**Hidden Markov Model (HMM)** (Advanced Method):
```python
from hmmlearn import hmm

model = hmm.GaussianHMM(n_components=2, covariance_type="full")
model.fit(returns.values.reshape(-1, 1))
regimes = model.predict(returns.values.reshape(-1, 1))
```
- Data-driven, learns regime characteristics automatically
- No arbitrary thresholds
- Requires sufficient data (6+ months)

**Combined VIX + Momentum**:
- High Fear: VIX > 30 AND RSI < 40
- Normal Conditions: VIX < 20 AND 40 < RSI < 60
- Complacency: VIX < 15 AND RSI > 60

**Regime Performance Analysis**:
```python
# Compare strategy returns across regimes
for regime in df['regime'].unique():
    regime_data = df[df['regime'] == regime]
    print(f"{regime}: Mean={regime_data.mean()}, Sharpe={...}")

# ANOVA test: Are returns different across regimes?
from scipy.stats import f_oneway
f_stat, p_value = f_oneway(*regime_groups)
```

**Implementation Considerations**:
- Start with simple VIX thresholds (easiest to implement)
- Add HMM for data-driven regime detection
- Report strategy performance separately by regime in backtest results
- Use ANOVA to test if returns significantly differ across regimes

**Key Sources**:
- [QuantInsti: Regime-Adaptive Trading](https://blog.quantinsti.com/regime-adaptive-trading-python/)
- [Medium: Market Regimes with Python](https://medium.com/@trading.dude/volatility-and-market-regimes-how-changing-risk-shapes-market-behavior-with-python-examples-190de97917d8)
- [Macrosynergy: Classifying Market Regimes](https://macrosynergy.com/research/classifying-market-regimes/)

### Research-Informed Recommendations

**Primary Strategy Choice**: **Debit Spreads** (Bull Call / Bear Put)
- Capital requirement: $50-$250 vs $500 for credit spreads (60-80% reduction)
- Better risk/reward: 150% profit potential vs 25% for credit spreads
- No margin requirements (capital unlocked immediately)
- Straightforward implementation (similar to existing vertical spread logic)

**Backtesting Approach**:
- Use existing BacktestEngine with enhanced slippage model (ORATS methodology)
- Implement Mann-Whitney U test for statistical comparison (non-parametric, robust)
- Add bootstrap confidence intervals for all metrics
- Implement VIX-based regime classification (simple, effective)
- Target: 6+ months of backtesting (Feb-Nov 2024) for statistical power

**Performance Metrics Priority** (in order):
1. **Capital Efficiency**: Return per $1000 deployed (key metric for low-capital strategies)
2. **Sharpe Ratio**: Risk-adjusted returns
3. **Win Rate**: Percentage of profitable trades
4. **Maximum Drawdown**: Worst peak-to-trough decline
5. **Profit Factor**: Total profit / total loss

**Architecture Approach**:
- Single new file: `src/alpaca_options/strategies/debit_spread.py`
- Inherit from BaseStrategy, follow VerticalSpreadStrategy patterns
- Configuration-driven (YAML-based parameters)
- Automatic integration with existing risk management and position tracking

**Key Constraints Identified**:
- **Data Limitation**: Alpaca data only from Feb 2024+ (use synthetic for earlier periods)
- **Sample Size**: Need 30-50 trades minimum for statistical significance (achievable in 6 months)
- **Cost Impact**: Commissions more significant for smaller trades (model accurately)
- **Rate Limits**: Free plan insufficient - budget $99/month for Algo Trader Plus if productionizing

---

## Technical Architecture

> **Note**: This section references the detailed research findings above to avoid duplication.

### System Overview

**High-Level Architecture**: Single new strategy module integrating with existing BaseStrategy architecture. Follows established patterns from VerticalSpreadStrategy with debit spread-specific logic.

**Core Components**:
- **DebitSpreadStrategy**: New strategy class implementing bull call and bear put spreads with directional signal generation based on RSI/MA indicators (researched in codebase integration section)
- **Enhanced BacktestEngine**: Existing engine with ORATS slippage model upgrade (researched in backtesting best practices)
- **StrategyComparator**: New utility class for statistical comparison using Mann-Whitney U test and bootstrap CI (researched in statistical methods)
- **RegimeClassifier**: New utility module for VIX-based market regime identification (researched in market regime analysis)

**Data Flow**:
1. **Strategy Registration**: Engine loads DebitSpreadStrategy via registry pattern
2. **Signal Generation**: MarketData (RSI, MAs) → strategy caches → OptionChain arrives → strategy generates OptionSignal with debit spread legs
3. **Execution**: Signal → RiskManager validation (Greeks, DTE, capital) → TradingClient places multi-leg order
4. **Position Management**: Engine monitors positions using signal metadata (profit_target=50% max profit, stop_loss=2x debit paid, close_dte=21)
5. **Backtesting**: Historical data (Feb 2024+) → BacktestEngine simulates trades → Statistical comparison vs vertical spreads → Regime performance breakdown

### Python Implementation Details

#### Strategy Module Structure

**Module Hierarchy**:
```
src/alpaca_options/strategies/
└── debit_spread.py (new)
    ├── DebitSpreadStrategy(BaseStrategy)
    ├──── __init__()
    ├──── initialize(config: dict) → None
    ├──── on_market_data(data: MarketData) → Optional[OptionSignal]
    ├──── on_option_chain(chain: OptionChain) → Optional[OptionSignal]
    ├──── get_criteria() → StrategyCriteria
    ├──── _determine_direction(symbol: str) → Optional[SpreadDirection]
    ├──── _build_bull_call_spread() → Optional[OptionSignal]
    ├──── _build_bear_put_spread() → Optional[OptionSignal]
    └──── cleanup() → None
```

**Implementation Pattern**:
- **Follow VerticalSpreadStrategy**: Cache market data in on_market_data(), generate signals in on_option_chain()
- **Delta Selection**: Buy 60-70 delta, sell 30-40 delta (configurable via YAML)
- **Direction Logic**: RSI-based (oversold → bullish, overbought → bearish) + MA confirmation
- **Risk/Reward Filters**: Require minimum debit amount, maximum debit/width ratio

**Architectural Decision Rationale**:
- **Why this structure**: Proven pattern from VerticalSpreadStrategy, minimal learning curve
- **Alternatives considered**: Standalone module vs inheritance (chose inheritance for code reuse)
- **Trade-offs**: Tight coupling to BaseStrategy interface (acceptable given stability of interface)

#### Data Structures and Configuration

**Configuration Strategy**: YAML-based (config/default.yaml) following existing pattern

**Strategy Configuration Block**:
```yaml
strategies:
  debit_spread:
    enabled: true
    allocation: 0.3  # 30% of capital for debit spreads
    capital_requirements:
      min_capital: 1500      # $1,500 minimum
      recommended_capital: 3000
      max_allocation_percent: 40
    config:
      underlyings: ["QQQ", "SPY"]

      # Delta selection (buying vs selling strikes)
      long_delta_min: 0.60
      long_delta_max: 0.70
      short_delta_min: 0.30
      short_delta_max: 0.40

      # Entry criteria
      min_dte: 30
      max_dte: 45
      min_iv_rank: 20  # Lower than credit spreads (better in low IV)

      # Technical filters
      rsi_oversold: 45  # Bullish signal
      rsi_overbought: 55  # Bearish signal

      # Risk/reward filters
      max_debit_to_width_ratio: 0.60  # Max 60% of spread width
      min_debit: 30  # Minimum $30 debit ($0.30 x 100)

      # Position management
      profit_target_pct: 0.50  # Close at 50% of max profit
      stop_loss_pct: 2.0  # Close at 200% of debit paid
      close_dte: 21  # Close when <= 21 DTE
```

**Signal Metadata Structure** (for position management):
```python
metadata = {
    "direction": "bull" | "bear",
    "is_debit_spread": True,
    "debit_paid": 200.0,  # Total debit (max risk)
    "max_profit": 300.0,  # Spread width - debit
    "long_strike": 100.0,
    "short_strike": 105.0,
    "long_delta": 0.65,
    "short_delta": 0.35,
    "dte": 35,
    "close_dte": 21,
    "underlying_price": 102.5,
    "spread_width": 5.0,
    "debit_to_width_ratio": 0.40,

    # Position management thresholds
    "profit_target": 150.0,  # 50% of $300 max
    "stop_loss": 400.0,  # 200% of $200 debit
    "expiration": datetime(...),
}
```

**Decision Rationale**:
- **Why YAML config**: Existing project pattern, allows runtime configuration changes without code modifications
- **Why detailed metadata**: Engine's position management loop requires profit_target, stop_loss, close_dte for automatic exits
- **Configuration precedence**: YAML overrides defaults, allowing per-underlying or per-account customization

#### Service Layer Architecture

**New Utility Modules** (to be created):

- **StrategyComparator** (`src/alpaca_options/utils/strategy_comparator.py`):
  - Responsibility: Statistical comparison between strategies using Mann-Whitney U test
  - Methods: `compare_strategies()`, `bootstrap_confidence_interval()`, `calculate_all_metrics()`
  - Uses: scipy.stats for statistical tests (already in dependencies)

- **RegimeClassifier** (`src/alpaca_options/utils/regime_classifier.py`):
  - Responsibility: VIX-based market regime identification
  - Methods: `classify_regime()`, `analyze_regime_performance()`
  - Simple threshold logic: VIX < 15 (low), 15-20 (normal), 20-30 (elevated), > 30 (high)

**External Integration Strategy**:
- **Alpaca API**: Already integrated via alpaca-py client (no changes needed)
- **Authentication**: Environment variables ALPACA_API_KEY, ALPACA_SECRET_KEY (existing)
- **Error Handling**: Existing try/except patterns in alpaca client modules

**Dependency Management**:
- **No New Dependencies Required**: All research-identified libraries already in project
  - scipy >= 1.11.0 (statistical tests)
  - numpy >= 1.26.0 (numerical operations)
  - pandas >= 2.1.0 (data manipulation)
  - alpaca-py >= 0.21.0 (Alpaca API)
- **Optional Future**: hmmlearn for HMM-based regime detection (if implementing advanced regime classification)

#### Python Environment Requirements

**Python Version**: 3.11 or 3.12 (existing project requirement)

**Package Manager**: UV (fast Python package management, already used)

**Development Environment**:
- Type checking: mypy with strict mode
- Linting: ruff with pycodestyle, flakes, isort, bugbear
- Testing: pytest with async support (pytest-asyncio)
- Line length: 100 characters (Black compatible)

**Performance Considerations**:
- Backtesting performance: 6-month backtest should complete in < 5 minutes
- Memory usage: Should handle 1000+ option contracts in memory efficiently
- Async operations: Use asyncio for concurrent API calls and strategy execution

### Implementation Complexity Assessment

**Complexity Level**: **Moderate**

**Implementation Challenges**:
- **Setup and Infrastructure**: Minimal - no new dependencies or infrastructure changes
- **Core Implementation**: Straightforward - follow VerticalSpreadStrategy pattern with debit spread logic
- **Integration Points**: Well-defined - single registration point in engine.py, clear interfaces
- **Testing Requirements**: Moderate - need comprehensive backtests over 6+ months of data

**Risk Assessment**:
- **High Risk Areas**:
  - **Data limitations**: Only 10 months of Alpaca options data available (Feb-Nov 2024)
  - **Sample size**: May not achieve 50+ trades in backtest period (depends on signal frequency)
  - **Market regime coverage**: Feb-Nov 2024 may not cover all volatility regimes
- **Mitigation Strategies**:
  - Use synthetic data for pre-Feb 2024 periods to extend backtest range
  - Lower statistical significance threshold if sample size < 30 trades
  - Manually test strategy in different simulated IV environments
- **Unknowns**:
  - Actual signal frequency (how many debit spread opportunities per month?)
  - Real-world fill quality on debit spreads (ORATS model vs reality)

**Dependency Analysis**:
- **External Dependencies**: None - all required libraries already in project
- **Internal Dependencies**:
  - Minimal changes to engine.py (add strategy to registration list)
  - Add new strategy file (debit_spread.py)
  - Add utility files (strategy_comparator.py, regime_classifier.py)
- **Breaking Changes**: None - backward compatible with existing strategies

**Testing Strategy**:
- **Unit Tests**: Test delta selection logic, direction determination, risk/reward calculations
- **Integration Tests**: Test full signal generation flow with mocked MarketData and OptionChain
- **Backtest Tests**: Verify backtest completes successfully on 6-month period with valid results
- **Comparison Tests**: Test statistical comparison logic (Mann-Whitney U, bootstrap CI)

### Technical Clarifications

**No critical clarifications needed** - research phase provided sufficient detail for implementation.

**Optional enhancements** (can be deferred to future iterations):
- HMM-based regime classification (vs simple VIX thresholds)
- Calendar spread strategy (second low-capital option)
- PMCC strategy for MEDIUM capital tier

---

**Next Phase**: After this technical planning is approved, proceed to `/ctxk:plan:3-steps` for implementation task breakdown.
