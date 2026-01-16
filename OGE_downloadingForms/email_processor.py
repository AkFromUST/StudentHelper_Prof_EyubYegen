#!/usr/bin/env python3
"""
OGE Email Processor - Phase 2

Processes emails from OGE, downloads PDF attachments, and organizes them
into a directory structure based on the peopleToPage.json mapping.

Structure: ~/Documents/Page_XX/PersonName/filename.pdf
"""

import os
import re
import json
import csv
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List, Set

import config

# Try to import thefuzz for fuzzy matching, fall back to simple matching if not available
try:
    from thefuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    print("⚠️  thefuzz not installed. Using simple string matching.")
    print("   Install with: pip install thefuzz python-Levenshtein")

# Configuration
MAPPING_FILE = "peopleToPage.json"
DOWNLOADS_ROOT = Path(__file__).parent / "OGE_Documents"  # ./OGE_Documents
UNMATCHED_FOLDER = "_Unmatched"
OGE_SENDER = "No_Reply/USOGE.OGEX5@oge.gov"

# Output CSV files
MATCHED_CSV = "matched_people.csv"
UNMATCHED_CSV = "unmatched_documents.csv"


class EmailProcessor:
    """Processes OGE emails and organizes attachments."""
    
    def __init__(self):
        self.email_address = config.GMAIL_USERNAME
        self.app_password = config.GMAIL_PASSWORD
        self.mapping: Dict[str, int] = {}
        self.downloads_root = DOWNLOADS_ROOT
        self.processed_count = 0
        self.unmatched_count = 0
        self.skipped_count = 0  # Files that already exist
        
        # Track matched people and unmatched documents for CSV export
        self.matched_people: Dict[str, List[str]] = {}  # person_name -> list of filenames
        self.unmatched_documents: List[str] = []  # list of unmatched filenames
        
        if not self.email_address or not self.app_password:
            raise ValueError(
                "Missing credentials. Please set GMAIL_USERNAME and GMAIL_PASSWORD in config.py"
            )
    
    def log(self, message: str, level: str = "info"):
        """Simple logging to console."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "start": "🚀", "download": "📥"}
        icon = icons.get(level, "•")
        print(f"{icon} [{timestamp}] {message}")
    
    def load_mapping(self) -> bool:
        """Load the people to page mapping from JSON file."""
        try:
            mapping_path = Path(__file__).parent / MAPPING_FILE
            if not mapping_path.exists():
                self.log(f"Mapping file not found: {mapping_path}", "error")
                return False
            
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.mapping = json.load(f)
            
            self.log(f"Loaded {len(self.mapping)} entries from {MAPPING_FILE}", "success")
            return True
        except Exception as e:
            self.log(f"Error loading mapping: {e}", "error")
            return False
    
    def parse_filename_to_name(self, filename: str) -> Tuple[str, str]:
        """Extract last name and first name from attachment filename.
        
        Filename format: FirstName-MiddleInitial-LastName-Year-Type.pdf
        
        Examples:
        - James-Abbott-2022-278TERM.pdf -> last_name="Abbott", first_name="James"
        - Jessica-D-Aber-2025-278TERM.pdf -> last_name="Aber", first_name="Jessica D"
        - Erhard-R-Chorle-06.09.2025-278T.pdf -> last_name="Chorle", first_name="Erhard R"
        
        The LAST part before numbers is the LAST NAME.
        Everything before that is the first name (+ middle initial).
        
        Returns:
            Tuple of (last_name, first_name)
        """
        # Remove file extension
        name_part = Path(filename).stem
        
        # Split by hyphen
        parts = name_part.split('-')
        
        if len(parts) < 2:
            return (parts[0] if parts else "", "")
        
        # Find where numbers start (year or date)
        # The part RIGHT BEFORE numbers is the LAST NAME
        name_parts = []
        for part in parts:
            # Stop when we hit a part that starts with a digit (year/date)
            if re.match(r'^\d', part):
                break
            name_parts.append(part)
        
        if len(name_parts) < 2:
            # Only one name part found
            return (name_parts[0] if name_parts else "", "")
        
        # Last name is the LAST part before numbers
        last_name = name_parts[-1]
        
        # First name is everything before the last name (joined with space)
        first_name = " ".join(name_parts[:-1])
        
        return (last_name, first_name)
    
    def find_matching_person(self, last_name: str, first_name: str) -> Optional[Tuple[str, int]]:
        """Find the matching person in the mapping using fuzzy matching.
        
        Args:
            last_name: Extracted last name from filename
            first_name: Extracted first name from filename
            
        Returns:
            Tuple of (full_name_key, page_number) or None if not found
        """
        # Construct the search key in "Last, First" format
        search_key = f"{last_name}, {first_name}".lower()
        
        best_match = None
        best_score = 0
        
        for key, page in self.mapping.items():
            key_lower = key.lower()
            
            # Exact match (case-insensitive)
            if key_lower == search_key:
                return (key, page)
            
            # Check if last name matches exactly
            key_last = key.split(',')[0].strip().lower()
            if key_last == last_name.lower():
                # Last name matches, check first name
                key_first_part = key.split(',')[1].strip().lower() if ',' in key else ""
                
                # Exact first name match
                if key_first_part.startswith(first_name.lower()):
                    return (key, page)
                
                # Use fuzzy matching if available
                if FUZZY_AVAILABLE:
                    score = fuzz.ratio(first_name.lower(), key_first_part.split()[0] if key_first_part else "")
                    if score > best_score and score >= 70:  # 70% threshold
                        best_score = score
                        best_match = (key, page)
                else:
                    # Simple partial match
                    if first_name.lower()[:3] in key_first_part:
                        return (key, page)
        
        return best_match
    
    def sanitize_folder_name(self, name: str) -> str:
        """Sanitize a string for use as a folder name."""
        # Replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        return sanitized[:100]
    
    def get_target_path(self, filename: str) -> Tuple[Path, str]:
        """Determine the target path for a downloaded file.
        
        Returns:
            Tuple of (target_directory, matched_person_name or "Unmatched")
        """
        last_name, first_name = self.parse_filename_to_name(filename)
        
        if not last_name:
            # Can't parse name, put in unmatched
            target_dir = self.downloads_root / UNMATCHED_FOLDER
            return (target_dir, "Unmatched")
        
        # Try to find matching person
        match = self.find_matching_person(last_name, first_name)
        
        if match:
            person_name, page_number = match
            # Create path: ~/Documents/Page_XX/PersonName/
            page_folder = f"Page_{page_number:02d}"
            person_folder = self.sanitize_folder_name(person_name)
            target_dir = self.downloads_root / page_folder / person_folder
            return (target_dir, person_name)
        else:
            # No match found
            target_dir = self.downloads_root / UNMATCHED_FOLDER
            return (target_dir, "Unmatched")
    
    def connect_to_gmail(self) -> Optional[imaplib.IMAP4_SSL]:
        """Connect to Gmail via IMAP."""
        try:
            self.log("Connecting to Gmail...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(self.email_address, self.app_password)
            self.log("Connected to Gmail", "success")
            return mail
        except Exception as e:
            self.log(f"Failed to connect to Gmail: {e}", "error")
            return None
    
    def is_from_oge(self, from_address: str) -> bool:
        """Check if the email is from OGE."""
        return OGE_SENDER.lower() in from_address.lower()
    
    def decode_header_value(self, value) -> str:
        """Decode email header value."""
        if value is None:
            return ""
        
        decoded_parts = decode_header(value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding or 'utf-8', errors='replace')
            else:
                result += part
        return result
    
    def save_attachment(self, part, target_dir: Path, filename: str) -> Tuple[bool, str]:
        """Save an email attachment to the target directory.
        
        Returns:
            Tuple of (success: bool, status: str)
            - status can be: "saved", "skipped" (already exists), "error"
        """
        try:
            # Create directory if it doesn't exist
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Get file path
            file_path = target_dir / filename
            
            # Skip if file already exists
            if file_path.exists():
                return (True, "skipped")
            
            # Save the file
            payload = part.get_payload(decode=True)
            if payload:
                with open(file_path, 'wb') as f:
                    f.write(payload)
                return (True, "saved")
            return (False, "error")
        except Exception as e:
            self.log(f"Error saving attachment: {e}", "error")
            return (False, "error")
    
    def process_email(self, mail: imaplib.IMAP4_SSL, email_id: bytes) -> int:
        """Process a single email and download its attachments.
        
        Returns:
            Number of attachments downloaded
        """
        downloaded = 0
        
        try:
            # Fetch the email
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                return 0
            
            # Parse email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Get sender
            from_addr = self.decode_header_value(msg.get("From", ""))
            subject = self.decode_header_value(msg.get("Subject", ""))
            
            # Check if from OGE
            if not self.is_from_oge(from_addr):
                return 0
            
            self.log(f"Processing email: {subject[:50]}...", "info")
            
            # Process attachments
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                
                filename = part.get_filename()
                if not filename:
                    continue
                
                # Decode filename if needed
                filename = self.decode_header_value(filename)
                
                # Only process PDF files
                if not filename.lower().endswith('.pdf'):
                    continue
                
                # Determine target path
                target_dir, matched_name = self.get_target_path(filename)
                
                # Save attachment
                success, status = self.save_attachment(part, target_dir, filename)
                
                if success:
                    if status == "skipped":
                        self.skipped_count += 1
                        self.log(f"⏭️  SKIPPED (exists): {filename}", "info")
                        # Still track for CSV even if skipped
                        if matched_name != "Unmatched":
                            if matched_name not in self.matched_people:
                                self.matched_people[matched_name] = []
                            if filename not in self.matched_people[matched_name]:
                                self.matched_people[matched_name].append(filename)
                        else:
                            if filename not in self.unmatched_documents:
                                self.unmatched_documents.append(filename)
                    elif matched_name == "Unmatched":
                        downloaded += 1
                        self.unmatched_count += 1
                        self.unmatched_documents.append(filename)
                        self.log(f"📁 UNMATCHED: {filename} -> {target_dir}", "warning")
                    else:
                        downloaded += 1
                        self.processed_count += 1
                        # Track matched person
                        if matched_name not in self.matched_people:
                            self.matched_people[matched_name] = []
                        self.matched_people[matched_name].append(filename)
                        self.log(f"📥 Saved: {filename} -> {matched_name} (Page {self.mapping.get(matched_name, '?')})", "download")
            
            return downloaded
            
        except Exception as e:
            self.log(f"Error processing email: {e}", "error")
            return 0
    
    def fetch_and_process_emails(self, unread_only: bool = True, mark_as_read: bool = False) -> int:
        """Fetch and process OGE emails.
        
        Args:
            unread_only: If True, only process unread emails
            mark_as_read: If True, mark processed emails as read
            
        Returns:
            Total number of attachments downloaded
        """
        mail = self.connect_to_gmail()
        if not mail:
            return 0
        
        total_downloaded = 0
        
        try:
            # Select inbox
            mail.select("INBOX")
            
            # Search for emails
            if unread_only:
                # Search for unread emails from OGE
                search_criteria = f'(UNSEEN FROM "{OGE_SENDER}")'
            else:
                # Search for all emails from OGE
                search_criteria = f'(FROM "{OGE_SENDER}")'
            
            self.log(f"Searching for emails with criteria: {search_criteria}")
            status, messages = mail.search(None, search_criteria)
            
            if status != "OK":
                self.log("Failed to search emails", "error")
                return 0
            
            email_ids = messages[0].split()
            self.log(f"Found {len(email_ids)} email(s) to process", "info")
            
            for email_id in email_ids:
                downloaded = self.process_email(mail, email_id)
                total_downloaded += downloaded
                
                # Mark as read if requested and we downloaded something
                if mark_as_read and downloaded > 0:
                    mail.store(email_id, '+FLAGS', '\\Seen')
            
            return total_downloaded
            
        except Exception as e:
            self.log(f"Error fetching emails: {e}", "error")
            return 0
        finally:
            try:
                mail.logout()
            except:
                pass
    
    def save_csv_reports(self):
        """Save CSV reports for matched people and unmatched documents."""
        csv_dir = Path(__file__).parent
        
        # Save matched people CSV
        matched_csv_path = csv_dir / MATCHED_CSV
        try:
            with open(matched_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Person Name', 'Page Number', 'Document Count', 'Documents'])
                
                for person_name, documents in sorted(self.matched_people.items()):
                    page_number = self.mapping.get(person_name, 'N/A')
                    doc_count = len(documents)
                    docs_list = "; ".join(documents)
                    writer.writerow([person_name, page_number, doc_count, docs_list])
            
            self.log(f"Saved {len(self.matched_people)} matched people to {MATCHED_CSV}", "success")
        except Exception as e:
            self.log(f"Error saving matched CSV: {e}", "error")
        
        # Save unmatched documents CSV
        unmatched_csv_path = csv_dir / UNMATCHED_CSV
        try:
            with open(unmatched_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Document Name'])
                
                for doc_name in sorted(self.unmatched_documents):
                    writer.writerow([doc_name])
            
            self.log(f"Saved {len(self.unmatched_documents)} unmatched documents to {UNMATCHED_CSV}", "success")
        except Exception as e:
            self.log(f"Error saving unmatched CSV: {e}", "error")
    
    def run(self, unread_only: bool = True, mark_as_read: bool = False):
        """Main execution method."""
        self.log("=== OGE Email Processor ===", "start")
        self.log(f"Downloads root: {self.downloads_root}")
        
        # Load mapping
        if not self.load_mapping():
            return
        
        # Process emails
        total = self.fetch_and_process_emails(unread_only, mark_as_read)
        
        # Save CSV reports
        self.save_csv_reports()
        
        # Summary
        self.log("=== PROCESSING COMPLETE ===", "success")
        self.log(f"New files downloaded: {total}", "info")
        self.log(f"Matched to people: {self.processed_count}", "success")
        self.log(f"Unmatched: {self.unmatched_count}", "warning" if self.unmatched_count > 0 else "info")
        self.log(f"Skipped (already exist): {self.skipped_count}", "info")
        self.log(f"Files saved to: {self.downloads_root}", "info")
        self.log(f"CSV reports: {MATCHED_CSV}, {UNMATCHED_CSV}", "info")


def main():
    """Entry point for the script."""
    import argparse
    parser = argparse.ArgumentParser(description='OGE Email Processor - Phase 2')
    parser.add_argument('--all', action='store_true', help='Process all emails (not just unread)')
    parser.add_argument('--mark-read', action='store_true', help='Mark processed emails as read')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    args = parser.parse_args()
    
    print("=" * 60)
    print("OGE Email Processor - Phase 2")
    print("=" * 60)
    print(f"Gmail account: {config.GMAIL_USERNAME}")
    print(f"Mapping file: {MAPPING_FILE}")
    print(f"Downloads to: {DOWNLOADS_ROOT}")
    print(f"Process: {'All emails' if args.all else 'Unread only'}")
    print(f"Mark as read: {'Yes' if args.mark_read else 'No'}")
    print("=" * 60)
    print()
    print("This script will:")
    print("   1. Connect to Gmail")
    print(f"   2. Fetch emails from: {OGE_SENDER}")
    print("   3. Download PDF attachments")
    print("   4. Organize files by Page/PersonName")
    print("   5. Put unmatched files in _Unmatched folder")
    print()
    
    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")
    
    try:
        processor = EmailProcessor()
        processor.run(unread_only=not args.all, mark_as_read=args.mark_read)
    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        return


if __name__ == "__main__":
    main()

