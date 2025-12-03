# Implementation Steps: Low Capital Strategy (Debit Spreads)
<!-- Template Version: 12 | ContextKit: 0.2.0 | Updated: 2025-10-17 -->

## 🚨 CRITICAL: This File is Your Progress Tracker

**This Steps.md file serves as the authoritative source of truth for implementation progress across all development sessions.**

### Key Principles
- **Token limits are irrelevant** - Progress is tracked here, sessions are resumable
- **Never rush or take shortcuts** - Each step deserves proper attention and time
- **Session boundaries don't matter** - User can resume where this file shows progress
- **Steps.md is the real todo list** - Even if AI uses TodoWrite during a session, THIS file is what persists
- **Quality over speed** - Thoroughness is mandatory, optimization for token limits is forbidden
- **Check off progress here** - Mark tasks as complete in this file as they're finished

### How This Works
1. Each task has a checkbox: `- [ ] **S001** Task description`
2. As tasks complete, they're marked: `- [x] **S001** Task description`
3. AI ignores token limit concerns and works methodically through steps
4. If context usage gets high (>80%), AI suggests user runs `/compact` before continuing
5. If session ends: User starts new session and resumes (this file has all progress)
6. Take the time needed for each step - there's no rush to finish in one session

---

# Implementation Steps: Low Capital Strategy (Debit Spreads)

**Created**: 2025-12-03
**Status**: Implementation Plan
**Prerequisites**: Completed business specification (Spec.md) and technical planning (Tech.md with research and architecture)

## Implementation Phases *(mandatory)*

### Phase 1: Setup & Configuration
*Foundation tasks that must complete before development*

- [x] **S001** Add debit spread strategy configuration to YAML ✅ Completed 2025-12-03
  - **Path**: `config/default.yaml` (add new strategy block around line 100+)
  - **Dependencies**: None
  - **Notes**: Add complete configuration block with delta selection, entry criteria, technical filters, risk/reward filters, and position management parameters as specified in Tech.md lines 470-505
  - **Config Structure**:
    - `enabled: true`, `allocation: 0.3`
    - `capital_requirements`: min_capital (1500), recommended_capital (3000), max_allocation_percent (40)
    - `config`: underlyings ([QQQ, SPY]), delta ranges (long 0.60-0.70, short 0.30-0.40), DTE (30-45), IV rank (>20), RSI thresholds, risk/reward filters, position management rules
  - **Implementation**: Added debit_spread configuration block at line 179-222 with all required parameters. Also added debit_spread to LOW capital tier enabled_strategies list.

- [x] **S002** [P] Create utility module directory structure ✅ Completed 2025-12-03
  - **Path**: Verify `src/alpaca_options/utils/` directory exists
  - **Dependencies**: None
  - **Notes**: Prepare for new utility modules (strategy_comparator.py, regime_classifier.py). Directory likely already exists from existing utils/greeks.py
  - **Verification**: Confirmed utils directory exists at src/alpaca_options/utils/ with __init__.py and greeks.py already present

- [x] **S003** [P] Document capital tier update (optional enhancement) ✅ Completed 2025-12-03
  - **Path**: Review `src/alpaca_options/core/capital_manager.py` around line 43
  - **Dependencies**: None
  - **Notes**: Optional task - determine if LOW tier capital requirements need adjustment for debit spreads. Tech.md suggests this is optional since strategy config already defines min_capital
  - **Implementation**: Added debit_spread to STRATEGY_CAPITAL_REQUIREMENTS dict with min_capital=1500, recommended=3000. Updated recommendations and allocation_weights for all capital tiers to include debit_spread strategy.

**🏁 MILESTONE: Foundation Setup**
*Use Task tool with commit-changes agent to commit: "Setup debit spread strategy foundation - configuration and structure"*

### Phase 2: Data Layer (TDD Approach)
*Models, data structures, and business logic foundation*

#### Test-First Implementation
- [ ] **S004** [P] Create test file for DebitSpreadStrategy
  - **Path**: `tests/test_strategies/test_debit_spread.py` (new file)
  - **Dependencies**: S001 (config must exist)
  - **Notes**: Create comprehensive test cases covering:
    - Strategy initialization with YAML config
    - Direction determination logic (RSI-based: oversold→bullish, overbought→bearish)
    - Delta selection and filtering (buy 60-70 delta, sell 30-40 delta)
    - Risk/reward validation (debit_to_width_ratio, min_debit checks)
    - Signal generation for bull call spreads (bullish direction)
    - Signal generation for bear put spreads (bearish direction)
    - Signal metadata structure validation (profit_target, stop_loss, close_dte)
    - Integration with StrategyCriteria (IV rank, DTE range, liquidity)

