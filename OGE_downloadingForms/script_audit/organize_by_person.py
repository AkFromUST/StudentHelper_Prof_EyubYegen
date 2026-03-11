#!/usr/bin/env python3
"""
Organizes flat PDFs from Automation_Script_Downloads_notMatched into
per-person subdirectories based on requested_documents.json keys.

Matching strategy (layered):
  1. Exact prefix match ("last, first" from filename vs JSON key name prefix)
  2. Exact word-set match (unordered name word comparison)
  3. Partial prefix match (starts-with in either direction)
  4. Subset word-set match (handles missing middle initials)

When multiple candidates survive, document-description disambiguation
(type + date extracted from the filename) narrows to one key.
If still ambiguous -> _Unmatched.

Usage:
  python organize_by_person.py              # dry run (preview only)
  python organize_by_person.py --execute    # actually move files
"""

import json
import re
import shutil
import argparse
import difflib
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # OGE_downloadingForms/
JSON_PATH = Path(__file__).resolve().parent / "consolidated_requested_documents.json"
SOURCE_DIR = BASE_DIR / "Automation_Script_Downloads_notMatched"
UNMATCHED_FOLDER = "_Unmatched"

AGENCY_KEYWORDS = frozenset({
    "department", "office", "agency", "commission", "federal", "national",
    "nuclear", "export-import", "consumer", "securities", "commodity",
    "defense", "social", "farm", "equal", "occupational", "court",
    "african", "millennium", "peace", "broadcasting", "railroad",
    "chemical", "surface", "marine", "pension", "tennessee", "postal",
    "trade", "privacy", "arctic", "inter-american", "amtrak", "executive",
    "white", "the", "board", "overseas", "small", "international",
    "selective", "merit", "general", "council", "u.s.", "environmental",
    "corporation", "central", "intelligence", "homeland", "veterans",
    "housing", "transportation", "labor", "energy", "interior", "treasury",
    "agriculture", "education", "health", "state", "justice",
})


def norm(w: str) -> str:
    """Normalize a single name word: strip periods/commas, lowercase."""
    return w.rstrip(".,").strip().lower()


def strip_copy_suffix(stem: str) -> str:
    """Remove _1, _1_1, (1), (N), PART N, etc. from a filename stem."""
    stem = re.sub(r"(_\d+)+$", "", stem)
    stem = re.sub(r"\s*\(\d+\)$", "", stem)
    stem = re.sub(r"\s+PART\s+\d+$", "", stem, flags=re.IGNORECASE)
    return stem.strip()


NAME_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"})


def _expand_words(raw_words: list[str]) -> set[str]:
    """Normalize words and split any hyphenated tokens into sub-parts too.
    e.g. ['hoehn-saric', 'alex'] -> {'hoehn', 'saric', 'alex'}
    """
    out: set[str] = set()
    for w in raw_words:
        n = norm(w)
        if not n or n.isdigit() or n in NAME_SUFFIXES:
            continue
        if "-" in n:
            out.update(part for part in n.split("-") if part)
        else:
            out.add(n)
    return out


def _core_prefix(prefix: str) -> str:
    """Strip single-letter middle initials from a prefix for loose matching.
    'abbott, jarvis b' -> 'abbott, jarvis'
    """
    parts = prefix.split(",", 1)
    if len(parts) < 2:
        return prefix
    last = parts[0].strip()
    rest_words = parts[1].strip().split()
    core = [w for w in rest_words if len(w) > 1]
    return f"{last}, {' '.join(core)}".strip(", ") if core else last


def name_words_from_key(key: str) -> frozenset:
    """Extract the set of name words from a JSON key like
    'hoehn-saric, alex consumer product safety commission, ...'
    Hyphenated last names are split into components.
    """
    parts = key.split(",", 1)
    last = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""

    first_parts = []
    for w in rest.split():
        if norm(w) in AGENCY_KEYWORDS:
            break
        first_parts.append(w)

    return frozenset(_expand_words(last.split() + first_parts))


def name_prefix_from_key(key: str) -> str:
    """Extract 'last, first [middle]' prefix (lowercased) from a JSON key."""
    parts = key.split(",", 1)
    last = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""

    first_parts = []
    for w in rest.split():
        if norm(w) in AGENCY_KEYWORDS:
            break
        first_parts.append(w)

    prefix = last + ", " + " ".join(first_parts) if first_parts else last
    return norm(prefix).rstrip(",").strip()


