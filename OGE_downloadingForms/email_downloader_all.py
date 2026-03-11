#!/usr/bin/env python3
"""
OGE Email Downloader - All Attachments

Reads emails from the OGE sender and downloads every PDF attachment into
a single flat folder: ./Automation_Script_Downloads_notMatched/

No name matching, no sub-folders, no mapping required.
Duplicate filenames are handled by appending a counter (file.pdf -> file_1.pdf).
"""

import os
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from datetime import datetime
from typing import Optional

import config

# Configuration
DOWNLOADS_FOLDER = Path(__file__).parent / "Automation_Script_Downloads_notMatched"
OGE_SENDER = "No_Reply/USOGE.OGEX5@oge.gov"


class AllAttachmentsDownloader:
    """Downloads all PDF attachments from OGE emails into a single folder."""

    def __init__(self):
        self.email_address = config.GMAIL_USERNAME
        self.app_password = config.GMAIL_PASSWORD
        self.downloads_folder = DOWNLOADS_FOLDER
        self.downloaded_count = 0
        self.duplicate_count = 0

        if not self.email_address:
            raise ValueError(
                "Missing GMAIL_USERNAME. Please set GMAIL_USERNAME in config.py"
            )

    def log(self, message: str, level: str = "info"):
        """Simple console logger."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "start": "🚀",
            "download": "📥",
            "duplicate": "🔄",
        }
        icon = icons.get(level, "•")
        print(f"{icon} [{timestamp}] {message}")

    def decode_header_value(self, value) -> str:
        """Decode an email header value."""
        if value is None:
            return ""
        decoded_parts = decode_header(value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding or "utf-8", errors="replace")
            else:
                result += part
        return result

    def get_unique_filename(self, filename: str) -> str:
        """Return a unique filename inside the downloads folder.

        If filename.pdf already exists, returns filename_1.pdf, then
        filename_2.pdf, etc.
        """
        file_path = self.downloads_folder / filename
        if not file_path.exists():
            return filename

        stem = file_path.stem
        ext = file_path.suffix
        counter = 1
        while True:
            new_name = f"{stem}_{counter}{ext}"
            if not (self.downloads_folder / new_name).exists():
                return new_name
            counter += 1

    def save_attachment(self, part, filename: str) -> bool:
        """Save a single attachment to the downloads folder."""
        try:
            self.downloads_folder.mkdir(parents=True, exist_ok=True)

            unique_name = self.get_unique_filename(filename)
            is_duplicate = unique_name != filename

            payload = part.get_payload(decode=True)
            if not payload:
                return False

            file_path = self.downloads_folder / unique_name
            with open(file_path, "wb") as f:
                f.write(payload)

            if is_duplicate:
                self.duplicate_count += 1
                self.log(f"DUPLICATE: {filename} -> {unique_name}", "duplicate")
            else:
                self.log(f"Saved: {unique_name}", "download")

            self.downloaded_count += 1
            return True

        except Exception as e:
            self.log(f"Error saving {filename}: {e}", "error")
            return False

    def connect_to_gmail(self) -> Optional[imaplib.IMAP4_SSL]:
        """Connect to Gmail via IMAP."""
        try:
            self.log("Connecting to Gmail...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            password = self.app_password if self.app_password else ""
            mail.login(self.email_address, password)
            self.log("Connected to Gmail", "success")
            return mail
        except Exception as e:
            self.log(f"Failed to connect to Gmail: {e}", "error")
            return None

    def process_email(self, mail: imaplib.IMAP4_SSL, email_id: bytes) -> int:
        """Process a single email and save all PDF attachments."""
        downloaded = 0
        try:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                return 0

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            from_addr = self.decode_header_value(msg.get("From", ""))
            subject = self.decode_header_value(msg.get("Subject", ""))

            if OGE_SENDER.lower() not in from_addr.lower():
                return 0

            self.log(f"Processing: {subject[:60]}", "info")

            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                filename = self.decode_header_value(filename)

                if not filename.lower().endswith(".pdf"):
                    continue

                if self.save_attachment(part, filename):
                    downloaded += 1

            return downloaded

        except Exception as e:
            self.log(f"Error processing email: {e}", "error")
            return 0

    def fetch_and_process_emails(self, unread_only: bool = True, mark_as_read: bool = False) -> int:
        """Fetch emails from OGE and download all PDF attachments."""
        mail = self.connect_to_gmail()
        if not mail:
            return 0

        total_downloaded = 0
        try:
            mail.select("INBOX")

            if unread_only:
                search_criteria = f'(UNSEEN FROM "{OGE_SENDER}")'
            else:
                search_criteria = f'(FROM "{OGE_SENDER}")'

            self.log(f"Searching: {search_criteria}")
            status, messages = mail.search(None, search_criteria)

            if status != "OK":
                self.log("Failed to search emails", "error")
                return 0

            email_ids = messages[0].split()
            self.log(f"Found {len(email_ids)} email(s) to process", "info")

            for email_id in email_ids:
                downloaded = self.process_email(mail, email_id)
                total_downloaded += downloaded

                if mark_as_read and downloaded > 0:
                    mail.store(email_id, "+FLAGS", "\\Seen")

            return total_downloaded

        except Exception as e:
            self.log(f"Error fetching emails: {e}", "error")
            return 0
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def run(self, unread_only: bool = True, mark_as_read: bool = False):
        """Main execution method."""
        self.log("=== OGE All-Attachments Downloader ===", "start")
        self.log(f"Downloads folder: {self.downloads_folder}")

        total = self.fetch_and_process_emails(unread_only, mark_as_read)

        self.log("=== COMPLETE ===", "success")
        self.log(f"Total files downloaded : {total}", "info")
        self.log(f"Saved as duplicates    : {self.duplicate_count}", "info")
        self.log(f"All files in           : {self.downloads_folder}", "info")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OGE All-Attachments Downloader")
    parser.add_argument("--all", action="store_true", help="Process all emails (not just unread)")
    parser.add_argument("--mark-read", action="store_true", help="Mark processed emails as read")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    print("=" * 60)
    print("OGE All-Attachments Downloader")
    print("=" * 60)
    print(f"Gmail account  : {config.GMAIL_USERNAME}")
    print(f"Sender filter  : {OGE_SENDER}")
    print(f"Downloads to   : {DOWNLOADS_FOLDER}")
    print(f"Process        : {'All emails' if args.all else 'Unread only'}")
    print(f"Mark as read   : {'Yes' if args.mark_read else 'No'}")
    print()
    print("This script will:")
    print("   1. Connect to Gmail")
    print(f"   2. Fetch emails from: {OGE_SENDER}")
    print("   3. Download ALL PDF attachments into one folder")
    print("   4. Handle duplicates by appending a counter (file_1.pdf, etc.)")
    print("   (No name matching or sub-folder organisation)")
    print("=" * 60)
    print()

    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != "y":
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")

    try:
        downloader = AllAttachmentsDownloader()
        downloader.run(unread_only=not args.all, mark_as_read=args.mark_read)
    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")


if __name__ == "__main__":
    main()
