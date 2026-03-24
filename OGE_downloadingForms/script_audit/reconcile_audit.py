#!/usr/bin/env python3
"""
Reconciles Automation_Script_Downloads_notMatched/ to match automation_audit.json exactly.

For each person folder:
  - Deletes PDF files present on disk but NOT listed in the JSON
    (these are byte-identical duplicates that dedup_audit.py flagged for removal).
  - Preserves ALL files that ARE listed in the JSON, including _1/_2/etc. suffixed
    files that dedup_audit.py confirmed have unique content.
  - Reports PDF files listed in the JSON but missing from disk (anomalies).
  - Reports folders on disk with no corresponding JSON key (leaves them untouched).

Folders whose names start with '_' (e.g. _Unmatched) are skipped entirely.
Non-PDF files (e.g. .DS_Store) are never touched.

Usage:
  python reconcile_audit.py           # dry run — prints what would happen, no deletions
  python reconcile_audit.py --live    # actually deletes unwanted files
"""

import json
import sys
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent   # OGE_downloadingForms/
SOURCE_DIR = BASE_DIR / "Automation_Script_Downloads_notMatched"
AUDIT_PATH = Path(__file__).resolve().parent / "automation_audit.json"

DRY_RUN = "--live" not in sys.argv


def sanitize_folder_name(key: str) -> str:
    """Mirror the sanitization used by organize_by_person.py / dedup_audit.py."""
    return key.replace("/", "_").replace(":", "_")[:200]


def main():
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        audit: dict[str, list[str]] = json.load(f)

    # folder_name → set of expected PDF filenames (all kept, including _1/_2 variants)
    expected: dict[str, set[str]] = {
        sanitize_folder_name(key): set(files)
        for key, files in audit.items()
    }

    files_deleted: int = 0
    files_missing: list[str] = []
    unknown_folders: list[str] = []

    for folder in sorted(SOURCE_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        if folder.name not in expected:
            unknown_folders.append(folder.name)
            continue

        expected_files = expected[folder.name]
        actual_pdfs    = {f.name for f in folder.glob("*.pdf")}

        # Remove files that exist on disk but are not in the JSON
        # (byte-identical duplicates identified by dedup_audit.py)
        for fname in sorted(actual_pdfs - expected_files):
            target = folder / fname
            if DRY_RUN:
                print(f"  [DRY RUN] would delete: {folder.name}/{fname}")
            else:
                target.unlink()
            files_deleted += 1

        # Report files the JSON expects but that are absent from disk
        for fname in sorted(expected_files - actual_pdfs):
            files_missing.append(f"{folder.name}/{fname}")

    print(f"\n{'='*60}")
    print(f"  Mode                         : {'DRY RUN (pass --live to apply)' if DRY_RUN else 'LIVE'}")
    print(f"  Files deleted (disk ∉ JSON)  : {files_deleted}")
    print(f"  Files missing (JSON ∉ disk)  : {len(files_missing)}")
    if files_missing:
        for m in files_missing[:30]:
            print(f"    MISSING: {m}")
        if len(files_missing) > 30:
            print(f"    ... and {len(files_missing) - 30} more")
    print(f"  Unknown folders (no JSON key): {len(unknown_folders)}")
    for uf in unknown_folders:
        print(f"    {uf}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
