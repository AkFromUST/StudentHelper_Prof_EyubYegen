#!/usr/bin/env python3
"""
Deduplicates PDF files across person folders and writes automation_audit.json.

For each person folder in Automation_Script_Downloads_notMatched/:
  1. Groups files by base name (stripping _1, _2, _1_1, etc. suffixes)
  2. Hashes every file (MD5) to detect byte-identical duplicates
  3. Keeps only content-unique files per group (prefers the unsuffixed original)

Output: script_audit/automation_audit.json
  Keys   = exact requested_documents.json keys
  Values = list of deduplicated filenames
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # OGE_downloadingForms/
SOURCE_DIR = BASE_DIR / "Automation_Script_Downloads_notMatched"
JSON_PATH = Path(__file__).resolve().parent / "consolidated_requested_documents.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "automation_audit.json"


def sanitize_folder_name(key: str) -> str:
    """Mirror the sanitization used by organize_by_person.py."""
    name = key.replace("/", "_").replace(":", "_")
    return name[:200]


def build_folder_to_key_map() -> dict[str, str]:
    """Map sanitized folder names back to their original JSON keys."""
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {sanitize_folder_name(k): k for k in data}


def strip_copy_suffix(stem: str) -> str:
    """Strip trailing _1, _1_1, etc. to get the canonical base stem."""
    return re.sub(r"(_\d+)+$", "", stem)


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def dedup_folder(folder: Path) -> tuple[list[str], int, int]:
    """Deduplicate PDFs in a single person folder.

    Returns (kept_filenames, total_files, duplicates_removed).
    Also returns count of cases where a suffixed file had different content.
    """
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        return [], 0, 0

    # Group by canonical base name
    groups: dict[str, list[Path]] = defaultdict(list)
    for pdf in pdfs:
        base = strip_copy_suffix(pdf.stem) + pdf.suffix
        groups[base].append(pdf)

    kept: list[str] = []
    duplicates_removed = 0

    for base_name, files in sorted(groups.items()):
        if len(files) == 1:
            kept.append(files[0].name)
            continue

        # Multiple files share the same base — hash them all
        hash_to_files: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            h = md5_file(f)
            hash_to_files[h].append(f)

        # For each unique hash, keep the file with the shortest name
        for h, same_content_files in hash_to_files.items():
            winner = min(same_content_files, key=lambda p: len(p.name))
            kept.append(winner.name)
            duplicates_removed += len(same_content_files) - 1

    return sorted(kept), len(pdfs), duplicates_removed


def main():
    folder_to_key = build_folder_to_key_map()

    audit: dict[str, list[str]] = {}
    total_files = 0
    total_kept = 0
    total_removed = 0
    different_content_kept = 0
    folders_processed = 0

    for folder in sorted(SOURCE_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        json_key = folder_to_key.get(folder.name)
        if not json_key:
            print(f"  WARN: no JSON key for folder: {folder.name[:80]}")
            json_key = folder.name

        kept, count, removed = dedup_folder(folder)
        audit[json_key] = kept
        total_files += count
        total_kept += len(kept)
        total_removed += removed
        folders_processed += 1

    # Count cases where suffixed files with different content were preserved
    for key, files in audit.items():
        bases = defaultdict(list)
        for f in files:
            base = strip_copy_suffix(Path(f).stem) + Path(f).suffix
            bases[base].append(f)
        for base, group in bases.items():
            if len(group) > 1:
                different_content_kept += len(group) - 1

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=4, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"  Folders processed       : {folders_processed}")
    print(f"  Total files scanned     : {total_files}")
    print(f"  Duplicates removed      : {total_removed}")
    print(f"  Unique files kept       : {total_kept}")
    print(f"  Different-content dupes : {different_content_kept}  (suffixed files with unique content, preserved)")
    print(f"  Output                  : {OUTPUT_PATH}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
