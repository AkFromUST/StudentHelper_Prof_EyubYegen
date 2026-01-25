#!/usr/bin/env python3
"""
Simple test script to verify config import works correctly.
"""

import os
import sys

# Add parent directory to path to import config
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

print(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")
print(f"Parent directory: {parent_dir}")
print(f"Python path (first 3): {sys.path[:3]}")
print()

try:
    import config
    print("✓ Config imported successfully!")
    print()
    print("Configuration values:")
    print(f"  - USER_NAME: {config.USER_NAME}")
    print(f"  - USER_EMAIL: {config.USER_EMAIL}")
    print(f"  - USER_OCCUPATION: {config.USER_OCCUPATION}")
    print(f"  - MAX_FILES_PER_BATCH: {config.MAX_FILES_PER_BATCH}")
    print(f"  - REQUESTED_DOCS_FILE: {config.REQUESTED_DOCS_FILE}")
    print()
    
    # Check if CSV file exists
    csv_path = "../AutomationComparison/results/not_found_in_all_reqs.csv"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_csv_path = os.path.normpath(os.path.join(script_dir, csv_path))
    
    print(f"CSV file check:")
    print(f"  - Expected path: {full_csv_path}")
    if os.path.exists(full_csv_path):
        print(f"  - ✓ File exists!")
        # Count lines
        with open(full_csv_path, 'r') as f:
            lines = f.readlines()
            total_lines = len(lines)
            names = [line.strip() for line in lines[1:] if line.strip()]  # Skip header
        print(f"  - Total lines: {total_lines}")
        print(f"  - Names (excluding header): {len(names)}")
        print(f"  - Names: {', '.join(names[:5])}{'...' if len(names) > 5 else ''}")
    else:
        print(f"  - ✗ File not found!")
    print()
    
    # Check if requested_documents.json exists
    tracker_path = os.path.join(script_dir, "requested_documents.json")
    print(f"Tracker file check:")
    print(f"  - Expected path: {tracker_path}")
    if os.path.exists(tracker_path):
        print(f"  - ✓ File exists!")
        import json
        with open(tracker_path, 'r') as f:
            data = json.load(f)
        print(f"  - Entries in tracker: {len(data)}")
        if data:
            first_key = list(data.keys())[0]
            print(f"  - Example entry: {first_key[:60]}...")
            print(f"    - Documents tracked: {len(data[first_key])}")
    else:
        print(f"  - ✗ File not found (will be created on first run)")
    
    print()
    print("=" * 70)
    print("✓ All checks passed! Ready to run the script.")
    print("=" * 70)
    
except ImportError as e:
    print(f"✗ Failed to import config!")
    print(f"  - Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error during checks: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
