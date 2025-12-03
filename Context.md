# Project Context: Alpaca Options Trading Bot

## Project Overview

- **Version**: ContextKit 0.2.0
- **Setup Date**: 2025-12-03
- **Components**: 1 component (single Python application)
- **Workspace**: None (standalone project)
- **Primary Tech Stack**: Python 3.11+, asyncio, Alpaca API
- **Development Guidelines**: None (ContextKit guidelines are Swift-focused)

## Component Architecture

**Project Structure**:

```
📁 alpaca_options
└── 🐍 alpaca-options-bot (Python Package) - Automated options trading with backtesting - Python 3.11+, UV, asyncio - ./
```

**Component Summary**:
- **1 Python package** - Python 3.11+, asyncio, Alpaca API integration
- **Dependencies**: 17 core dependencies + 8 dev dependencies
- **Package Manager**: UV (fast, reliable Python package management)

---

## Component Details

### alpaca-options-bot - Python Package

**Location**: `./`
**Purpose**: Automated options trading bot with Alpaca integration, backtesting framework, and terminal UI dashboard
**Tech Stack**: Python 3.11+, asyncio, Alpaca-py, Rich, Pandas, Pydantic

**File Structure**:
```
alpaca_options/
├── src/alpaca_options/           # Main package
│   ├── alpaca/                   # Alpaca API integration
│   │   ├── client.py             # Main Alpaca client wrapper
│   │   ├── trading.py            # Order execution and management
│   │   ├── data.py               # Market data streaming
│   │   └── options.py            # Options-specific API calls
│   ├── backtesting/              # Backtesting framework
│   │   ├── engine.py             # Backtest engine
│   │   ├── data_loader.py        # Historical data loading
│   │   └── alpaca_options_fetcher.py  # Historical options data
│   ├── core/                     # Core engine components
│   │   ├── engine.py             # Live trading engine orchestrator
│   │   ├── config.py             # Configuration loading
│   │   ├── events.py             # Event bus
│   │   └── capital_manager.py    # Capital tier management
│   ├── risk/                     # Risk management
│   │   └── manager.py            # Risk checks, position sizing
│   ├── strategies/               # Trading strategies
│   │   ├── base.py               # BaseStrategy ABC
│   │   ├── debit_spread.py       # Debit spreads (LOW tier, $1.5k+)
│   │   ├── vertical_spread.py    # Credit spreads (LOW tier, $2k+)
│   │   ├── iron_condor.py        # Iron condors (MEDIUM tier)
│   │   └── wheel.py              # Wheel strategy (HIGH tier)
│   ├── screener/                 # Market screening
│   │   ├── scanner.py            # Market scanner
│   │   ├── filters.py            # Filtering criteria
│   │   └── technical.py          # Technical indicators
│   ├── ui/                       # Terminal interface
│   │   └── dashboard.py          # Rich terminal UI
│   └── cli.py                    # Typer CLI entry point
├── tests/                        # Test suite
│   └── test_strategies/          # Strategy tests
├── scripts/                      # Utility scripts
│   ├── comprehensive_backtest.py # Detailed backtesting
│   └── run_paper_trading.py      # Paper trading runner
├── config/                       # Configuration files
│   ├── default.yaml              # Default configuration
│   └── paper_qqq.yaml            # Paper trading config
├── pyproject.toml                # Project configuration
└── uv.lock                       # UV lock file
```

**Dependencies** (from pyproject.toml):

Core:
- `alpaca-py>=0.21.0` - Alpaca trading API client
- `rich>=13.7.0` - Terminal UI and formatting
- `pandas>=2.1.0` - Data manipulation
- `numpy>=1.26.0` - Numerical computing
- `pydantic>=2.5.0` - Data validation
- `aiohttp>=3.9.0` - Async HTTP client
- `scipy>=1.11.0` - Scientific computing (Greeks)
- `typer>=0.9.0` - CLI framework
- `pyyaml>=6.0.0` - Configuration parsing

Dev:
- `pytest>=7.4.0` - Testing framework
- `pytest-asyncio>=0.23.0` - Async test support
- `mypy>=1.8.0` - Type checking
- `ruff>=0.1.0` - Linting

**Development Commands**:
```bash
# Build/Install (validated during setup)
uv sync

# Run CLI
uv run alpaca-options --help

# Run paper trading
uv run alpaca-options run --paper

# Run backtest
uv run alpaca-options backtest --strategy vertical_spread --symbol QQQ --capital 5000

# Run comprehensive backtest script
uv run python scripts/comprehensive_backtest.py

# Test (validated during setup)
uv run pytest tests/

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
```

**Code Style** (detected from pyproject.toml):
- Line length: 100 characters
- Target Python: 3.11
- Linter: Ruff with pycodestyle, flakes, isort, bugbear
- Formatter: Black compatible
- Type checking: mypy with strict mode

---

## Development Environment

**Requirements** (from analysis):
- Python 3.11 or 3.12
- UV package manager
- Alpaca API credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)

**Build Tools** (detected):
- UV (fast Python package manager)
- Hatchling (build backend)
- pytest (testing)
- mypy (type checking)
- ruff (linting)

**Environment Variables**:
```bash
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
```

## Development Guidelines

**Applied Guidelines**: None (Python project, ContextKit guidelines are Swift-focused)

**Python Best Practices**:
- Use async/await for I/O operations
- Type hints on all functions
- Pydantic for data validation
- Configuration via YAML files
- Structured logging with Rich

## Constitutional Principles

**Core Principles**:
- ✅ Code maintainability (readable, testable, documented code)
- ✅ Type safety (strict mypy checking)
- ✅ Test coverage (pytest with coverage reporting)
- ✅ Risk management (position limits, Greeks constraints)
- ✅ Paper trading validation (test strategies before live trading)

**Workspace Inheritance**: None - using project defaults

## ContextKit Workflow

**Systematic Feature Development**:
- `/ctxk:plan:1-spec` - Create business requirements specification
- `/ctxk:plan:2-research-tech` - Define technical research and architecture
- `/ctxk:plan:3-steps` - Break down into executable implementation tasks

**Development Execution**:
- `/ctxk:impl:start-working` - Continue development within feature branch
- `/ctxk:impl:commit-changes` - Auto-format code and commit with intelligent messages

**Quality Assurance**: Automated agents validate code quality during development
**Project Management**: All validated build/test commands documented above for immediate use

## Development Automation

**Quality Agents Available**:
- `build-project` - Execute builds with validation
- `run-test-suite` - Execute complete test suite
- `run-specific-test` - Execute specific test with focused analysis

## Configuration Hierarchy

**Inheritance**: Project-level only (no workspace)

**Project Configuration**:
- `config/default.yaml` - Default trading configuration
- `config/paper_qqq.yaml` - Paper trading configuration for QQQ
- `pyproject.toml` - Python project configuration

**Override Precedence**: Config files override defaults

---
*Generated by ContextKit with comprehensive component analysis. Manual edits preserved during updates.*
