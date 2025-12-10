#!/usr/bin/env python3
"""Test script to verify .env file loading."""

import os
import sys
from pathlib import Path

# Calculate project root (same as in optimize_delta.py)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

print(f"Project root: {project_root}")
print(f"Looking for .env at: {project_root / '.env'}")
print(f".env exists: {(project_root / '.env').exists()}")

# Load dotenv (same as in optimize_delta.py)
from dotenv import load_dotenv
result = load_dotenv(project_root / ".env")
print(f"\nload_dotenv() returned: {result}")

# Check environment variables
api_key = os.environ.get("ALPACA_API_KEY", "")
api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

print(f"\nALPACA_API_KEY found: {bool(api_key)}")
print(f"ALPACA_SECRET_KEY found: {bool(api_secret)}")

if api_key:
    print(f"ALPACA_API_KEY length: {len(api_key)}")
    print(f"ALPACA_API_KEY first 5 chars: {api_key[:5]}...")
if api_secret:
    print(f"ALPACA_SECRET_KEY length: {len(api_secret)}")
    print(f"ALPACA_SECRET_KEY first 5 chars: {api_secret[:5]}...")

if not api_key or not api_secret:
    print("\n❌ ERROR: Credentials not loaded from .env file")
    print("\nChecking if credentials are in shell environment:")
    print(f"  Shell ALPACA_API_KEY: {bool(os.getenv('ALPACA_API_KEY'))}")
    print(f"  Shell ALPACA_SECRET_KEY: {bool(os.getenv('ALPACA_SECRET_KEY'))}")
else:
    print("\n✓ Credentials loaded successfully")
