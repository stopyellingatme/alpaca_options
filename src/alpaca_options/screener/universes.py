"""Symbol universes for screening.

Provides pre-defined lists of symbols commonly used for options trading.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class UniverseType(Enum):
    """Types of symbol universes available."""

    SP500 = "sp500"
    NASDAQ100 = "nasdaq100"
    OPTIONS_FRIENDLY = "options_friendly"
    HIGH_VOLUME_OPTIONS = "high_volume_options"
    EXPANDED_OPTIONS = "expanded_options"  # Phase 3 Enhancement: ~300 symbols
    ETFS = "etfs"
    SECTOR_ETFS = "sector_etfs"
    CUSTOM = "custom"


@dataclass
class SymbolUniverse:
    """A universe of symbols for screening."""

    name: str
    universe_type: UniverseType
    symbols: list[str]
    description: str = ""

    def __len__(self) -> int:
        return len(self.symbols)

    def __iter__(self):
        return iter(self.symbols)


# Major ETFs with high options liquidity
MAJOR_ETFS = [
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "IWM",   # Russell 2000
    "DIA",   # Dow Jones
    "EEM",   # Emerging Markets
    "EFA",   # EAFE (Europe, Australasia, Far East)
    "GLD",   # Gold
    "SLV",   # Silver
    "TLT",   # 20+ Year Treasury
    "HYG",   # High Yield Corporate Bond
    "XLF",   # Financial Sector
    "XLE",   # Energy Sector
    "XLK",   # Technology Sector
    "XLV",   # Healthcare Sector
    "XLI",   # Industrial Sector
    "XLP",   # Consumer Staples
    "XLY",   # Consumer Discretionary
    "XLU",   # Utilities
    "XLB",   # Materials
    "XLRE",  # Real Estate
    "VXX",   # VIX Short-Term Futures
    "USO",   # Oil
    "UNG",   # Natural Gas
    "FXI",   # China Large-Cap
    "ARKK",  # ARK Innovation
]

# Sector ETFs
SECTOR_ETFS = [
    "XLF",   # Financial
    "XLE",   # Energy
    "XLK",   # Technology
    "XLV",   # Healthcare
    "XLI",   # Industrial
    "XLP",   # Consumer Staples
    "XLY",   # Consumer Discretionary
    "XLU",   # Utilities
    "XLB",   # Materials
    "XLRE",  # Real Estate
    "XLC",   # Communication Services
    "SMH",   # Semiconductors
    "XBI",   # Biotech
    "XOP",   # Oil & Gas Exploration
    "XHB",   # Homebuilders
    "XRT",   # Retail
    "KRE",   # Regional Banks
    "IBB",   # Biotech (iShares)
    "IYR",   # Real Estate (iShares)
    "ITB",   # Home Construction
]

# High-volume options stocks - consistently among most active
HIGH_VOLUME_OPTIONS_STOCKS = [
    # Mega-cap tech
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "AMZN",  # Amazon
    "GOOGL", # Alphabet
    "META",  # Meta
    "NVDA",  # Nvidia
    "TSLA",  # Tesla
    # Other high-volume
    "AMD",   # AMD
    "NFLX",  # Netflix
    "BABA",  # Alibaba
    "BA",    # Boeing
    "DIS",   # Disney
    "JPM",   # JPMorgan
    "BAC",   # Bank of America
    "C",     # Citigroup
    "WFC",   # Wells Fargo
    "GS",    # Goldman Sachs
    "MS",    # Morgan Stanley
    "V",     # Visa
    "MA",    # Mastercard
    "PYPL",  # PayPal
    "SQ",    # Block (Square)
    "COIN",  # Coinbase
    "SHOP",  # Shopify
    "UBER",  # Uber
    "LYFT",  # Lyft
    "ABNB",  # Airbnb
    "SNOW",  # Snowflake
    "PLTR",  # Palantir
    "RIVN",  # Rivian
    "LCID",  # Lucid
    "NIO",   # NIO
    "F",     # Ford
    "GM",    # General Motors
    "XOM",   # ExxonMobil
    "CVX",   # Chevron
    "COP",   # ConocoPhillips
    "OXY",   # Occidental
    "PFE",   # Pfizer
    "MRNA",  # Moderna
    "JNJ",   # Johnson & Johnson
    "UNH",   # UnitedHealth
    "MRK",   # Merck
    "ABBV",  # AbbVie
    "LLY",   # Eli Lilly
    "WMT",   # Walmart
    "TGT",   # Target
    "COST",  # Costco
    "HD",    # Home Depot
    "LOW",   # Lowe's
    "NKE",   # Nike
    "SBUX",  # Starbucks
    "MCD",   # McDonald's
    "CMG",   # Chipotle
    "CRM",   # Salesforce
    "ORCL",  # Oracle
    "IBM",   # IBM
    "INTC",  # Intel
    "MU",    # Micron
    "QCOM",  # Qualcomm
    "AVGO",  # Broadcom
    "TXN",   # Texas Instruments
    "AMAT",  # Applied Materials
    "LRCX",  # Lam Research
    "ASML",  # ASML
    "TSM",   # Taiwan Semiconductor
    "T",     # AT&T
    "VZ",    # Verizon
    "TMUS",  # T-Mobile
    "CMCSA", # Comcast
    "CHTR",  # Charter
    "NFLX",  # Netflix
    "ROKU",  # Roku
    "SPOT",  # Spotify
    "ZM",    # Zoom
    "DOCU",  # DocuSign
    "CRWD",  # CrowdStrike
    "NET",   # Cloudflare
    "DDOG",  # Datadog
    "ZS",    # Zscaler
    "PANW",  # Palo Alto Networks
    "FTNT",  # Fortinet
]

# Nasdaq 100 components (top tech-heavy index)
NASDAQ_100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR", "CDNS",
    "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX",
    "CTAS", "CTSH", "DDOG", "DLTR", "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT",
    "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN", "INTC", "INTU",
    "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP", "MDB",
    "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL", "MSFT", "MU", "NFLX", "NVDA",
    "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PYPL",
    "QCOM", "REGN", "ROP", "ROST", "SBUX", "SIRI", "SMCI", "SNPS", "TEAM", "TMUS",
    "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBA", "WBD", "WDAY", "XEL", "ZS",
]

# S&P 500 - abbreviated list of most liquid (full list would be 500)
SP500_LIQUID = [
    # Top 100 most liquid S&P 500 components
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "COST", "KO", "AVGO", "WMT", "MCD", "CSCO", "TMO", "ACN", "ABT",
    "CRM", "DHR", "BAC", "NKE", "PFE", "CMCSA", "VZ", "ADBE", "NFLX", "ORCL",
    "TXN", "PM", "INTC", "AMD", "UPS", "COP", "NEE", "RTX", "HON", "QCOM",
    "UNP", "LOW", "SPGI", "BA", "CAT", "ELV", "AMAT", "DE", "IBM", "GS",
    "AMGN", "SBUX", "MS", "GE", "MDT", "BLK", "ISRG", "AXP", "INTU", "BKNG",
    "PLD", "GILD", "ADP", "VRTX", "TJX", "SYK", "ADI", "MDLZ", "CVS", "MMC",
    "C", "TMUS", "LRCX", "REGN", "MO", "CB", "CI", "ZTS", "SO", "DUK",
    "BDX", "CME", "EOG", "PNC", "SCHW", "CL", "ITW", "NOC", "BSX", "WM",
]

# Options-friendly stocks: High liquidity, reasonable prices, tight spreads
OPTIONS_FRIENDLY = list(set(
    MAJOR_ETFS +
    HIGH_VOLUME_OPTIONS_STOCKS[:50]  # Top 50 most liquid options stocks
))

# Expanded universe for Phase 3 (~300 symbols)
# Combines multiple sources while respecting API limits
EXPANDED_OPTIONS = list(set(
    MAJOR_ETFS +                      # 25 ETFs
    SECTOR_ETFS +                     # 20 sector ETFs
    HIGH_VOLUME_OPTIONS_STOCKS +      # 181 high-volume stocks
    NASDAQ_100[:50] +                 # Top 50 Nasdaq 100 (overlap filtered)
    SP500_LIQUID[:50]                 # Top 50 S&P 500 (overlap filtered)
))

# Tiered priority for scanning (Phase 3 Enhancement)
# Tier 1: Highest priority - scan every 5 minutes
TIER_1_PRIORITY = [
    # Major indexes and most liquid ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Mega-cap tech with highest options volume
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    # High-volatility tickers
    "AMD", "PLTR", "COIN",
]

# Tier 2: Medium priority - scan every 10 minutes
TIER_2_PRIORITY = [
    # Sector ETFs
    *SECTOR_ETFS,
    # Next tier high-volume stocks
    "NFLX", "BABA", "BA", "DIS", "JPM", "BAC", "GS", "V", "MA",
    "PYPL", "SQ", "SHOP", "UBER", "ABNB", "SNOW", "RIVN",
]

# Tier 3: Low priority - scan every 15 minutes
# Everything else in EXPANDED_OPTIONS that's not in Tier 1 or 2


def get_sp500_symbols() -> list[str]:
    """Get S&P 500 symbols (most liquid subset)."""
    return SP500_LIQUID.copy()


def get_nasdaq100_symbols() -> list[str]:
    """Get Nasdaq 100 symbols."""
    return NASDAQ_100.copy()


def get_options_friendly_symbols() -> list[str]:
    """Get symbols known for high options liquidity."""
    return OPTIONS_FRIENDLY.copy()


def get_sector_etfs() -> list[str]:
    """Get sector ETF symbols."""
    return SECTOR_ETFS.copy()


def get_major_etfs() -> list[str]:
    """Get major ETF symbols."""
    return MAJOR_ETFS.copy()


def get_expanded_options() -> list[str]:
    """Get expanded options universe (~300 symbols).

    Phase 3 Enhancement: Larger symbol set for comprehensive market coverage.
    """
    return EXPANDED_OPTIONS.copy()


def get_tier_1_symbols() -> list[str]:
    """Get Tier 1 (highest priority) symbols.

    Scan frequency: Every 5 minutes.
    """
    return TIER_1_PRIORITY.copy()


def get_tier_2_symbols() -> list[str]:
    """Get Tier 2 (medium priority) symbols.

    Scan frequency: Every 10 minutes.
    """
    return TIER_2_PRIORITY.copy()


def get_tier_3_symbols() -> list[str]:
    """Get Tier 3 (low priority) symbols.

    Scan frequency: Every 15 minutes.
    Returns symbols in EXPANDED_OPTIONS not in Tier 1 or 2.
    """
    tier1_set = set(TIER_1_PRIORITY)
    tier2_set = set(TIER_2_PRIORITY)

    tier3 = [s for s in EXPANDED_OPTIONS if s not in tier1_set and s not in tier2_set]
    return tier3


def get_symbol_tier(symbol: str) -> int:
    """Get the priority tier for a symbol.

    Args:
        symbol: Stock symbol.

    Returns:
        Tier number (1, 2, or 3). Returns 3 if not found.
    """
    if symbol in TIER_1_PRIORITY:
        return 1
    elif symbol in TIER_2_PRIORITY:
        return 2
    else:
        return 3


def get_universe(universe_type: UniverseType) -> SymbolUniverse:
    """Get a symbol universe by type.

    Args:
        universe_type: Type of universe to retrieve.

    Returns:
        SymbolUniverse with symbols and metadata.
    """
    universes = {
        UniverseType.SP500: SymbolUniverse(
            name="S&P 500 Liquid",
            universe_type=UniverseType.SP500,
            symbols=get_sp500_symbols(),
            description="Most liquid S&P 500 components",
        ),
        UniverseType.NASDAQ100: SymbolUniverse(
            name="Nasdaq 100",
            universe_type=UniverseType.NASDAQ100,
            symbols=get_nasdaq100_symbols(),
            description="Nasdaq 100 index components",
        ),
        UniverseType.OPTIONS_FRIENDLY: SymbolUniverse(
            name="Options Friendly",
            universe_type=UniverseType.OPTIONS_FRIENDLY,
            symbols=get_options_friendly_symbols(),
            description="High liquidity options stocks and ETFs",
        ),
        UniverseType.HIGH_VOLUME_OPTIONS: SymbolUniverse(
            name="High Volume Options",
            universe_type=UniverseType.HIGH_VOLUME_OPTIONS,
            symbols=HIGH_VOLUME_OPTIONS_STOCKS,
            description="Stocks with highest options trading volume",
        ),
        UniverseType.EXPANDED_OPTIONS: SymbolUniverse(
            name="Expanded Options Universe",
            universe_type=UniverseType.EXPANDED_OPTIONS,
            symbols=get_expanded_options(),
            description="Phase 3 Enhancement: ~300 symbols with tiered scanning",
        ),
        UniverseType.ETFS: SymbolUniverse(
            name="Major ETFs",
            universe_type=UniverseType.ETFS,
            symbols=get_major_etfs(),
            description="Major ETFs across asset classes",
        ),
        UniverseType.SECTOR_ETFS: SymbolUniverse(
            name="Sector ETFs",
            universe_type=UniverseType.SECTOR_ETFS,
            symbols=get_sector_etfs(),
            description="Sector-specific ETFs",
        ),
    }

    if universe_type not in universes:
        raise ValueError(f"Unknown universe type: {universe_type}")

    return universes[universe_type]


def create_custom_universe(
    name: str,
    symbols: list[str],
    description: str = "",
) -> SymbolUniverse:
    """Create a custom symbol universe.

    Args:
        name: Name for the universe.
        symbols: List of symbols.
        description: Optional description.

    Returns:
        Custom SymbolUniverse.
    """
    return SymbolUniverse(
        name=name,
        universe_type=UniverseType.CUSTOM,
        symbols=symbols,
        description=description,
    )


def merge_universes(*universes: SymbolUniverse) -> SymbolUniverse:
    """Merge multiple universes into one, removing duplicates.

    Args:
        *universes: Universes to merge.

    Returns:
        Merged SymbolUniverse with unique symbols.
    """
    all_symbols: set[str] = set()
    names: list[str] = []

    for universe in universes:
        all_symbols.update(universe.symbols)
        names.append(universe.name)

    return SymbolUniverse(
        name=" + ".join(names),
        universe_type=UniverseType.CUSTOM,
        symbols=sorted(list(all_symbols)),
        description=f"Merged universe from: {', '.join(names)}",
    )