- [ ] **S005** [P] Create test file for RegimeClassifier utility
  - **Path**: `tests/test_utils/test_regime_classifier.py` (new file)
  - **Dependencies**: None
  - **Notes**: Test VIX-based regime classification logic:
    - Low volatility: VIX < 15
    - Normal: VIX 15-20
    - Elevated: VIX 20-30
    - High volatility: VIX > 30
    - Regime performance analysis functionality
    - ANOVA test for returns across regimes (scipy.stats.f_oneway)

- [ ] **S006** [P] Create test file for StrategyComparator utility
  - **Path**: `tests/test_utils/test_strategy_comparator.py` (new file)
  - **Dependencies**: None
  - **Notes**: Test statistical comparison methods:
    - Mann-Whitney U test implementation (scipy.stats.mannwhitneyu)
    - Bootstrap confidence interval generation (10,000 samples)
    - Cohen's d effect size calculation
    - Multiple comparison correction (Bonferroni, FDR)
    - Comprehensive metrics calculation (Sharpe, profit factor, capital efficiency)

#### Strategy Implementation
- [ ] **S007** Implement DebitSpreadStrategy class
  - **Path**: `src/alpaca_options/strategies/debit_spread.py` (new file ~300-400 lines)
  - **Dependencies**: S004 (tests written), S001 (config exists)
  - **Notes**: Follow VerticalSpreadStrategy pattern from Tech.md lines 456-464:
    - Inherit from BaseStrategy
    - Implement required methods: `initialize()`, `on_market_data()`, `on_option_chain()`, `get_criteria()`, `cleanup()`
    - Cache market data (RSI, MAs) in `on_market_data()` keyed by symbol
    - Determine direction in `_determine_direction()` using cached RSI values
    - Generate signals in `on_option_chain()` using `_build_bull_call_spread()` or `_build_bear_put_spread()`
    - Include comprehensive signal metadata as specified in Tech.md lines 508-528
    - Implement delta filtering, DTE validation, risk/reward checks
  - **Implementation Pattern**: Reference existing `src/alpaca_options/strategies/vertical_spread.py` for established patterns

- [ ] **S008** [P] Implement RegimeClassifier utility
  - **Path**: `src/alpaca_options/utils/regime_classifier.py` (new file ~100-150 lines)
  - **Dependencies**: S005 (tests written)
  - **Notes**: Implement VIX-based regime classification as specified in Tech.md lines 331-375:
    - `classify_regime(vix_value: float) -> str` method using threshold logic
    - `analyze_regime_performance(df: pd.DataFrame) -> Dict` method
    - ANOVA test integration for statistical regime comparison
    - Optional: HMM-based regime detection for future enhancement (can defer)

