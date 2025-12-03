"""Alpaca API client wrapper for unified access."""

import logging
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.live.option import OptionDataStream
from alpaca.data.live.stock import StockDataStream
from alpaca.data.enums import DataFeed

from alpaca_options.core.config import Settings

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Unified Alpaca API client managing all sub-clients.

    Provides centralized access to:
    - Trading API (orders, positions, account)
    - Stock market data (bars, quotes, trades)
    - Options market data (chains, quotes)
    - Real-time streaming data
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._api_key = settings.alpaca.api_key
        self._api_secret = settings.alpaca.api_secret
        self._paper = settings.alpaca.paper
        self._data_feed = settings.alpaca.data_feed

        # Clients (lazily initialized)
        self._trading_client: Optional[TradingClient] = None
        self._stock_data_client: Optional[StockHistoricalDataClient] = None
        self._option_data_client: Optional[OptionHistoricalDataClient] = None
        self._stock_stream: Optional[StockDataStream] = None
        self._option_stream: Optional[OptionDataStream] = None

        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._is_connected

    @property
    def is_paper(self) -> bool:
        """Check if using paper trading."""
        return self._paper

    def _validate_credentials(self) -> None:
        """Validate API credentials are set."""
        if not self._api_key or not self._api_secret:
            raise ValueError(
                "Alpaca API credentials not configured. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables."
            )

    @property
    def trading(self) -> TradingClient:
        """Get the trading client for orders and account management."""
        if self._trading_client is None:
            self._validate_credentials()
            self._trading_client = TradingClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
                paper=self._paper,
            )
            logger.info(f"Trading client initialized (paper={self._paper})")
        return self._trading_client

    @property
    def stock_data(self) -> StockHistoricalDataClient:
        """Get the stock historical data client."""
        if self._stock_data_client is None:
            self._validate_credentials()
            self._stock_data_client = StockHistoricalDataClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
            )
            logger.info("Stock data client initialized")
        return self._stock_data_client

    @property
    def option_data(self) -> OptionHistoricalDataClient:
        """Get the options historical data client."""
        if self._option_data_client is None:
            self._validate_credentials()
            self._option_data_client = OptionHistoricalDataClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
            )
            logger.info("Options data client initialized")
        return self._option_data_client

    def _get_data_feed(self) -> DataFeed:
        """Convert string data feed to DataFeed enum."""
        feed_map = {
            "iex": DataFeed.IEX,
            "sip": DataFeed.SIP,
            "delayed_sip": DataFeed.DELAYED_SIP,
            "otc": DataFeed.OTC,
        }
        return feed_map.get(self._data_feed.lower(), DataFeed.IEX)

    @property
    def stock_stream(self) -> StockDataStream:
        """Get the stock real-time data stream."""
        if self._stock_stream is None:
            self._validate_credentials()
            self._stock_stream = StockDataStream(
                api_key=self._api_key,
                secret_key=self._api_secret,
                feed=self._get_data_feed(),
            )
            logger.info(f"Stock stream initialized (feed={self._data_feed})")
        return self._stock_stream

    @property
    def option_stream(self) -> OptionDataStream:
        """Get the options real-time data stream."""
        if self._option_stream is None:
            self._validate_credentials()
            self._option_stream = OptionDataStream(
                api_key=self._api_key,
                secret_key=self._api_secret,
                feed=self._get_data_feed(),
            )
            logger.info(f"Options stream initialized (feed={self._data_feed})")
        return self._option_stream

    async def connect(self) -> None:
        """Establish connections to Alpaca APIs."""
        self._validate_credentials()

        # Test trading connection by fetching account
        try:
            account = self.trading.get_account()
            logger.info(
                f"Connected to Alpaca (Account: {account.account_number}, "
                f"Equity: ${float(account.equity):,.2f})"
            )
            self._is_connected = True
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Alpaca APIs and cleanup resources."""
        # Close streaming connections
        if self._stock_stream is not None:
            try:
                await self._stock_stream.close()
            except Exception as e:
                logger.warning(f"Error closing stock stream: {e}")

        if self._option_stream is not None:
            try:
                await self._option_stream.close()
            except Exception as e:
                logger.warning(f"Error closing option stream: {e}")

        self._is_connected = False
        logger.info("Disconnected from Alpaca")

    def get_account_info(self) -> dict:
        """Get current account information.

        Returns:
            Dictionary with account details.
        """
        account = self.trading.get_account()
        return {
            "account_number": account.account_number,
            "status": account.status.value if account.status else "unknown",
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
            "account_blocked": account.account_blocked,
            "daytrade_count": account.daytrade_count,
            "last_equity": float(account.last_equity),
            "multiplier": account.multiplier,
            "initial_margin": float(account.initial_margin) if account.initial_margin else 0,
            "maintenance_margin": float(account.maintenance_margin) if account.maintenance_margin else 0,
            "sma": float(account.sma) if account.sma else 0,
        }


# Global client instance
_default_client: Optional[AlpacaClient] = None


def get_alpaca_client(settings: Optional[Settings] = None) -> AlpacaClient:
    """Get or create the default Alpaca client.

    Args:
        settings: Optional settings. Required on first call.

    Returns:
        The global AlpacaClient instance.
    """
    global _default_client

    if _default_client is None:
        if settings is None:
            raise ValueError("Settings required for first client initialization")
        _default_client = AlpacaClient(settings)

    return _default_client
