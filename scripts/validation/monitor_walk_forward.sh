#!/bin/bash
# Monitor Walk-Forward Validation Progress

echo "═══════════════════════════════════════════════════════════"
echo "  Walk-Forward Validation Monitor"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Expected Runtime: ~2 hours (4 symbols × 4 windows)"
echo "Symbols: SPY, AAPL, MSFT, NVDA"
echo "Windows: 2019-2020→2021, 2020-2021→2022, 2021-2022→2023, 2022-2023→2024"
echo ""
echo "Press Ctrl+C to exit monitoring (validation will continue in background)"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo ""

# Follow the log file
tail -f logs/walk_forward.log