class PDFOrganizer:
    def __init__(self):
        self.mapping: dict[str, list[str]] = {}
        self.word_index: dict[frozenset, list[str]] = defaultdict(list)
        self.prefix_index: dict[str, list[str]] = defaultdict(list)
        self.core_prefix_index: dict[str, list[str]] = defaultdict(list)
        self.all_prefixes: list[tuple[str, str]] = []
        self.all_wordsets: list[tuple[frozenset, str]] = []
        self.all_core_prefixes: list[tuple[str, str]] = []
        self._all_prefix_strings: list[str] = []  # for difflib fuzzy

    def load(self):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            self.mapping = json.load(f)

        for key in self.mapping:
            ws = name_words_from_key(key)
            pf = name_prefix_from_key(key)
            cp = _core_prefix(pf)

            self.word_index[ws].append(key)
            self.prefix_index[pf].append(key)
            self.core_prefix_index[cp].append(key)
            self.all_prefixes.append((pf, key))
            self.all_core_prefixes.append((cp, key))
            self.all_wordsets.append((ws, key))
            if pf not in self._all_prefix_strings:
                self._all_prefix_strings.append(pf)

        n_ws = len(self.word_index)
        n_pf = len(self.prefix_index)
        print(f"Loaded {len(self.mapping)} person keys  |  {n_ws} unique word-sets  |  {n_pf} unique prefixes")

    # ------------------------------------------------------------------
    # Filename parsing
    # ------------------------------------------------------------------

    def parse_filename(self, filename: str):
        """Return (word_set | None, prefix | None, doc_descriptions: list[str])."""
        stem = Path(filename).stem
        clean = strip_copy_suffix(stem)

        # Pattern A: ...final278 / ...AMENDEDfinal278 / ...finalAMENDED278
        m = re.match(r"^(.+?)\s+((?:AMENDED)?final(?:AMENDED)?278)", clean, re.IGNORECASE)
        if m:
            amended = "amended" in m.group(2).lower()
            desc = "nominee 278 (amended" if amended else "nominee 278"
            return self._name_and_descs(m.group(1), [desc])

        # Pattern B: ...OGE[-\s]YYYY-NNN...
        m = re.match(r"^(.+?)\s+(OGE[\s-]+\d{4}[\s-].+)$", clean, re.IGNORECASE)
        if m:
            oge = re.sub(r"\s+", "-", m.group(2).strip()).lower()
            return self._name_and_descs(m.group(1), [f"certificate of divestiture {oge}"])

        # Pattern C: ...YYYY 278PC...
        m = re.match(r"^(.+?)\s+(\d{4})\s+278PC", clean, re.IGNORECASE)
        if m:
            return self._name_and_descs(m.group(1), [f"presidential candidate {m.group(2)}"])

        # Pattern D: ALL-CAPS with dash separator (e.g. OLIVER DAVIS VALERIA - PAS_DAEO ...)
        if re.match(r"^[A-Z ]{5,}\s*-", clean):
            return self._parse_allcaps(clean)

        # Pattern E: Hyphenated First-Middle-Last-Date-Type
        if "-" in clean and re.search(r"\d", clean):
            return self._parse_hyphenated(clean)

        return None, None, []

    def _name_and_descs(self, name_str: str, descs: list[str]):
        """Build (word_set, prefix, descs) from a name string (may or may not have comma)."""
        name_str = name_str.strip().rstrip(",").strip()
        words = re.split(r"[,\s]+", name_str)
        words = [w for w in words if w]
        ws = frozenset(_expand_words(words))

        prefix = None
        if "," in name_str:
            # Handle extra commas for suffixes: "Barrack, Jr., Thomas"
            comma_parts = name_str.split(",")
            comma_parts = [p.strip() for p in comma_parts if p.strip()]
            # Filter out name suffixes from parts
            filtered = [p for p in comma_parts if norm(p) not in NAME_SUFFIXES]
            if len(filtered) >= 2:
                last = filtered[0]
                first = " ".join(filtered[1:])
            elif filtered:
                last = filtered[0]
                first = ""
            else:
                last = comma_parts[0]
                first = ""
            prefix = norm(f"{last}, {first}").rstrip(",").strip()
        return ws, prefix, descs

    def _parse_hyphenated(self, stem: str):
        # Normalize stray periods between name and date: "Patman.01" -> "Patman-01"
        stem = re.sub(r"\.(\d{2}[.\-])", r"-\1", stem)
        parts = stem.split("-")

        name_parts: list[str] = []
        date_idx = None
        for i, p in enumerate(parts):
            if re.match(r"^\d", p):
                date_idx = i
                break
            name_parts.append(p)

        if not name_parts:
            return None, None, []

        ws = frozenset(_expand_words(name_parts))
        last = name_parts[-1]
        first = " ".join(name_parts[:-1])
        prefix = norm(f"{last}, {first}") if first else norm(last)

        rest_str = "-".join(parts[date_idx:]) if date_idx is not None else ""
        descs = self._doc_descs_from_type_str(rest_str)
        return ws, prefix, descs

    def _parse_allcaps(self, stem: str):
        m = re.match(r"^([A-Z][A-Z ]+?)\s*-", stem)
        if not m:
            return None, None, []
        name_parts = m.group(1).strip().split()
        ws = frozenset(norm(w) for w in name_parts if norm(w))

        descs: list[str] = []
        date_m = re.search(r"(\d{4})-(\d{2})-(\d{2})", stem)
        if date_m and "278-T" in stem:
            y, mo, d = date_m.group(1), date_m.group(2), date_m.group(3)
            descs.append(f"278 transaction {mo}/{d}/{y}")
        return ws, None, descs

    def _doc_descs_from_type_str(self, type_str: str) -> list[str]:
        """From 'MM.DD.YYYY-278T' or 'YYYY-278' extract possible JSON doc descriptions."""
        descs: list[str] = []
        if not type_str:
            return descs

        # Try MM.DD.YYYY (or MM-DD-YYYY) first
        dm = re.match(r"(\d{2})[.\-](\d{2})[.\-](\d{4})[.\-]?(.*)", type_str)
        if dm:
            date_str = f"{dm.group(1)}/{dm.group(2)}/{dm.group(3)}"
            raw_type = dm.group(4).strip("-. ") if dm.group(4) else ""
        else:
            ym = re.match(r"(\d{4})[.\-]?(.*)", type_str)
            if not ym:
                return descs
            date_str = ym.group(1)
            raw_type = ym.group(2).strip("-. ") if ym.group(2) else ""

        doc_type = re.sub(r"(_\d+)+$", "", raw_type)
        doc_type = re.sub(r"\s*\(\d+\)$", "", doc_type)
        doc_type = doc_type.strip().upper()

        if doc_type in ("278T", "378T"):
            if "/" in date_str:
                descs.append(f"278 transaction {date_str}")
        elif doc_type == "278TERM":
            descs.extend(["termination", "annual term"])
        elif doc_type in ("278", ""):
            if len(date_str) == 4:
                descs.append(f"annual - {date_str}")
            elif "/" in date_str:
                year = date_str.split("/")[-1]
                descs.append(f"annual - {year}")
                descs.append(f"278 transaction {date_str}")
        elif doc_type == "278NE":
            descs.extend(["nominee 278", "new entrant"])
        elif doc_type.startswith("278ANNU"):
            if len(date_str) == 4:
                descs.append(f"annual - {date_str}")
            descs.append("annual term")
        elif doc_type.startswith("278PC"):
            if len(date_str) == 4:
                descs.append(f"presidential candidate {date_str}")
        elif "TERMDRAFT" in doc_type:
            descs.extend(["termination", "termination (pending final oge disposition)"])
        elif "NEDRAFT" in doc_type:
            descs.extend(["nominee 278", "new entrant", "new entrant (pending final oge disposition)"])
        elif doc_type.startswith("278AMENDED") or doc_type == "278AMEND":
            if len(date_str) == 4:
                descs.append(f"annual - {date_str}")

        return descs

    # ------------------------------------------------------------------
    # Matching engine
    # ------------------------------------------------------------------

    def match_file(self, filename: str) -> str | None:
        ws, prefix, descs = self.parse_filename(filename)
        if ws is None or len(ws) == 0:
            return None

        # Strategy 1: exact prefix
        if prefix:
            cands = self.prefix_index.get(prefix, [])
            result = self._resolve(cands, descs)
            if result:
                return result

        # Strategy 2: exact word-set
        cands = self.word_index.get(ws, [])
        result = self._resolve(cands, descs)
        if result:
            return result

        # Strategy 3: partial prefix (starts-with either direction)
        if prefix:
            cands = []
            for kp, key in self.all_prefixes:
                if kp.startswith(prefix) or prefix.startswith(kp):
                    cands.append(key)
            result = self._resolve(cands, descs)
            if result:
                return result

        # Strategy 4: core prefix (drop single-letter middle initials)
        if prefix:
            cp = _core_prefix(prefix)
            cands = self.core_prefix_index.get(cp, [])
            result = self._resolve(cands, descs)
            if result:
                return result
            # Also try partial core prefix
            cands = []
            for kcp, key in self.all_core_prefixes:
                if kcp.startswith(cp) or cp.startswith(kcp):
                    cands.append(key)
            result = self._resolve(cands, descs)
            if result:
                return result

        # Strategy 5: subset word-set (file ⊆ key or key ⊆ file, min 2 shared)
        if len(ws) >= 2:
            cands = []
            for kws, key in self.all_wordsets:
                if ws <= kws or kws <= ws:
                    if len(ws & kws) >= 2:
                        cands.append(key)
            result = self._resolve(cands, descs)
            if result:
                return result

        # Strategy 6: fuzzy prefix matching via difflib (catches typos)
        if prefix and len(prefix) >= 5:
            close = difflib.get_close_matches(prefix, self._all_prefix_strings, n=3, cutoff=0.78)
            if close:
                cands = []
                for c in close:
                    cands.extend(self.prefix_index.get(c, []))
                result = self._resolve(cands, descs)
                if result:
                    return result

        return None

    def _resolve(self, candidates: list[str], descs: list[str]) -> str | None:
        if not candidates:
            return None
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1:
            return unique[0]

        # If all candidates share the same normalized name (e.g. Unicode apostrophe
        # variants), they represent the same person — pick the first.
        if len({name_prefix_from_key(k) for k in unique}) == 1:
            if not descs:
                return unique[0]
            # Still try doc matching to pick the most specific key
            matched = []
            for key in unique:
                key_docs = {d.lower().strip() for d in self.mapping[key]}
                for desc in descs:
                    if desc.lower().strip() in key_docs:
                        matched.append(key)
                        break
            return matched[0] if matched else unique[0]

        if descs:
            matched = []
            for key in unique:
                key_docs = {d.lower().strip() for d in self.mapping[key]}
                for desc in descs:
                    if desc.lower().strip() in key_docs:
                        matched.append(key)
                        break
            if len(matched) == 1:
                return matched[0]

            # Fallback: partial OGE-number matching
            for key in unique:
                key_docs_lower = " ".join(self.mapping[key]).lower()
                for desc in descs:
                    oge_m = re.search(r"oge-\d{4}-\d+", desc.lower())
                    if oge_m and oge_m.group(0) in key_docs_lower:
                        return key

        return None

    # ------------------------------------------------------------------
    # Folder naming
    # ------------------------------------------------------------------

    @staticmethod
    def sanitize_folder_name(key: str) -> str:
        name = key.replace("/", "_").replace(":", "_")
        if len(name) > 200:
            name = name[:200]
        return name

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, dry_run: bool = True):
        self.load()

        pdfs = sorted(f for f in SOURCE_DIR.iterdir() if f.is_file() and f.suffix.lower() == ".pdf")
        print(f"Found {len(pdfs)} PDFs to organize\n")

        matched_count = 0
        unmatched_files: list[str] = []
        person_counts: dict[str, int] = defaultdict(int)

        for i, pdf in enumerate(pdfs, 1):
            key = self.match_file(pdf.name)

            if key:
                folder = SOURCE_DIR / self.sanitize_folder_name(key)
                if not dry_run:
                    folder.mkdir(exist_ok=True)
                    shutil.move(str(pdf), str(folder / pdf.name))
                matched_count += 1
                person_counts[key] += 1
            else:
                folder = SOURCE_DIR / UNMATCHED_FOLDER
                if not dry_run:
                    folder.mkdir(exist_ok=True)
                    shutil.move(str(pdf), str(folder / pdf.name))
                unmatched_files.append(pdf.name)

            if i % 2000 == 0 or i == len(pdfs):
                print(f"  [{i:>6}/{len(pdfs)}]  matched so far: {matched_count}")

        total = matched_count + len(unmatched_files)
        print(f"\n{'=' * 60}")
        print(f"  Matched  : {matched_count:>6}  ({matched_count/total*100:.1f}%)")
        print(f"  Unmatched: {len(unmatched_files):>6}  ({len(unmatched_files)/total*100:.1f}%)")
        print(f"  Total    : {total:>6}")
        print(f"  Folders  : {len(person_counts):>6}")
        print(f"{'=' * 60}")

        if unmatched_files:
            print(f"\nUnmatched files ({len(unmatched_files)}):")
            for f in unmatched_files[:80]:
                print(f"  - {f}")
            if len(unmatched_files) > 80:
                print(f"  ... and {len(unmatched_files) - 80} more")

        if dry_run:
            print("\n** DRY RUN — no files were moved. Run with --execute to move files. **")
        else:
            print(f"\nDone. Files organized under: {SOURCE_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Organize PDFs by person (requested_documents.json)")
    parser.add_argument("--execute", action="store_true", help="Actually move files (default is dry run)")
    args = parser.parse_args()

    organizer = PDFOrganizer()
    organizer.run(dry_run=not args.execute)


if __name__ == "__main__":
    main()
