"""Rich-based terminal dashboard for trading bot monitoring."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from alpaca_options.core.events import Event, EventType

if TYPE_CHECKING:
    from alpaca_options.core.config import Settings
    from alpaca_options.core.engine import TradingEngine


class TradingDashboard:
    """Rich-based terminal dashboard for real-time trading monitoring."""

    def __init__(self, engine: "TradingEngine", settings: "Settings") -> None:
        self.engine = engine
        self.settings = settings
        self.console = Console()
        self._running = False

        # Dashboard state
        self._logs: list[str] = []
        self._orders: list[dict] = []
        self._greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        self._performance = {
            "today": 0.0,
            "week": 0.0,
            "month": 0.0,
            "ytd": 0.0,
        }

        # Screener state
        self._screener_enabled = settings.screener.enabled if hasattr(settings, 'screener') else False
        self._screener_opportunities: list[dict] = []
        self._screener_stats = {
            "scan_count": 0,
            "total_found": 0,
            "queue_size": 0,
            "last_scan": None,
        }

        # Cache the layout structure (created once, panels updated)
        self._layout: Layout | None = None

    def _create_layout(self) -> Layout:
        """Create the dashboard layout structure."""
        layout = Layout()

        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=12),
        )

        layout["main"].split_row(
            Layout(name="positions", ratio=2),
            Layout(name="sidebar", ratio=1),
        )

        # Adjust sidebar layout based on whether screener is enabled
        if self._screener_enabled:
            layout["sidebar"].split(
                Layout(name="screener", ratio=2),
                Layout(name="strategies", ratio=1),
                Layout(name="greeks", ratio=1),
            )
        else:
            layout["sidebar"].split(
                Layout(name="strategies", ratio=1),
                Layout(name="greeks", ratio=1),
            )

        layout["footer"].split_row(
            Layout(name="orders", ratio=1),
            Layout(name="logs", ratio=1),
        )

        return layout

    def _make_header(self) -> Panel:
        """Create the header panel."""
        mode = "PAPER" if self.settings.alpaca.paper else "LIVE"
        mode_color = "yellow" if self.settings.alpaca.paper else "red"
        status = "🟢 RUNNING" if self.engine.is_running else "🔴 STOPPED"

        # Get account info from engine (includes effective capital)
        account = self.engine.get_account_info()
        equity = account.get("equity", 0)
        effective_capital = account.get("effective_capital", equity)
        effective_bp = account.get("effective_buying_power", account.get("buying_power", 0))
        capital_capped = account.get("capital_capped", False)

        header_text = Text()
        header_text.append(f" {status}  ", style="bold")
        header_text.append(f"Mode: ", style="dim")
        header_text.append(f"{mode}  ", style=f"bold {mode_color}")

        # Show effective capital with cap indicator
        if capital_capped:
            header_text.append(f"Capital: ", style="dim")
            header_text.append(f"${effective_capital:,.0f}", style="green")
            header_text.append(f" [CAP]  ", style="yellow")
        else:
            header_text.append(f"Equity: ", style="dim")
            header_text.append(f"${equity:,.2f}  ", style="green")

        header_text.append(f"Buying Power: ", style="dim")
        header_text.append(f"${effective_bp:,.0f}", style="cyan")

        return Panel(
            header_text,
            title="[bold]Alpaca Options Bot[/bold]",
            border_style="blue",
        )

    def _make_positions_table(self) -> Panel:
        """Create the positions panel."""
        table = Table(expand=True, show_header=True, header_style="bold cyan")

        table.add_column("Symbol", style="white", no_wrap=True)
        table.add_column("Side", style="dim")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("P&L %", justify="right")

        positions = self.engine.get_positions()

        for pos in positions:
            pnl = pos.unrealized_pnl
            pnl_pct = pos.unrealized_pnl_percent
            pnl_style = "green" if pnl >= 0 else "red"
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            pnl_pct_str = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"

            table.add_row(
                pos.symbol,
                pos.side.upper(),
                str(pos.quantity),
                f"${pos.entry_price:.2f}",
                f"${pos.current_price:.2f}",
                Text(pnl_str, style=pnl_style),
                Text(pnl_pct_str, style=pnl_style),
            )

        if not positions:
            table.add_row(
                "[dim]No positions[/dim]", "", "", "", "", "", ""
            )

        return Panel(table, title="[bold]Active Positions[/bold]", border_style="green")

    def _make_strategies_panel(self) -> Panel:
        """Create the strategies status panel."""
        table = Table(expand=True, show_header=True, header_style="bold cyan")

        table.add_column("Strategy", style="white")
        table.add_column("Status", justify="center")
        table.add_column("Alloc", justify="right")

        strategy_status = self.engine.get_strategy_status()

        for name, status in strategy_status.items():
            status_icon = "🟢" if status["initialized"] else "🟡"
            status_text = "Active" if status["initialized"] else "Idle"
            allocation = f"{status['allocation'] * 100:.0f}%"

            table.add_row(
                name,
                f"{status_icon} {status_text}",
                allocation,
            )

        if not strategy_status:
            table.add_row("[dim]No strategies[/dim]", "", "")

        return Panel(table, title="[bold]Strategies[/bold]", border_style="yellow")

    def _make_greeks_panel(self) -> Panel:
        """Create the Greeks exposure panel."""
        risk = self.settings.risk

        # Calculate aggregate Greeks from positions (simplified)
        # In real implementation, this would sum Greeks from all option positions
        positions = self.engine.get_positions()
        total_delta = sum(
            getattr(p, 'delta', 0) * p.quantity
            for p in positions
            if hasattr(p, 'delta')
        )

        lines = []

        # Delta
        delta = self._greeks.get("delta", total_delta)
        delta_limit = risk.max_portfolio_delta
        delta_pct = abs(delta / delta_limit * 100) if delta_limit else 0
        delta_bar = self._make_bar(delta_pct, 30)
        lines.append(f"Delta:  {delta:>+8.1f}  {delta_bar}  ±{delta_limit}")

        # Gamma
        gamma = self._greeks.get("gamma", 0)
        gamma_limit = risk.max_portfolio_gamma
        gamma_pct = abs(gamma / gamma_limit * 100) if gamma_limit else 0
        gamma_bar = self._make_bar(gamma_pct, 30)
        lines.append(f"Gamma:  {gamma:>+8.1f}  {gamma_bar}  ±{gamma_limit}")

        # Theta
        theta = self._greeks.get("theta", 0)
        theta_target = abs(risk.min_portfolio_theta)
        theta_pct = abs(theta / theta_target * 100) if theta_target else 0
        theta_bar = self._make_bar(theta_pct, 30, positive=True)
        lines.append(f"Theta: ${theta:>+7.2f}  {theta_bar}  +${theta_target}")

        # Vega
        vega = self._greeks.get("vega", 0)
        vega_limit = risk.max_portfolio_vega
        vega_pct = abs(vega / vega_limit * 100) if vega_limit else 0
        vega_bar = self._make_bar(vega_pct, 30)
        lines.append(f"Vega:  ${vega:>+7.2f}  {vega_bar}  ±${vega_limit}")

        return Panel(
            "\n".join(lines),
            title="[bold]Greeks Exposure[/bold]",
            border_style="magenta",
        )

    def _make_bar(self, percent: float, max_width: int, positive: bool = False) -> str:
        """Create a simple progress bar."""
        filled = int(min(percent, 100) / 100 * max_width)
        empty = max_width - filled

        if positive:
            color = "green" if percent < 80 else "yellow"
        else:
            color = "green" if percent < 50 else ("yellow" if percent < 80 else "red")

        return f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"

    def _make_screener_panel(self) -> Panel:
        """Create the screener opportunities panel."""
        table = Table(expand=True, show_header=True, header_style="bold cyan")

        table.add_column("Symbol", style="white", no_wrap=True)
        table.add_column("Type", style="dim")
        table.add_column("Score", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("Signal", justify="center")

        # Show recent opportunities
        for opp in self._screener_opportunities[-8:]:  # Last 8 opportunities
            opp_type = opp.get("type", "")
            type_color = {
                "bullish": "green",
                "bearish": "red",
                "high_iv": "yellow",
                "low_iv": "cyan",
            }.get(opp_type.lower(), "white")

            signal = opp.get("signal", "")
            signal_color = "green" if signal.lower() == "buy" else ("red" if signal.lower() == "sell" else "white")

            score = opp.get("score", 0)
            score_color = "green" if score >= 70 else ("yellow" if score >= 50 else "dim")

            table.add_row(
                opp.get("symbol", ""),
                Text(opp_type.upper(), style=type_color),
                Text(f"{score:.0f}", style=score_color),
                f"{opp.get('rsi', 0):.0f}",
                Text(signal.upper(), style=signal_color),
            )

        if not self._screener_opportunities:
            table.add_row("[dim]Scanning...[/dim]", "", "", "", "")

        # Add stats footer
        stats = self._screener_stats
        last_scan = stats.get("last_scan")
        last_scan_str = last_scan.strftime("%H:%M:%S") if last_scan else "Never"

        subtitle = f"Scans: {stats['scan_count']} | Found: {stats['total_found']} | Last: {last_scan_str}"

        return Panel(
            table,
            title="[bold]Screener Opportunities[/bold]",
            subtitle=f"[dim]{subtitle}[/dim]",
            border_style="cyan",
        )

    def _make_orders_panel(self) -> Panel:
        """Create the recent orders panel."""
        table = Table(expand=True, show_header=True, header_style="bold cyan")

        table.add_column("Time", style="dim", width=8)
        table.add_column("Symbol", style="white")
        table.add_column("Side", justify="center")
        table.add_column("Qty", justify="right")
        table.add_column("Status", justify="center")

        # Show recent orders from log
        for order in self._orders[-5:]:  # Last 5 orders
            status_color = {
                "filled": "green",
                "submitted": "yellow",
                "cancelled": "red",
                "rejected": "red",
            }.get(order.get("status", ""), "white")

            table.add_row(
                order.get("time", ""),
                order.get("symbol", ""),
                order.get("side", "").upper(),
                str(order.get("quantity", "")),
                Text(order.get("status", "").upper(), style=status_color),
            )

        if not self._orders:
            table.add_row("[dim]No orders[/dim]", "", "", "", "")

        return Panel(table, title="[bold]Recent Orders[/bold]", border_style="cyan")

    def _make_logs_panel(self) -> Panel:
        """Create the logs panel."""
        max_lines = self.settings.ui.log_lines

        if not self._logs:
            log_text = "[dim]No log entries[/dim]"
        else:
            recent_logs = self._logs[-max_lines:]
            log_text = "\n".join(recent_logs)

        return Panel(log_text, title="[bold]Logs[/bold]", border_style="white")

    def _render(self) -> Layout:
        """Render the complete dashboard."""
        # Create layout once, reuse on subsequent renders
        if self._layout is None:
            self._layout = self._create_layout()

        self._layout["header"].update(self._make_header())
        self._layout["positions"].update(self._make_positions_table())
        self._layout["strategies"].update(self._make_strategies_panel())
        self._layout["greeks"].update(self._make_greeks_panel())
        self._layout["orders"].update(self._make_orders_panel())
        self._layout["logs"].update(self._make_logs_panel())

        # Add screener panel if enabled
        if self._screener_enabled:
            self._layout["screener"].update(self._make_screener_panel())

        return self._layout

    def add_log(self, message: str, level: str = "INFO") -> None:
        """Add a log message to the dashboard.

        Args:
            message: Log message text.
            level: Log level (INFO, WARN, ERROR, DEBUG).
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_colors = {
            "DEBUG": "dim",
            "INFO": "white",
            "WARN": "yellow",
            "ERROR": "red",
        }
        color = level_colors.get(level, "white")
        formatted = f"[dim]{timestamp}[/dim] [{color}]{level:5}[/{color}] {message}"
        self._logs.append(formatted)

        # Keep only recent logs
        max_logs = self.settings.ui.log_lines * 3
        if len(self._logs) > max_logs:
            self._logs = self._logs[-max_logs:]

    def add_order(self, order: dict) -> None:
        """Add an order to the orders list.

        Args:
            order: Order dictionary with symbol, side, quantity, status.
        """
        order["time"] = datetime.now().strftime("%H:%M:%S")
        self._orders.append(order)

        # Keep only recent orders
        if len(self._orders) > 20:
            self._orders = self._orders[-20:]

    async def _handle_event(self, event: Event) -> None:
        """Handle events from the event bus."""
        if event.event_type == EventType.ORDER_SUBMITTED:
            self.add_order({
                "symbol": event.data.get("symbol", ""),
                "side": event.data.get("side", ""),
                "quantity": event.data.get("quantity", 0),
                "status": "submitted",
            })
            self.add_log(
                f"Order submitted: {event.data.get('side', '')} "
                f"{event.data.get('quantity', '')} {event.data.get('symbol', '')}",
                "INFO"
            )

        elif event.event_type == EventType.ORDER_FILLED:
            self.add_log(
                f"Order filled: {event.data.get('symbol', '')}",
                "INFO"
            )

        elif event.event_type == EventType.SIGNAL_GENERATED:
            self.add_log(
                f"Signal: {event.data.get('signal_type', '')} "
                f"{event.data.get('underlying', '')} "
                f"(conf: {event.data.get('confidence', 0):.0%})",
                "INFO"
            )

        elif event.event_type == EventType.ERROR:
            self.add_log(
                f"Error: {event.data.get('error', 'Unknown')}",
                "ERROR"
            )

        elif event.event_type == EventType.STRATEGY_STARTED:
            self.add_log(
                f"Strategy started: {event.data.get('strategy', '')}",
                "INFO"
            )

        elif event.event_type == EventType.STRATEGY_STOPPED:
            self.add_log(
                f"Strategy stopped: {event.data.get('strategy', '')}",
                "WARN"
            )

        elif event.event_type == EventType.RISK_LIMIT_WARNING:
            self.add_log(
                f"Risk warning: {event.data.get('message', '')}",
                "WARN"
            )

        # Screener events
        elif event.event_type == EventType.SCREENER_UPDATE:
            self._screener_stats["scan_count"] += 1
            self._screener_stats["last_scan"] = datetime.now()
            self.add_log(
                f"Screener: {event.data.get('message', 'update')}",
                "INFO"
            )

        elif event.event_type == EventType.SCREENER_OPPORTUNITY:
            # Add opportunity to the list
            self._screener_opportunities.append({
                "symbol": event.data.get("symbol", ""),
                "type": event.data.get("type", ""),
                "score": event.data.get("score", 0),
                "rsi": event.data.get("rsi", 0),
                "signal": event.data.get("signal", ""),
                "priority": event.data.get("priority", ""),
                "time": datetime.now(),
            })
            self._screener_stats["total_found"] += 1

            # Keep only recent opportunities
            if len(self._screener_opportunities) > 50:
                self._screener_opportunities = self._screener_opportunities[-50:]

            self.add_log(
                f"Opportunity: {event.data.get('symbol', '')} "
                f"({event.data.get('type', '')}) "
                f"Score: {event.data.get('score', 0):.0f}",
                "INFO"
            )

    async def run(self) -> None:
        """Run the dashboard with live updates."""
        self._running = True

        # Subscribe to events
        self.engine.event_bus.subscribe_all(self._handle_event)

        # Start the trading engine
        self.add_log("Starting trading engine...", "INFO")
        await self.engine.start()
        self.add_log("Trading engine started", "INFO")

        try:
            with Live(
                self._render(),
                console=self.console,
                refresh_per_second=1 / self.settings.ui.refresh_rate,
                screen=True,
            ) as live:
                while self._running:
                    # Update the display
                    live.update(self._render())

                    # Allow other tasks to run
                    await asyncio.sleep(self.settings.ui.refresh_rate)

        except KeyboardInterrupt:
            self.add_log("Shutdown requested...", "WARN")
        finally:
            self._running = False
            self.add_log("Stopping trading engine...", "INFO")
            await self.engine.stop()
            self.add_log("Trading engine stopped", "INFO")

    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False