- [ ] **S009** [P] Implement StrategyComparator utility
  - **Path**: `src/alpaca_options/utils/strategy_comparator.py` (new file ~200-250 lines)
  - **Dependencies**: S006 (tests written)
  - **Notes**: Implement statistical comparison as specified in Tech.md lines 280-324:
    - `compare_strategies()` method with Mann-Whitney U test
    - `bootstrap_confidence_interval()` method (10,000 samples, 95% CI)
    - `calculate_all_metrics()` including: Sharpe ratio, profit factor, win rate, max drawdown, capital efficiency (return per $1000)
    - Effect size calculation (Cohen's d)
    - Multiple comparison correction (Bonferroni method)
    - Use scipy.stats for all statistical operations (already in dependencies)

**🏁 MILESTONE: Strategy Implementation Complete**
*Use Task tool with commit-changes agent to commit: "Implement debit spread strategy and statistical utilities"*

### Phase 3: Service Layer
*Business logic, API integration, data management*

#### Integration Testing
- [ ] **S010** [P] Create integration test for strategy registration
  - **Path**: `tests/test_core/test_engine_integration.py` (add test case to existing file)
  - **Dependencies**: S007 (DebitSpreadStrategy implemented)
  - **Notes**: Test that DebitSpreadStrategy loads correctly via engine's strategy registry, initializes with config, and can receive market data/option chains

- [ ] **S011** [P] Create backtest enhancement test
  - **Path**: `tests/test_backtesting/test_slippage_model.py` (new file)
  - **Dependencies**: None
  - **Notes**: Test ORATS slippage methodology implementation:
    - Single-leg: 75% of bid-ask spread
    - Two-leg spreads (debit spreads): 65% of bid-ask spread
    - Four-leg spreads (iron condors): 56% of bid-ask spread
    - Verify slippage calculation integration in BacktestEngine

#### Service Implementation
- [ ] **S012** Register DebitSpreadStrategy in TradingEngine
  - **Path**: `src/alpaca_options/core/engine.py` (modify around line 282)
  - **Dependencies**: S007 (DebitSpreadStrategy class exists)
  - **Error Handling**: Follow existing pattern for strategy loading with try/except
  - **Integration**: Add import statement and registration to strategy list following Tech.md lines 54-58
  - **Pattern**:
    ```python
    from alpaca_options.strategies.debit_spread import DebitSpreadStrategy
    # Add to registration loop
    ```

- [ ] **S013** Enhance BacktestEngine with ORATS slippage model
  - **Path**: `src/alpaca_options/backtesting/engine.py` (modify slippage calculation method)
  - **Dependencies**: S011 (slippage tests written)
  - **Notes**: Replace existing percentage-based slippage with ORATS methodology from Tech.md lines 236-242:
    - Detect number of legs in position (1, 2, or 4)
    - Apply appropriate slippage percentage (75%, 65%, 56%)
    - Calculate slippage from bid-ask spread width
    - Update execution simulation to use new model

- [ ] **S014** [P] Add portfolio Greeks tracking to backtest results
  - **Path**: `src/alpaca_options/backtesting/engine.py` (add Greeks aggregation to results)
  - **Dependencies**: S007 (strategy generates positions with Greeks)
  - **Notes**: Enhance backtest results to include portfolio-level Greeks tracking:
    - Net Delta, Gamma, Theta, Vega across all open positions
    - Track Greeks evolution over time (daily snapshots)
    - Validate against risk constraints (|Delta| < 0.30, |Gamma| < 0.20)
    - Reference existing utils/greeks.py for calculations

- [ ] **S015** Validate risk management integration
  - **Path**: Review `src/alpaca_options/risk/manager.py` behavior with debit spreads
  - **Dependencies**: S007, S012 (strategy implemented and registered)
  - **Notes**: Verify RiskManager correctly handles debit spread positions:
    - Capital requirement = debit paid (no margin)
    - DTE validation works correctly (21-45 day range)
    - Position sizing respects max_allocation_percent from config
    - Portfolio Greeks constraints enforced
    - No code changes expected - validation task only

**🏁 MILESTONE: Service Integration Complete**
*Use Task tool with commit-changes agent to commit: "Integrate debit spread strategy with engine and enhance backtesting"*

### Phase 4: CLI & Output Enhancement
*Command-line interface, terminal output, reporting*

#### CLI Testing
- [ ] **S016** [P] Create test for CLI strategy selection
  - **Path**: `tests/test_cli.py` (add test cases to existing file)
  - **Dependencies**: S012 (strategy registered)
  - **Notes**: Test that `--strategy debit_spread` flag works correctly in CLI, loads configuration, and initializes strategy

- [ ] **S017** [P] Create test for backtest comparison output
  - **Path**: `tests/test_backtesting/test_comparison_output.py` (new file)
  - **Dependencies**: S009 (StrategyComparator exists)
  - **Notes**: Test comparison report generation with mock data, verify formatting includes all required metrics (p-values, confidence intervals, effect sizes)

#### Output Implementation
- [ ] **S018** Update CLI backtest command for strategy comparison
  - **Path**: `src/alpaca_options/cli.py` (add comparison command or flag)
  - **Dependencies**: S009 (StrategyComparator implemented)
  - **Patterns**: Follow existing Typer CLI patterns
  - **Notes**: Add command like `alpaca-options compare --strategy1 vertical_spread --strategy2 debit_spread --symbol QQQ --period 6M`

- [ ] **S019** [P] Implement comparison output formatter
  - **Path**: `src/alpaca_options/ui/comparison_output.py` (new file ~150 lines)
  - **Dependencies**: S009 (StrategyComparator)
  - **Notes**: Use Rich library to create formatted comparison tables:
    - Performance metrics table (returns, Sharpe, win rate, drawdown)
    - Statistical significance indicators (p-values, confidence intervals)
    - Capital efficiency comparison (return per $1000 deployed)
    - Winner determination with visual indicators
    - Regime-specific performance breakdown

- [ ] **S020** [P] Implement regime performance breakdown output
  - **Path**: `src/alpaca_options/ui/regime_output.py` (new file ~100 lines)
  - **Dependencies**: S008 (RegimeClassifier)
  - **Notes**: Create Rich-formatted tables showing strategy performance by market regime:
    - Performance in low volatility (VIX < 15)
    - Performance in normal volatility (VIX 15-20)
    - Performance in elevated volatility (VIX 20-30)
    - Performance in high volatility (VIX > 30)
    - ANOVA test results showing statistical significance of regime differences

**🏁 MILESTONE: CLI Enhancement Complete**
*Use Task tool with commit-changes agent to commit: "Enhance CLI with strategy comparison and regime analysis output"*

### Phase 5: Automated Integration & Build Validation
*Automated testing, builds, and code quality checks that AI can execute*

- [ ] **S021** [P] Run complete test suite for debit spread feature
  - **Path**: Execute pytest for all new and modified test files
  - **Dependencies**: S004-S011, S016-S017 (all tests created)
  - **Notes**: Use Task tool with run-test-suite agent to execute:
    - `tests/test_strategies/test_debit_spread.py`
    - `tests/test_utils/test_regime_classifier.py`
    - `tests/test_utils/test_strategy_comparator.py`
    - `tests/test_backtesting/test_slippage_model.py`
    - `tests/test_cli.py` (new test cases)
    - Verify all tests pass with proper coverage

- [ ] **S022** [P] Type checking validation with mypy
  - **Path**: Run mypy strict mode on new modules
  - **Dependencies**: S007-S009, S018-S020 (all implementations complete)
  - **Notes**: Execute `uv run mypy src/alpaca_options/strategies/debit_spread.py src/alpaca_options/utils/regime_classifier.py src/alpaca_options/utils/strategy_comparator.py src/alpaca_options/ui/comparison_output.py src/alpaca_options/ui/regime_output.py`
  - Ensure no type errors in strict mode (project requirement)

- [ ] **S023** [P] Code linting with ruff
  - **Path**: Run ruff linter on new and modified files
  - **Dependencies**: S007-S009, S018-S020 (all implementations complete)
  - **Notes**: Execute `uv run ruff check src/alpaca_options/strategies/debit_spread.py src/alpaca_options/utils/ src/alpaca_options/ui/comparison_output.py src/alpaca_options/ui/regime_output.py`
  - Fix any linting violations (line length 100 chars, code style compliance)

- [ ] **S024** Build validation and dependency resolution
  - **Path**: Full project build with UV
  - **Dependencies**: All implementation tasks (S001-S020)
  - **Notes**: Use Task tool with build-project agent to validate:
    - `uv sync` completes successfully (no dependency conflicts)
    - All imports resolve correctly
    - No build warnings or errors
    - Project installs cleanly

**🏁 MILESTONE: Automated Validation Complete**
*Use Task tool with commit-changes agent to commit: "Complete debit spread feature automated testing and validation"*

### Phase 6: Manual User Testing & Validation
*Tasks requiring human interaction with running application*

- [ ] **S025** Manual comprehensive backtest execution
  ```
  ═══════════════════════════════════════════════════
  ║ 🧪 MANUAL BACKTEST VALIDATION REQUIRED
  ═══════════════════════════════════════════════════
  ║
  ║ 1. Set environment variables:
  ║    export ALPACA_API_KEY=your_key
  ║    export ALPACA_SECRET_KEY=your_secret
  ║
  ║ 2. Run debit spread backtest:
  ║    uv run alpaca-options backtest \
  ║      --strategy debit_spread \
  ║      --symbol QQQ \
  ║      --start-date 2024-02-01 \
  ║      --end-date 2024-11-30 \
  ║      --capital 5000
  ║
  ║ 3. Verify output includes:
  ║    ✓ Trade execution log with entry/exit details
  ║    ✓ Performance metrics (return %, Sharpe, win rate, max drawdown)
  ║    ✓ Capital efficiency (return per $1000 deployed)
  ║    ✓ Cost breakdown (gross P&L, commissions, slippage, net P&L)
  ║    ✓ Greeks tracking over time
  ║
  ║ 4. Run vertical spread backtest for comparison:
  ║    uv run alpaca-options backtest \
  ║      --strategy vertical_spread \
  ║      --symbol QQQ \
  ║      --start-date 2024-02-01 \
  ║      --end-date 2024-11-30 \
  ║      --capital 5000
  ║
  ║ Reply "✅ Passed" with key metrics or "❌ Issues: [description]"
  ```

- [ ] **S026** Manual strategy comparison execution
  ```
  ═══════════════════════════════════════════════════
  ║ 🧪 MANUAL COMPARISON VALIDATION REQUIRED
  ═══════════════════════════════════════════════════
  ║
  ║ 1. Run strategy comparison command:
  ║    uv run alpaca-options compare \
  ║      --strategy1 vertical_spread \
  ║      --strategy2 debit_spread \
  ║      --symbol QQQ \
  ║      --period 6M
  ║
  ║ 2. Verify comparison output includes:
  ║    ✓ Side-by-side performance metrics table
  ║    ✓ Mann-Whitney U test results (p-value, significance)
  ║    ✓ Bootstrap confidence intervals (95% CI for each metric)
  ║    ✓ Cohen's d effect size
  ║    ✓ Winner determination or "inconclusive" statement
  ║    ✓ Capital efficiency comparison
  ║
  ║ 3. Verify regime performance breakdown:
  ║    ✓ Performance in each volatility regime (low, normal, elevated, high)
  ║    ✓ ANOVA test results showing regime significance
  ║
  ║ 4. Check report readability and clarity
  ║
  ║ Reply "✅ Passed" with winner or "❌ Issues: [description]"
  ```

- [ ] **S027** Manual paper trading validation
  ```
  ═══════════════════════════════════════════════════
  ║ 🧪 MANUAL PAPER TRADING VALIDATION REQUIRED
  ═══════════════════════════════════════════════════
  ║
  ║ 1. Update paper trading config to enable debit_spread:
  ║    Edit config/paper_qqq.yaml:
  ║    - Set debit_spread.enabled: true
  ║    - Set vertical_spread.enabled: false (test debit spread only)
  ║
  ║ 2. Run paper trading session:
  ║    uv run alpaca-options run --paper --config config/paper_qqq.yaml
  ║
  ║ 3. Monitor for signal generation:
  ║    ✓ Strategy loads correctly without errors
  ║    ✓ Receives market data and option chains
  ║    ✓ Generates signals with correct direction (bull/bear)
  ║    ✓ Signal metadata includes profit_target, stop_loss, close_dte
  ║
  ║ 4. If signal generated, verify:
  ║    ✓ RiskManager validates position (capital, Greeks, DTE)
  ║    ✓ Order placed correctly as 2-leg spread
  ║    ✓ Position tracking monitors P&L
  ║
  ║ 5. Let run for 15-30 minutes to observe behavior
  ║
  ║ Reply "✅ Passed" with observations or "❌ Issues: [description]"
  ```

- [ ] **S028** Manual edge case scenario testing
  ```
  ═══════════════════════════════════════════════════
  ║ 🧪 MANUAL EDGE CASE TESTING REQUIRED
  ═══════════════════════════════════════════════════
  ║
  ║ Test the following edge cases manually:
  ║
  ║ 1. Insufficient capital scenario:
  ║    - Set config with min_capital: 10000 (high requirement)
  ║    - Run backtest with --capital 5000
  ║    - Verify: Strategy skips trades with capital warning
  ║
  ║ 2. Low IV environment (unfavorable for debit spreads):
  ║    - Run backtest during low IV period (if data available)
  ║    - Verify: Strategy filters correctly with min_iv_rank: 20
  ║
  ║ 3. Extreme volatility (VIX > 40):
  ║    - Backtest during high volatility period
  ║    - Verify: Regime classifier correctly identifies high volatility
  ║    - Check: Performance metrics separately tracked
  ║
  ║ 4. No valid option chains (illiquid underlying):
  ║    - Try backtest with low-liquidity symbol
  ║    - Verify: Strategy handles gracefully without crashes
  ║
  ║ 5. Conflicting signals (rapid direction changes):
  ║    - Monitor paper trading during volatile market
  ║    - Verify: Strategy doesn't open conflicting positions
  ║
  ║ Reply "✅ Passed all scenarios" or "❌ Failed: [scenario and description]"
  ```

**🏁 MILESTONE: User Testing Complete**
*All manual validation scenarios verified - ready for production consideration*

### Phase 7: Release Preparation & Compliance
*Final automated tasks and external process preparation*

- [ ] **S029** [P] Update project documentation
  - **Path**: `CLAUDE.md` (add debit spread strategy section)
  - **Dependencies**: All implementation complete
  - **Notes**: Document new strategy in main project documentation:
    - Add "Debit Spreads (LOW Tier)" section to Trading Strategies
    - Include capital requirements ($50-$250 vs $500 for credit spreads)
    - Document entry criteria (delta selection, RSI logic, IV requirements)
    - Add exit rules (profit target 50% max profit, stop loss 2x debit, close at 21 DTE)
    - Include example configuration from config/default.yaml

- [ ] **S030** [P] Update Context.md with feature details
  - **Path**: `Context.md` (add to strategies list)
  - **Dependencies**: All implementation complete
  - **Notes**: Add debit_spread.py to component file structure list in Context.md around line 60:
    - Add to strategies/ section: `├── debit_spread.py         # Debit spreads (LOW tier)`
    - Update strategy count and descriptions

- [ ] **S031** Create backtest comparison report template
  - **Path**: `docs/backtest_reports/debit_spread_vs_vertical_spread.md` (new file)
  - **Dependencies**: S025, S026 (manual backtests complete)
  - **Notes**: Create comprehensive comparison report documenting:
    - Executive summary with winner determination
    - Detailed performance metrics for both strategies
    - Statistical significance analysis (Mann-Whitney U, p-values, effect sizes)
    - Capital efficiency comparison (return per $1000 deployed)
    - Regime-specific performance breakdown
    - Recommendations for production deployment
    - Optimal entry/exit criteria and position sizing
    - Address all FR-010 requirements from Spec.md

- [ ] **S032** Production deployment recommendations
  ```
  ═══════════════════════════════════════════════════
  ║ 📋 PRODUCTION DEPLOYMENT RECOMMENDATIONS
  ═══════════════════════════════════════════════════
  ║
  ║ Based on backtest results and paper trading validation:
  ║
  ║ 1. Review backtest comparison report (S031)
  ║
  ║ 2. Decision criteria for enabling debit_spread in production:
  ║    ✓ Backtest shows statistically significant improvement (p < 0.05)
  ║    ✓ Capital efficiency exceeds vertical_spread by >20%
  ║    ✓ Paper trading validates signal generation without errors
  ║    ✓ Risk management constraints respected
  ║    ✓ All edge cases handled gracefully
  ║
  ║ 3. If approved for production:
  ║    - Update live config to enable: debit_spread.enabled: true
  ║    - Set conservative allocation initially: allocation: 0.2 (20%)
  ║    - Monitor first 10 trades closely for slippage and execution quality
  ║    - Compare live performance vs backtest after 30 days
  ║
  ║ 4. If not approved:
  ║    - Document reasons in report
  ║    - Identify improvements for next iteration
  ║    - Consider alternative strategies (calendar spreads, PMCC)
  ║
  ║ Reply "✅ Recommendations documented" when analysis complete
  ```

**🏁 MILESTONE: Release Ready**
*Use Task tool with commit-changes agent to commit: "Finalize debit spread feature - documentation and deployment recommendations"*

## AI-Assisted Development Time Estimation *(Claude Code + Human Review)*

> **⚠️ ESTIMATION BASIS**: These estimates assume development with Claude Code (AI) executing implementation tasks with human review and guidance. Times reflect AI execution + human review cycles, not manual coding.

### Phase-by-Phase Review Time
**Setup & Configuration (S001-S003)**: 30-45 minutes
- *AI creates YAML config quickly, human reviews parameter values and structure*

**Data Layer (S004-S009)**: 3-4 hours
- *AI implements strategy class and utilities with tests, human validates trading logic and statistical methods*
- *Most complex phase - strategy signal generation logic requires careful review*

**Service Layer (S010-S015)**: 2-3 hours
- *AI handles integration and slippage model updates, human validates risk management and backtest enhancements*

**CLI & Output (S016-S020)**: 1.5-2 hours
- *AI creates CLI commands and Rich formatting, human reviews output clarity and usability*

**Integration & Quality (S021-S024)**: 1-2 hours
- *AI runs automated tests and validation, human reviews test results and fixes any issues*

**Manual Testing (S025-S028)**: 3-5 hours
- *Human-intensive phase: running backtests, comparing strategies, validating paper trading*

**Release Preparation (S029-S032)**: 1-2 hours
- *AI updates documentation, human reviews recommendations and creates final report*

### Knowledge Gap Risk Factors
**🟢 Low Risk** (Well-documented Python libraries): Minimal correction cycles expected
- **scipy, pandas, numpy**: Excellent documentation, stable APIs
- **alpaca-py**: Good documentation with examples
- **Project architecture**: Well-established BaseStrategy pattern

**🟡 Medium Risk** (Trading strategy implementation): Some refinement iterations likely
- **Options Greeks calculations**: May need iteration for accuracy
- **Delta selection logic**: Refinement based on backtest results
- **Signal generation timing**: May require adjustment

**API Documentation Quality Impact**:
- **Excellent docs** (Python stdlib, scipy, pandas): ~10% additional review time
- **Good docs** (alpaca-py, Rich): ~15% additional review time
- **Trading domain knowledge**: ~20% additional review time for validation

### Total Estimated Review Time
**Core Development**: 12-16 hours (AI implementation + human review)
**Risk-Adjusted Time**: 14-19 hours (with trading logic refinements)
**Manual Testing Allocation**: 3-5 hours (backtesting and validation)

**Total Project Time**: 17-24 hours spread across multiple sessions

> **💡 TIME COMPOSITION**:
> - AI Implementation: ~20% (Claude Code executes Python quickly)
> - Human Review: ~35% (validating trading logic and statistical methods)
> - Correction Cycles: ~20% (strategy refinements based on backtest results)
> - Manual Testing: ~25% (backtesting, comparison, paper trading validation)

## Implementation Structure *(AI guidance)*

### Task Numbering Convention
- **Format**: `S###` with sequential numbering (S001, S002, S003...)
- **Parallel Markers**: `[P]` for tasks that can run concurrently
- **Dependencies**: Clear prerequisite task references
- **File Paths**: Specific target files for each implementation task

### Progress Tracking & Session Continuity
- **This file is the progress tracker** - Check off tasks as `[x]` when complete
- **Sessions are resumable** - New sessions read this file to see what's done
- **Token limits don't matter** - Work can span multiple sessions seamlessly
- **Never rush to completion** - Take the time each step needs for quality
- **TodoWrite is temporary** - Only this file persists across sessions
- **Quality is paramount** - Shortcuts and speed optimizations are forbidden

### Parallel Execution Rules
- **Different files** = `[P]` parallel safe
- **Same file modifications** = Sequential only
- **Independent components** = `[P]` parallel safe
- **Shared resources** = Sequential only
- **Tests with implementation** = Can run `[P]` parallel

### Manual User Action Format
For complex Xcode operations (target creation, scheme setup), use standardized format:
```
═══════════════════════════════════════════════════
║ 🎯 MANUAL XCODE ACTION REQUIRED
═══════════════════════════════════════════════════
║
║ [Step-by-step Xcode UI instructions]
║ [Specific menu paths and actions]
║
║ Reply "Done" when completed to continue.
```

### Quality Integration
*Built into implementation phases, not separate agent tasks*

- **Code Standards**: Follow Context/Guidelines patterns throughout
- **Error Handling**: Apply ErrorKit patterns during service implementation
- **UI Guidelines**: Follow SwiftUI patterns during UI implementation
- **Testing Coverage**: Include test tasks for each implementation phase
- **Platform Compliance**: Consider iOS/macOS requirements in each phase

## Dependency Analysis *(AI generated)*

### Critical Path
**Longest dependency chain (sequential tasks only)**:
S001 → S004 → S007 → S012 → S018 → S021 → S024 → S025 → S026 → S031 → S032

**Estimated critical path time**: ~10-14 hours (serial execution)

**Breakdown**:
1. S001 (Config) → S004 (Tests) → S007 (Strategy) [~2.5 hours]
2. S007 → S012 (Registration) → S018 (CLI) [~1.5 hours]
3. S018 → S021 (Test suite) → S024 (Build) [~1 hour]
4. S024 → S025 (Backtest) → S026 (Comparison) [~4 hours]
5. S026 → S031 (Report) → S032 (Recommendations) [~1.5 hours]

### Parallel Opportunities
**High parallelism phases** (AI can work on multiple files simultaneously):

**Phase 2 (Data Layer)**:
- [P] S005, S006 can run parallel with S004 (different test files)
- [P] S008, S009 can run parallel with S007 after their tests complete (different utility files)

**Phase 3 (Service Layer)**:
- [P] S010, S011 can run parallel (different test files)
- [P] S014 can run parallel with S013 (different code sections in engine.py)

**Phase 4 (CLI)**:
- [P] S016, S017 can run parallel (different test files)
- [P] S019, S020 can run parallel with S018 (different output formatter files)

**Phase 5 (Validation)**:
- [P] S021, S022, S023 can all run parallel (independent validation tasks)

**Phase 7 (Documentation)**:
- [P] S029, S030 can run parallel (different documentation files)

**Parallelism benefit**: Can reduce total wall-clock time by ~30-40% if AI works on parallel tasks simultaneously

### Python/Trading-Specific Dependencies
**Python Environment**:
- Python 3.11+ (project requirement)
- UV package manager (already installed)
- No new dependencies required (all libraries already in pyproject.toml)

**Trading Domain**:
- BaseStrategy architecture (established pattern)
- Alpaca API (already integrated)
- Historical data availability (Feb 2024+ from Alpaca)
- Synthetic data generator (fallback for pre-Feb 2024)

**External Services**:
- Alpaca API credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- No rate limits for strategy implementation (only affects backtesting volume)

## Completion Verification *(mandatory)*

### Implementation Completeness
- [x] All user scenarios from Spec.md have corresponding implementation tasks?
  - ✓ Low-capital strategy research (debit spreads selected): S007
  - ✓ Strategy implementation following BaseStrategy: S007
  - ✓ Comprehensive backtesting over 6+ months: S025
  - ✓ Performance comparison with statistical significance: S026, S009
  - ✓ All 10 functional requirements (FR-001 to FR-010) mapped to tasks

- [x] All architectural components from Tech.md have creation/modification tasks?
  - ✓ DebitSpreadStrategy class: S007
  - ✓ RegimeClassifier utility: S008
  - ✓ StrategyComparator utility: S009
  - ✓ Engine registration: S012
  - ✓ ORATS slippage model: S013
  - ✓ Portfolio Greeks tracking: S014
  - ✓ CLI comparison command: S018
  - ✓ Output formatters: S019, S020

- [x] Error handling and edge cases covered in task breakdown?
  - ✓ Insufficient capital scenario: S028
  - ✓ Low IV environment handling: S028
  - ✓ Extreme volatility handling: S028
  - ✓ Illiquid underlyings: S028
  - ✓ Conflicting signals: S028
  - ✓ Risk management validation: S015

- [x] Performance requirements addressed in implementation plan?
  - ✓ ORATS slippage model for realistic execution: S013
  - ✓ Statistical comparison with Mann-Whitney U: S009
  - ✓ Capital efficiency metrics: S009, S019
  - ✓ Regime-specific performance: S008, S020
  - ✓ Portfolio Greeks tracking: S014

- [x] Python/Trading-specific requirements integrated throughout phases?
  - ✓ Type checking with mypy: S022
  - ✓ Code linting with ruff: S023
  - ✓ Pytest test coverage: S021
  - ✓ Alpaca API integration: S007, S012
  - ✓ Risk management constraints: S015

### Quality Standards
- [x] Each task specifies exact file paths and dependencies?
  - ✓ All S001-S032 tasks include specific file paths
  - ✓ Dependencies clearly documented for each task
  - ✓ Line numbers referenced where applicable (e.g., engine.py:282)

- [x] Parallel markers `[P]` applied correctly for independent tasks?
  - ✓ Test files can run parallel (S004, S005, S006)
  - ✓ Utility implementations parallel (S008, S009)
  - ✓ Output formatters parallel (S019, S020)
  - ✓ Documentation tasks parallel (S029, S030)
  - ✓ Validation tasks parallel (S021, S022, S023)

- [x] Test tasks included for all major implementation components?
  - ✓ DebitSpreadStrategy tests: S004
  - ✓ RegimeClassifier tests: S005
  - ✓ StrategyComparator tests: S006
  - ✓ Slippage model tests: S011
  - ✓ Integration tests: S010
  - ✓ CLI tests: S016, S017
  - ✓ Complete test suite execution: S021

- [x] Code standards and guidelines referenced throughout plan?
  - ✓ Follow VerticalSpreadStrategy pattern: S007
  - ✓ BaseStrategy architecture: S007
  - ✓ Type hints (mypy strict): S022
  - ✓ Line length 100 chars (ruff): S023
  - ✓ TDD approach: Phase 2 structure

- [x] No implementation details that should be in tech plan?
  - ✓ Tasks reference Tech.md for implementation details
  - ✓ Configuration structures documented in Tech.md
  - ✓ Signal metadata structure in Tech.md
  - ✓ Steps.md focuses on task breakdown only

### Release Readiness
- [x] Trading system compliance considerations addressed?
  - ✓ Risk management validation: S015
  - ✓ Paper trading validation before production: S027
  - ✓ Edge case testing: S028
  - ✓ Production deployment criteria: S032
  - ✓ Phased rollout recommendations: S032

- [x] Documentation and release preparation tasks included?
  - ✓ CLAUDE.md updates: S029
  - ✓ Context.md updates: S030
  - ✓ Backtest comparison report: S031
  - ✓ Production deployment recommendations: S032

- [x] Feature branch ready for systematic development execution?
  - ✓ Branch: feature/001-low-capital-strategy (already exists)
  - ✓ All planning phases complete (Spec.md, Tech.md, Steps.md)
  - ✓ Clear task enumeration S001-S032
  - ✓ Milestones defined with commit guidance

- [x] All milestones defined with appropriate commit guidance?
  - ✓ Foundation Setup: After S003
  - ✓ Strategy Implementation Complete: After S009
  - ✓ Service Integration Complete: After S015
  - ✓ CLI Enhancement Complete: After S020
  - ✓ Automated Validation Complete: After S024
  - ✓ User Testing Complete: After S028
  - ✓ Release Ready: After S032
  - ✓ All milestones specify "Use Task tool with commit-changes agent"

---

**Next Phase**: After implementation steps are reviewed and approved, proceed to `/ctxk:impl:start-working` to begin systematic development execution.

---