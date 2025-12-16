"""SEC Filings Analysis Module.

This module provides access to SEC filings data (10-K, 10-Q, 8-K) for analyzing
company fundamentals, risk factors, financial health, and bankruptcy risk to improve trading decisions.

Architecture:
    - SECFilingsProvider (ABC): Multi-provider abstraction for extensibility
    - EdgarToolsProvider: Primary provider using EdgarTools library
    - SECFilingsAnalyzer: Main interface with caching and analysis

Usage:
    analyzer = SECFilingsAnalyzer(cache_ttl_days=7)

    # Get risk score
    risk_score = analyzer.get_risk_score("AAPL")

    # Get financial health
    health = analyzer.get_financial_health("AAPL")

    # Get cash flow health and bankruptcy risk
    cash_flow = analyzer.get_cash_flow_health("AAPL")

    # Check if symbol has high risk
    if analyzer.has_high_risk("AAPL", threshold=7.0):
        logger.info("High risk detected, avoiding trade")

    # Check for bankruptcy risk
    if analyzer.has_bankruptcy_risk("AAPL", threshold=7.0):
        logger.info("Bankruptcy risk detected, avoiding trade")
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SECFilingsData:
    """Container for SEC filings data."""

    def __init__(
        self,
        symbol: str,
        filing_type: str,
        filing_date: datetime,
        business: Optional[str] = None,
        risk_factors: Optional[str] = None,
        mda: Optional[str] = None,
    ):
        """Initialize SEC filings data.

        Args:
            symbol: Stock ticker symbol
            filing_type: Type of filing (10-K, 10-Q, 8-K)
            filing_date: Date of filing
            business: Business description section
            risk_factors: Risk factors section
            mda: Management discussion and analysis section
        """
        self.symbol = symbol
        self.filing_type = filing_type
        self.filing_date = filing_date
        self.business = business
        self.risk_factors = risk_factors
        self.mda = mda


class RiskScore:
    """Container for risk assessment results."""

    def __init__(
        self,
        symbol: str,
        overall_score: float,
        risk_factor_count: int,
        has_legal_proceedings: bool,
        has_regulatory_risks: bool,
        filing_date: datetime,
    ):
        """Initialize risk score.

        Args:
            symbol: Stock ticker symbol
            overall_score: Overall risk score (0-10, higher = riskier)
            risk_factor_count: Number of risk factors identified
            has_legal_proceedings: Whether company has active legal proceedings
            has_regulatory_risks: Whether company faces regulatory risks
            filing_date: Date of filing used for analysis
        """
        self.symbol = symbol
        self.overall_score = overall_score
        self.risk_factor_count = risk_factor_count
        self.has_legal_proceedings = has_legal_proceedings
        self.has_regulatory_risks = has_regulatory_risks
        self.filing_date = filing_date

    def __repr__(self) -> str:
        return (
            f"RiskScore(symbol={self.symbol}, score={self.overall_score:.1f}, "
            f"factors={self.risk_factor_count}, legal={self.has_legal_proceedings}, "
            f"regulatory={self.has_regulatory_risks})"
        )


class FinancialHealth:
    """Container for financial health metrics."""

    def __init__(
        self,
        symbol: str,
        health_score: float,
        has_balance_sheet: bool,
        has_income_statement: bool,
        filing_date: datetime,
        notes: Optional[str] = None,
    ):
        """Initialize financial health.

        Args:
            symbol: Stock ticker symbol
            health_score: Overall health score (0-10, higher = healthier)
            has_balance_sheet: Whether balance sheet data is available
            has_income_statement: Whether income statement data is available
            filing_date: Date of filing used for analysis
            notes: Additional notes about financial health
        """
        self.symbol = symbol
        self.health_score = health_score
        self.has_balance_sheet = has_balance_sheet
        self.has_income_statement = has_income_statement
        self.filing_date = filing_date
        self.notes = notes

    def __repr__(self) -> str:
        return (
            f"FinancialHealth(symbol={self.symbol}, score={self.health_score:.1f}, "
            f"bs={self.has_balance_sheet}, is={self.has_income_statement})"
        )


class InsiderSentiment:
    """Container for insider trading sentiment analysis."""

    def __init__(
        self,
        symbol: str,
        sentiment_score: float,
        buy_count: int,
        sell_count: int,
        buy_value: float,
        sell_value: float,
        analysis_period_days: int,
    ):
        """Initialize insider sentiment.

        Args:
            symbol: Stock ticker symbol
            sentiment_score: Sentiment score (-1.0 to +1.0, negative = selling, positive = buying)
            buy_count: Number of insider buy transactions
            sell_count: Number of insider sell transactions
            buy_value: Total value of insider buys
            sell_value: Total value of insider sells
            analysis_period_days: Number of days analyzed
        """
        self.symbol = symbol
        self.sentiment_score = sentiment_score
        self.buy_count = buy_count
        self.sell_count = sell_count
        self.buy_value = buy_value
        self.sell_value = sell_value
        self.analysis_period_days = analysis_period_days

    def __repr__(self) -> str:
        return (
            f"InsiderSentiment(symbol={self.symbol}, score={self.sentiment_score:.2f}, "
            f"buys={self.buy_count}, sells={self.sell_count})"
        )


class CashFlowHealth:
    """Container for cash flow and bankruptcy risk analysis."""

    def __init__(
        self,
        symbol: str,
        has_negative_ocf: bool,
        ocf_quarters_negative: int,
        has_high_debt: bool,
        has_low_liquidity: bool,
        bankruptcy_risk_score: float,
        filing_date: datetime,
    ):
        """Initialize cash flow health metrics.

        Args:
            symbol: Stock ticker symbol
            has_negative_ocf: Whether operating cash flow is currently negative
            ocf_quarters_negative: Number of consecutive quarters with negative OCF
            has_high_debt: Whether debt/equity ratio exceeds 2.0
            has_low_liquidity: Whether current ratio is below 1.0
            bankruptcy_risk_score: Risk score from 0-10 (higher = more risk)
            filing_date: Date of filing used for analysis
        """
        self.symbol = symbol
        self.has_negative_ocf = has_negative_ocf
        self.ocf_quarters_negative = ocf_quarters_negative
        self.has_high_debt = has_high_debt
        self.has_low_liquidity = has_low_liquidity
        self.bankruptcy_risk_score = bankruptcy_risk_score
        self.filing_date = filing_date

    def __repr__(self) -> str:
        return (
            f"CashFlowHealth(symbol={self.symbol}, risk_score={self.bankruptcy_risk_score:.1f}, "
            f"neg_ocf={self.has_negative_ocf}, high_debt={self.has_high_debt}, "
            f"low_liquidity={self.has_low_liquidity})"
        )


class AuditorWarnings:
    """Container for auditor warning flags from SEC filings."""

    def __init__(
        self,
        symbol: str,
        has_going_concern: bool,
        has_material_weakness: bool,
        has_auditor_change: bool,
        has_restatement: bool,
        filing_date: datetime,
    ):
        """Initialize auditor warnings.

        Args:
            symbol: Stock ticker symbol
            has_going_concern: Whether auditor raised going concern warnings
            has_material_weakness: Whether material weakness in internal controls identified
            has_auditor_change: Whether company recently changed auditors
            has_restatement: Whether company restated financial results
            filing_date: Date of filing analyzed
        """
        self.symbol = symbol
        self.has_going_concern = has_going_concern
        self.has_material_weakness = has_material_weakness
        self.has_auditor_change = has_auditor_change
        self.has_restatement = has_restatement
        self.filing_date = filing_date

    @property
    def warning_count(self) -> int:
        """Total number of auditor warning flags."""
        return sum(
            [
                self.has_going_concern,
                self.has_material_weakness,
                self.has_auditor_change,
                self.has_restatement,
            ]
        )

    def has_critical_warnings(self) -> bool:
        """Check if company has critical auditor warnings.

        Returns:
            True if going concern OR material weakness detected, False otherwise
        """
        return self.has_going_concern or self.has_material_weakness

    def __repr__(self) -> str:
        return (
            f"AuditorWarnings(symbol={self.symbol}, warnings={self.warning_count}, "
            f"going_concern={self.has_going_concern}, material_weakness={self.has_material_weakness})"
        )


class InsiderActivity:
    """Analyzer for insider trading activity from Form 4 filings."""

    def __init__(self) -> None:
        """Initialize insider activity analyzer."""
        try:
            from edgar import Company

            self._Company = Company
            logger.info("InsiderActivity analyzer initialized")
        except ImportError:
            logger.error("edgartools library not installed. Run: uv add edgartools")
            raise

    def get_insider_sentiment(
        self, symbol: str, days: int = 90
    ) -> Optional[InsiderSentiment]:
        """Analyze Form 4 filings to calculate insider sentiment score.

        Args:
            symbol: Stock ticker symbol
            days: Number of days to analyze (default: 90)

        Returns:
            InsiderSentiment with score from -1.0 (heavy selling) to +1.0 (heavy buying)
        """
        try:
            company = self._Company(symbol)
            cutoff_date = datetime.now() - timedelta(days=days)

            # Get Form 4 filings (insider transactions)
            filings = company.get_filings(form="4")
            if not filings or len(filings) == 0:
                logger.debug(f"No Form 4 filings found for {symbol}")
                return None

            buy_count = 0
            sell_count = 0
            buy_value = 0.0
            sell_value = 0.0

            # Analyze each filing
            for filing in filings:
                if filing.filing_date < cutoff_date:
                    break  # Filings are sorted newest first

                try:
                    filing_obj = filing.obj()
                    if not hasattr(filing_obj, "transactions"):
                        continue

                    # Parse transactions
                    for txn in filing_obj.transactions:
                        if not hasattr(txn, "transaction_code"):
                            continue

                        # P = Purchase, S = Sale, M = Option Exercise
                        # Focus on P (purchase) and S (sale)
                        code = str(txn.transaction_code).upper()
                        shares = getattr(txn, "shares", 0) or 0
                        price = getattr(txn, "price_per_share", 0) or 0
                        value = shares * price

                        if code == "P":  # Purchase
                            buy_count += 1
                            buy_value += value
                        elif code == "S":  # Sale
                            sell_count += 1
                            sell_value += value

                except Exception as e:
                    logger.debug(f"Failed to parse Form 4 filing: {e}")
                    continue

            # Calculate sentiment score
            total_count = buy_count + sell_count
            if total_count == 0:
                logger.debug(f"No insider transactions found for {symbol} in last {days} days")
                return None

            # Weighted by both count and value
            count_ratio = (buy_count - sell_count) / total_count
            total_value = buy_value + sell_value
            value_ratio = (
                (buy_value - sell_value) / total_value if total_value > 0 else 0.0
            )

            # Average count and value ratios
            sentiment_score = (count_ratio + value_ratio) / 2.0

            logger.info(
                f"Insider sentiment for {symbol}: {sentiment_score:.2f} "
                f"(buys: {buy_count}/${buy_value:,.0f}, sells: {sell_count}/${sell_value:,.0f})"
            )

            return InsiderSentiment(
                symbol=symbol,
                sentiment_score=sentiment_score,
                buy_count=buy_count,
                sell_count=sell_count,
                buy_value=buy_value,
                sell_value=sell_value,
                analysis_period_days=days,
            )

        except Exception as e:
            logger.error(f"Failed to analyze insider sentiment for {symbol}: {e}")
            return None


class SECFilingsProvider(ABC):
    """Abstract base class for SEC filings data providers.

    Enables multi-provider architecture with graceful fallback.
    Current implementation: EdgarTools (edgartools library)
    Future: Could add AlphaVantage, SEC-API, or other providers
    """

    @abstractmethod
    def get_latest_filing(
        self, symbol: str, filing_type: str = "10-K"
    ) -> Optional[SECFilingsData]:
        """Get latest filing data for a symbol.

        Args:
            symbol: Stock ticker symbol
            filing_type: Type of filing (10-K, 10-Q, 8-K)

        Returns:
            SECFilingsData if available, None otherwise
        """
        pass


class EdgarToolsProvider(SECFilingsProvider):
    """EdgarTools-based SEC filings provider.

    Uses the edgartools library to access SEC EDGAR database.
    Provides access to 10-K, 10-Q, and other filings.
    """

    def __init__(self) -> None:
        """Initialize EdgarTools provider."""
        try:
            from edgar import Company, set_identity

            self._Company = Company
            self._set_identity = set_identity

            # Set SEC identity (required)
            self._set_identity("alpaca.options.bot@trading.com")
            logger.info("EdgarTools provider initialized")
        except ImportError:
            logger.error("edgartools library not installed. Run: uv add edgartools")
            raise

    def get_latest_filing(
        self, symbol: str, filing_type: str = "10-K"
    ) -> Optional[SECFilingsData]:
        """Get latest filing data for a symbol using EdgarTools.

        Args:
            symbol: Stock ticker symbol
            filing_type: Type of filing (10-K, 10-Q, 8-K)

        Returns:
            SECFilingsData if available, None otherwise
        """
        try:
            company = self._Company(symbol)
            filings = company.get_filings(form=filing_type)

            if not filings or len(filings) == 0:
                logger.warning(f"No {filing_type} filings found for {symbol}")
                return None

            # Get latest filing
            latest = filings.latest()
            filing_obj = latest.obj()

            # Extract sections
            business = None
            risk_factors = None
            mda = None

            if hasattr(filing_obj, "business"):
                business = str(filing_obj.business) if filing_obj.business else None

            if hasattr(filing_obj, "risk_factors"):
                risk_factors = (
                    str(filing_obj.risk_factors) if filing_obj.risk_factors else None
                )

            if hasattr(filing_obj, "management_discussion"):
                mda = (
                    str(filing_obj.management_discussion)
                    if filing_obj.management_discussion
                    else None
                )

            return SECFilingsData(
                symbol=symbol,
                filing_type=filing_type,
                filing_date=latest.filing_date,
                business=business,
                risk_factors=risk_factors,
                mda=mda,
            )

        except Exception as e:
            logger.error(f"Failed to retrieve {filing_type} for {symbol}: {e}")
            return None


class SECFilingsAnalyzer:
    """Main interface for SEC filings analysis with caching.

    Provides risk scoring and financial health analysis for trading decisions.
    Uses caching to avoid hitting SEC rate limits (10 requests/second).

    Usage:
        analyzer = SECFilingsAnalyzer(cache_ttl_days=7)
        risk_score = analyzer.get_risk_score("AAPL")
        if risk_score and risk_score.overall_score > 7.0:
            logger.info("High risk detected")
    """

    def __init__(self, cache_ttl_days: int = 7):
        """Initialize SEC filings analyzer.

        Args:
            cache_ttl_days: Cache time-to-live in days (default 7)
                           SEC filings don't change frequently, so longer cache is fine
        """
        self._providers: list[SECFilingsProvider] = [EdgarToolsProvider()]
        self._cache: dict[str, tuple[Optional[SECFilingsData], datetime]] = {}
        self._cache_ttl = timedelta(days=cache_ttl_days)
        self._insider_activity = InsiderActivity()
        self._insider_cache: dict[str, tuple[Optional[InsiderSentiment], datetime]] = {}
        self._cashflow_cache: dict[str, tuple[Optional[CashFlowHealth], datetime]] = {}
        self._auditor_cache: dict[str, tuple[Optional[AuditorWarnings], datetime]] = {}
        logger.info(f"SEC filings analyzer initialized (cache TTL: {cache_ttl_days} days)")

    def _get_filing_cached(
        self, symbol: str, filing_type: str = "10-K"
    ) -> Optional[SECFilingsData]:
        """Get filing data with caching.

        Args:
            symbol: Stock ticker symbol
            filing_type: Type of filing

        Returns:
            SECFilingsData if available, None otherwise
        """
        cache_key = f"{symbol}:{filing_type}"

        # Check cache
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_data

        # Cache miss - fetch from providers
        logger.debug(f"Cache miss for {cache_key}, fetching from providers")
        filing_data = None

        for provider in self._providers:
            try:
                filing_data = provider.get_latest_filing(symbol, filing_type)
                if filing_data:
                    break
            except Exception as e:
                logger.warning(
                    f"Provider {provider.__class__.__name__} failed for {symbol}: {e}"
                )
                continue

        # Cache result (even if None)
        self._cache[cache_key] = (filing_data, datetime.now())
        return filing_data

    def get_risk_score(self, symbol: str) -> Optional[RiskScore]:
        """Calculate risk score for a symbol based on 10-K filings.

        Risk scoring factors:
            - Number and severity of risk factors mentioned
            - Legal proceedings
            - Regulatory risks
            - Competitive risks

        Args:
            symbol: Stock ticker symbol

        Returns:
            RiskScore if analysis successful, None otherwise
        """
        filing = self._get_filing_cached(symbol, "10-K")
        if not filing or not filing.risk_factors:
            logger.warning(f"No risk factors data available for {symbol}")
            return None

        risk_text = filing.risk_factors.lower()

        # Count risk indicators
        risk_keywords = [
            "litigation",
            "lawsuit",
            "regulatory",
            "compliance",
            "investigation",
            "dispute",
            "violation",
            "penalty",
            "sanctions",
            "material adverse",
            "significant risk",
            "uncertainty",
        ]

        risk_count = sum(risk_text.count(keyword) for keyword in risk_keywords)

        # Check for specific risk types
        has_legal = any(
            keyword in risk_text for keyword in ["litigation", "lawsuit", "legal proceedings"]
        )
        has_regulatory = any(
            keyword in risk_text for keyword in ["regulatory", "compliance", "sec investigation"]
        )

        # Calculate overall score (0-10, higher = riskier)
        # Base score on risk keyword frequency
        base_score = min(risk_count / 10.0, 7.0)  # Cap at 7.0 from keyword count

        # Add penalties for specific risks
        if has_legal:
            base_score += 1.5
        if has_regulatory:
            base_score += 1.5

        overall_score = min(base_score, 10.0)  # Cap at 10.0

        logger.info(
            f"Risk score for {symbol}: {overall_score:.1f} "
            f"(factors: {risk_count}, legal: {has_legal}, regulatory: {has_regulatory})"
        )

        return RiskScore(
            symbol=symbol,
            overall_score=overall_score,
            risk_factor_count=risk_count,
            has_legal_proceedings=has_legal,
            has_regulatory_risks=has_regulatory,
            filing_date=filing.filing_date,
        )

    def get_financial_health(self, symbol: str) -> Optional[FinancialHealth]:
        """Assess financial health based on 10-K filings.

        Financial health factors:
            - Availability of complete financial statements
            - Management discussion sentiment
            - Business description stability

        Args:
            symbol: Stock ticker symbol

        Returns:
            FinancialHealth if analysis successful, None otherwise
        """
        filing = self._get_filing_cached(symbol, "10-K")
        if not filing:
            logger.warning(f"No filings data available for {symbol}")
            return None

        # Check data availability
        has_balance_sheet = filing.business is not None
        has_income_statement = filing.mda is not None

        # Simple health score based on data availability
        health_score = 5.0  # Neutral baseline

        if has_balance_sheet:
            health_score += 2.0
        if has_income_statement:
            health_score += 2.0

        # Analyze MD&A for negative sentiment if available
        if filing.mda:
            mda_text = filing.mda.lower()
            negative_keywords = [
                "decline",
                "decrease",
                "loss",
                "impairment",
                "downturn",
                "challenging",
                "adverse",
            ]
            negative_count = sum(mda_text.count(keyword) for keyword in negative_keywords)

            # Reduce health score for negative sentiment
            health_score -= min(negative_count / 5.0, 2.0)

        health_score = max(0.0, min(health_score, 10.0))  # Clamp to 0-10

        notes = None
        if health_score < 5.0:
            notes = "Low financial health detected from SEC filings"

        logger.info(f"Financial health for {symbol}: {health_score:.1f}")

        return FinancialHealth(
            symbol=symbol,
            health_score=health_score,
            has_balance_sheet=has_balance_sheet,
            has_income_statement=has_income_statement,
            filing_date=filing.filing_date,
            notes=notes,
        )

    def has_high_risk(self, symbol: str, threshold: float = 7.0) -> bool:
        """Check if symbol has high risk based on SEC filings.

        Args:
            symbol: Stock ticker symbol
            threshold: Risk score threshold (default 7.0)

        Returns:
            True if risk score exceeds threshold, False otherwise
        """
        risk_score = self.get_risk_score(symbol)
        if not risk_score:
            return False
        return risk_score.overall_score >= threshold

    def get_insider_sentiment(self, symbol: str, days: int = 90) -> Optional[InsiderSentiment]:
        """Get insider sentiment with caching.

        Args:
            symbol: Stock ticker symbol
            days: Number of days to analyze (default: 90)

        Returns:
            InsiderSentiment if available, None otherwise
        """
        cache_key = f"{symbol}:insider:{days}"

        # Check cache
        if cache_key in self._insider_cache:
            cached_data, cached_time = self._insider_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                logger.debug(f"Cache hit for insider sentiment: {cache_key}")
                return cached_data

        # Cache miss - fetch from insider activity analyzer
        logger.debug(f"Cache miss for insider sentiment: {cache_key}")
        sentiment = self._insider_activity.get_insider_sentiment(symbol, days)

        # Cache result (even if None)
        self._insider_cache[cache_key] = (sentiment, datetime.now())
        return sentiment

    def has_negative_insider_activity(
        self, symbol: str, threshold: float = -0.3, days: int = 90
    ) -> bool:
        """Check if symbol has negative insider trading activity.

        Args:
            symbol: Stock ticker symbol
            threshold: Sentiment threshold (default: -0.3, range: -1.0 to +1.0)
            days: Number of days to analyze (default: 90)

        Returns:
            True if insider sentiment is below threshold (heavy selling), False otherwise
        """
        sentiment = self.get_insider_sentiment(symbol, days)
        if not sentiment:
            return False
        return sentiment.sentiment_score < threshold

    def get_cash_flow_health(self, symbol: str) -> Optional[CashFlowHealth]:
        """Analyze cash flow health and bankruptcy risk from 10-K/10-Q filings.

        Analyzes:
            - Operating cash flow trends (current and historical quarters)
            - Debt levels (debt/equity ratio)
            - Current ratio (liquidity)
            - Bankruptcy risk score calculation

        Args:
            symbol: Stock ticker symbol

        Returns:
            CashFlowHealth with bankruptcy risk metrics, None if data unavailable
        """
        cache_key = f"{symbol}:cashflow"

        # Check cache
        if cache_key in self._cashflow_cache:
            cached_data, cached_time = self._cashflow_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                logger.debug(f"Cache hit for cash flow health: {cache_key}")
                return cached_data

        # Cache miss - analyze filings
        logger.debug(f"Cache miss for cash flow health: {cache_key}, analyzing filings")

        try:
            from edgar import Company

            company = Company(symbol)

            # Try 10-K first, fallback to 10-Q
            filing = None
            filing_type = None
            for ftype in ["10-K", "10-Q"]:
                filings = company.get_filings(form=ftype)
                if filings and len(filings) > 0:
                    filing = filings.latest()
                    filing_type = ftype
                    break

            if not filing:
                logger.warning(f"No 10-K or 10-Q filings found for {symbol}")
                self._cashflow_cache[cache_key] = (None, datetime.now())
                return None

            filing_obj = filing.obj()

            # Initialize default values
            has_negative_ocf = False
            ocf_quarters_negative = 0
            has_high_debt = False
            has_low_liquidity = False

            # Parse cash flow statement
            if hasattr(filing_obj, "cash_flow_statement"):
                cf_stmt = filing_obj.cash_flow_statement
                if cf_stmt is not None:
                    # Check operating cash flow
                    # Common field names: "OperatingCashFlow", "NetCashProvidedByOperatingActivities"
                    ocf_value = None
                    if hasattr(cf_stmt, "OperatingCashFlow"):
                        ocf_value = getattr(cf_stmt, "OperatingCashFlow", None)
                    elif hasattr(cf_stmt, "NetCashProvidedByOperatingActivities"):
                        ocf_value = getattr(cf_stmt, "NetCashProvidedByOperatingActivities", None)

                    if ocf_value is not None:
                        try:
                            ocf_float = float(ocf_value)
                            has_negative_ocf = ocf_float < 0
                        except (ValueError, TypeError):
                            pass

            # Parse balance sheet for debt and liquidity
            if hasattr(filing_obj, "balance_sheet"):
                bs = filing_obj.balance_sheet
                if bs is not None:
                    # Debt/equity ratio
                    total_debt = None
                    total_equity = None

                    if hasattr(bs, "LongTermDebt"):
                        total_debt = getattr(bs, "LongTermDebt", None)
                    if hasattr(bs, "StockholdersEquity"):
                        total_equity = getattr(bs, "StockholdersEquity", None)

                    if total_debt is not None and total_equity is not None:
                        try:
                            debt = float(total_debt)
                            equity = float(total_equity)
                            if equity > 0:
                                debt_equity_ratio = debt / equity
                                has_high_debt = debt_equity_ratio > 2.0
                        except (ValueError, TypeError):
                            pass

                    # Current ratio (current assets / current liabilities)
                    current_assets = None
                    current_liabilities = None

                    if hasattr(bs, "AssetsCurrent"):
                        current_assets = getattr(bs, "AssetsCurrent", None)
                    if hasattr(bs, "LiabilitiesCurrent"):
                        current_liabilities = getattr(bs, "LiabilitiesCurrent", None)

                    if current_assets is not None and current_liabilities is not None:
                        try:
                            assets = float(current_assets)
                            liabilities = float(current_liabilities)
                            if liabilities > 0:
                                current_ratio = assets / liabilities
                                has_low_liquidity = current_ratio < 1.0
                        except (ValueError, TypeError):
                            pass

            # Check 10-Q history for consecutive negative quarters
            if filing_type == "10-Q":
                try:
                    quarterly_filings = company.get_filings(form="10-Q")
                    if quarterly_filings and len(quarterly_filings) > 1:
                        for q_filing in quarterly_filings[:4]:  # Check last 4 quarters
                            try:
                                q_obj = q_filing.obj()
                                if hasattr(q_obj, "cash_flow_statement"):
                                    cf = q_obj.cash_flow_statement
                                    if cf is not None:
                                        ocf = None
                                        if hasattr(cf, "OperatingCashFlow"):
                                            ocf = getattr(cf, "OperatingCashFlow", None)
                                        elif hasattr(cf, "NetCashProvidedByOperatingActivities"):
                                            ocf = getattr(
                                                cf, "NetCashProvidedByOperatingActivities", None
                                            )

                                        if ocf is not None:
                                            try:
                                                if float(ocf) < 0:
                                                    ocf_quarters_negative += 1
                                                else:
                                                    break  # Stop at first positive quarter
                                            except (ValueError, TypeError):
                                                break
                            except Exception as e:
                                logger.debug(f"Failed to parse quarterly filing: {e}")
                                break
                except Exception as e:
                    logger.debug(f"Failed to analyze quarterly history: {e}")

            # Calculate bankruptcy risk score (0-10, higher = more risk)
            risk_score = 0.0

            # Negative OCF scoring
            if has_negative_ocf:
                risk_score += 3.0
            if ocf_quarters_negative >= 2:
                risk_score += 2.0
            if ocf_quarters_negative >= 3:
                risk_score += 1.0

            # High debt scoring
            if has_high_debt:
                risk_score += 2.5

            # Low liquidity scoring
            if has_low_liquidity:
                risk_score += 2.0

            risk_score = min(risk_score, 10.0)  # Cap at 10.0

            logger.info(
                f"Cash flow health for {symbol}: risk_score={risk_score:.1f}, "
                f"neg_ocf={has_negative_ocf}, quarters_neg={ocf_quarters_negative}, "
                f"high_debt={has_high_debt}, low_liquidity={has_low_liquidity}"
            )

            cash_flow_health = CashFlowHealth(
                symbol=symbol,
                has_negative_ocf=has_negative_ocf,
                ocf_quarters_negative=ocf_quarters_negative,
                has_high_debt=has_high_debt,
                has_low_liquidity=has_low_liquidity,
                bankruptcy_risk_score=risk_score,
                filing_date=filing.filing_date,
            )

            # Cache result
            self._cashflow_cache[cache_key] = (cash_flow_health, datetime.now())
            return cash_flow_health

        except Exception as e:
            logger.error(f"Failed to analyze cash flow health for {symbol}: {e}")
            self._cashflow_cache[cache_key] = (None, datetime.now())
            return None

    def has_bankruptcy_risk(self, symbol: str, threshold: float = 7.0) -> bool:
        """Check if symbol has high bankruptcy risk.

        Args:
            symbol: Stock ticker symbol
            threshold: Bankruptcy risk score threshold (default: 7.0, range: 0-10)

        Returns:
            True if bankruptcy risk score >= threshold, False otherwise
        """
        cash_flow_health = self.get_cash_flow_health(symbol)
        if not cash_flow_health:
            return False
        return cash_flow_health.bankruptcy_risk_score >= threshold

    def get_auditor_warnings(self, symbol: str) -> Optional[AuditorWarnings]:
        """Analyze 10-K filings for auditor warnings and red flags.

        Scans for critical keywords indicating:
            - Going concern warnings (substantial doubt about ability to continue)
            - Material weaknesses in internal controls
            - Recent auditor changes (potential red flag)
            - Financial restatements

        Args:
            symbol: Stock ticker symbol

        Returns:
            AuditorWarnings if analysis successful, None otherwise
        """
        cache_key = f"{symbol}:auditor"

        # Check cache
        if cache_key in self._auditor_cache:
            cached_data, cached_time = self._auditor_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                logger.debug(f"Cache hit for auditor warnings: {cache_key}")
                return cached_data

        # Cache miss - analyze 10-K
        logger.debug(f"Cache miss for auditor warnings: {cache_key}")
        filing = self._get_filing_cached(symbol, "10-K")
        if not filing:
            logger.warning(f"No 10-K filing available for auditor analysis: {symbol}")
            self._auditor_cache[cache_key] = (None, datetime.now())
            return None

        # Combine all available text sections for comprehensive search
        search_text = ""
        if filing.risk_factors:
            search_text += filing.risk_factors + " "
        if filing.mda:
            search_text += filing.mda + " "
        if filing.business:
            search_text += filing.business

        if not search_text:
            logger.warning(f"No text content available for auditor analysis: {symbol}")
            self._auditor_cache[cache_key] = (None, datetime.now())
            return None

        search_text = search_text.lower()

        # Check for going concern warnings
        has_going_concern = any(
            keyword in search_text
            for keyword in ["going concern", "substantial doubt", "ability to continue"]
        )

        # Check for material weakness in internal controls
        has_material_weakness = any(
            keyword in search_text
            for keyword in ["material weakness", "internal control deficienc"]
        )

        # Check for auditor changes
        has_auditor_change = any(
            keyword in search_text
            for keyword in ["change in auditor", "change of auditor", "dismissed auditor"]
        )

        # Check for restatements
        has_restatement = any(
            keyword in search_text for keyword in ["restatement", "restated financial"]
        )

        warnings = AuditorWarnings(
            symbol=symbol,
            has_going_concern=has_going_concern,
            has_material_weakness=has_material_weakness,
            has_auditor_change=has_auditor_change,
            has_restatement=has_restatement,
            filing_date=filing.filing_date,
        )

        logger.info(
            f"Auditor warnings for {symbol}: {warnings.warning_count} total "
            f"(going_concern={has_going_concern}, material_weakness={has_material_weakness}, "
            f"auditor_change={has_auditor_change}, restatement={has_restatement})"
        )

        # Cache result
        self._auditor_cache[cache_key] = (warnings, datetime.now())
        return warnings

    def has_critical_auditor_warnings(self, symbol: str) -> bool:
        """Check if symbol has critical auditor warnings.

        Critical warnings include:
            - Going concern doubts
            - Material weaknesses in internal controls

        Args:
            symbol: Stock ticker symbol

        Returns:
            True if critical warnings detected, False otherwise
        """
        warnings = self.get_auditor_warnings(symbol)
        if not warnings:
            return False
        return warnings.has_critical_warnings()

    def clear_cache(self) -> None:
        """Clear the filings cache."""
        self._cache.clear()
        self._insider_cache.clear()
        self._cashflow_cache.clear()
        self._auditor_cache.clear()
        logger.info("SEC filings cache cleared")
