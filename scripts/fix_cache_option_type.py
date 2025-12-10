#!/usr/bin/env python3
"""Fix cached option chains - convert option_type from uppercase to lowercase."""

import json
from pathlib import Path

cache_dir = Path("data/dolthub_cache")
cache_files = list(cache_dir.glob("*.json"))

print(f"Found {len(cache_files)} cache files to fix")

fixed_count = 0
for cache_file in cache_files:
    try:
        # Read cache
        with open(cache_file, "r") as f:
            data = json.load(f)

        # Check if needs fixing
        if data["contracts"] and isinstance(data["contracts"][0].get("option_type"), str):
            first_type = data["contracts"][0]["option_type"]
            if first_type in ("CALL", "PUT"):  # Uppercase - needs fixing
                # Fix all contracts
                for contract in data["contracts"]:
                    if "option_type" in contract:
                        contract["option_type"] = contract["option_type"].lower()

                # Write back
                with open(cache_file, "w") as f:
                    json.dump(data, f)

                fixed_count += 1
                if fixed_count % 50 == 0:
                    print(f"Fixed {fixed_count} files...")

    except Exception as e:
        print(f"Error fixing {cache_file.name}: {e}")

print(f"\n✓ Fixed {fixed_count}/{len(cache_files)} cache files")
print("All option_type values are now lowercase ('call', 'put')")
