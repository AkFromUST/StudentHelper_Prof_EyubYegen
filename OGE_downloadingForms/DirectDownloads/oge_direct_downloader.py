#!/usr/bin/env python3
"""
OGE Direct Downloader Script

Downloads files that are directly available (no form submission required)
from the OGE website and organizes them into the direct_downloads folder
with separate subdirectories for each individual.

Features:
- Three-level tracking system (for popup files only):
  * seen_rows.json: Tracks processed individuals from popups
  * row_individual.json: Maps rows to their individuals
  * finished_rows.json: Tracks fully completed rows
- Direct table downloads: NOT tracked (same person can have multiple files)
- Popup downloads: Tracked (prevents re-opening popups for same individuals)
- Downloads files marked "(click to download)" from Presidential Nominee system
- Organizes downloads: direct_downloads/<individual_name>/
- Processes pages 1-53 (sorted by Name, filtered by Transaction)
- Skips repeated popup rows efficiently (no popup reopening needed)
"""

import json
import time
import os
import re
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
    UnexpectedAlertPresentException,
    NoAlertPresentException
)
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
BASE_URL = "https://www.oge.gov/Web/OGE.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm"
START_PAGE = 1
END_PAGE = 53
PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT_TIMEOUT = 15

# File paths
SEEN_ROWS_FILE = "seen_rows.json"  # Tracks processed individuals
ROW_INDIVIDUAL_FILE = "row_individual.json"  # Maps rows to individuals
FINISHED_ROWS_FILE = "finished_rows.json"  # Tracks completed rows
DOWNLOADS_ROOT = Path(__file__).parent / "direct_downloads"
PROGRESS_FILE = "direct_download_progress.md"
LOG_FILE = "direct_download_log.csv"


class DirectDownloadLogger:
    """Handles logging for direct downloads."""
    
    def __init__(self):
        self.log_file = Path(__file__).parent / LOG_FILE
        self.progress_file = Path(__file__).parent / PROGRESS_FILE
        self.downloaded_files: List[Dict] = []
        self.skipped_files: List[Dict] = []
        self._init_progress_file()
    
    def _init_progress_file(self):
        """Initialize the progress markdown file."""
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            f.write("# OGE Direct Download Progress\n\n")
            f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Pages:** {START_PAGE} to {END_PAGE}\n\n")
            f.write("---\n\n")
    
    def log(self, message: str, level: str = "info"):
        """Log message to console and progress file."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "start": "🚀", "download": "📥", "skip": "⏭️"}
        icon = icons.get(level, "•")
        
        print(f"{icon} [{timestamp}] {message}")
        
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"- `{timestamp}` {icon} {message}\n")
    
    def log_download(self, name: str, page: int, filename: str, status: str):
        """Log a download attempt."""
        entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'name': name,
            'page': page,
            'filename': filename,
            'status': status
        }
        
        if status == 'downloaded':
            self.downloaded_files.append(entry)
        else:
            self.skipped_files.append(entry)
    
    def save_csv_log(self):
        """Save all logged downloads to CSV."""
        try:
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp', 'name', 'page', 'filename', 'status'])
                writer.writeheader()
                
                for entry in self.downloaded_files + self.skipped_files:
                    writer.writerow(entry)
            
            self.log(f"Saved {len(self.downloaded_files) + len(self.skipped_files)} entries to {LOG_FILE}", "success")
        except Exception as e:
            self.log(f"Error saving CSV log: {e}", "error")
    
    def log_summary(self, total_downloaded: int, total_skipped: int, total_no_download: int, total_seen_skipped: int = 0):
        """Log final summary."""
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"\n## Final Summary\n")
            f.write(f"- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Files downloaded:** {total_downloaded}\n")
            f.write(f"- **Files skipped (already exist):** {total_skipped}\n")
            f.write(f"- **Individuals skipped (already seen):** {total_seen_skipped}\n")
            f.write(f"- **Rows without direct download:** {total_no_download}\n")


class OGEDirectDownloader:
    """Downloads directly available files from OGE website."""
    
    def __init__(self, headless: bool = False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self.current_page = 1
        self.logger = DirectDownloadLogger()
        self.seen_rows: Dict[str, bool] = {}  # Tracks individuals
        self.row_individuals: Dict[str, List[str]] = {}  # Maps rows to individuals
        self.finished_rows: Dict[str, bool] = {}  # Tracks completed rows
        self.downloads_root = DOWNLOADS_ROOT
        
        # Statistics
        self.total_downloaded = 0
        self.total_skipped = 0
        self.total_no_download = 0
        self.total_seen_skipped = 0
    
    def load_seen_rows(self) -> bool:
        """Load the seen individuals tracking from JSON file."""
        try:
            seen_path = Path(__file__).parent / SEEN_ROWS_FILE
            if not seen_path.exists():
                self.logger.log(f"No existing {SEEN_ROWS_FILE} found, starting fresh", "info")
                self.seen_rows = {}
                return True
            
            with open(seen_path, 'r', encoding='utf-8') as f:
                self.seen_rows = json.load(f)
            
            seen_count = sum(1 for v in self.seen_rows.values() if v)
            self.logger.log(f"Loaded {len(self.seen_rows)} individuals from {SEEN_ROWS_FILE} ({seen_count} already processed)", "success")
            return True
        except Exception as e:
            self.logger.log(f"Error loading seen individuals: {e}", "error")
            self.seen_rows = {}
            return True
    
    def save_seen_rows(self):
        """Save the seen individuals tracking to JSON file."""
        try:
            seen_path = Path(__file__).parent / SEEN_ROWS_FILE
            with open(seen_path, 'w', encoding='utf-8') as f:
                json.dump(self.seen_rows, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.log(f"Error saving seen individuals: {e}", "error")
            return False
    
    def load_finished_rows(self) -> bool:
        """Load the finished rows tracking from JSON file."""
        try:
            finished_path = Path(__file__).parent / FINISHED_ROWS_FILE
            if not finished_path.exists():
                self.logger.log(f"No existing {FINISHED_ROWS_FILE} found, starting fresh", "info")
                self.finished_rows = {}
                return True
            
            with open(finished_path, 'r', encoding='utf-8') as f:
                self.finished_rows = json.load(f)
            
            finished_count = sum(1 for v in self.finished_rows.values() if v)
            self.logger.log(f"Loaded {len(self.finished_rows)} rows from {FINISHED_ROWS_FILE} ({finished_count} already finished)", "success")
            return True
        except Exception as e:
            self.logger.log(f"Error loading finished rows: {e}", "error")
            self.finished_rows = {}
            return True
    
    def save_finished_rows(self):
        """Save the finished rows tracking to JSON file."""
        try:
            finished_path = Path(__file__).parent / FINISHED_ROWS_FILE
            with open(finished_path, 'w', encoding='utf-8') as f:
                json.dump(self.finished_rows, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.log(f"Error saving finished rows: {e}", "error")
            return False
    
    def is_row_finished(self, row_name: str) -> bool:
        """Check if a row has been fully processed (all individuals done)."""
        return self.finished_rows.get(row_name, False)
    
    def mark_row_as_finished(self, row_name: str):
        """Mark a row as finished/completely processed."""
        self.finished_rows[row_name] = True
        self.save_finished_rows()
    
    def load_row_individuals(self) -> bool:
        """Load the row-to-individuals mapping from JSON file."""
        try:
            row_ind_path = Path(__file__).parent / ROW_INDIVIDUAL_FILE
            if not row_ind_path.exists():
                self.logger.log(f"No existing {ROW_INDIVIDUAL_FILE} found, starting fresh", "info")
                self.row_individuals = {}
                return True
            
            with open(row_ind_path, 'r', encoding='utf-8') as f:
                self.row_individuals = json.load(f)
            
            self.logger.log(f"Loaded {len(self.row_individuals)} row mappings from {ROW_INDIVIDUAL_FILE}", "success")
            return True
        except Exception as e:
            self.logger.log(f"Error loading row individuals: {e}", "error")
            self.row_individuals = {}
            return True
    
    def save_row_individuals(self):
        """Save the row-to-individuals mapping to JSON file."""
        try:
            row_ind_path = Path(__file__).parent / ROW_INDIVIDUAL_FILE
            with open(row_ind_path, 'w', encoding='utf-8') as f:
                json.dump(self.row_individuals, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.log(f"Error saving row individuals: {e}", "error")
            return False
    
    def get_individuals_for_row(self, row_name: str) -> Optional[List[str]]:
        """Get the list of individuals associated with a row."""
        return self.row_individuals.get(row_name)
    
    def store_individuals_for_row(self, row_name: str, individuals: List[str]):
        """Store the list of individuals for a row."""
        self.row_individuals[row_name] = individuals
        self.save_row_individuals()
    
    def is_individual_seen(self, individual_name: str) -> bool:
        """Check if an individual has already been processed."""
        return self.seen_rows.get(individual_name, False)
    
    def mark_individual_as_seen(self, individual_name: str):
        """Mark an individual as seen/processed."""
        self.seen_rows[individual_name] = True
        self.save_seen_rows()
    
    def setup_driver(self):
        """Initialize the Chrome WebDriver with download settings."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Create default download directory
        default_download = self.downloads_root / "_temp"
        default_download.mkdir(parents=True, exist_ok=True)
        
        prefs = {
            "download.default_directory": str(default_download),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        self.wait = WebDriverWait(self.driver, ELEMENT_WAIT_TIMEOUT)
        
        self.logger.log("Chrome WebDriver initialized", "start")
    
    def dismiss_alert(self):
        """Dismiss any alert dialogs that may appear."""
        try:
            alert = self.driver.switch_to.alert
            alert.accept()
            time.sleep(0.5)
            return True
        except NoAlertPresentException:
            return False
        except Exception:
            return False
    
    def safe_click(self, element, retries: int = 3):
        """Safely click an element with retry logic."""
        for attempt in range(retries):
            try:
                self.dismiss_alert()
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)
                element.click()
                return True
            except UnexpectedAlertPresentException:
                self.dismiss_alert()
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
            except (StaleElementReferenceException, Exception) as e:
                self.dismiss_alert()
                if attempt < retries - 1:
                    time.sleep(0.5)
                else:
                    raise e
        return False
    
    def wait_for_table_load(self):
        """Wait for the table to finish loading."""
        try:
            self.dismiss_alert()
            WebDriverWait(self.driver, 20).until_not(
                EC.presence_of_element_located((By.XPATH, "//td[contains(text(), 'Loading')]"))
            )
            time.sleep(1)
        except TimeoutException:
            pass
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
    
    def navigate_to_main_page(self):
        """Navigate to the OGE main search page."""
        self.logger.log("Navigating to OGE website...")
        self.driver.get(BASE_URL)
        time.sleep(2)
    
    def handle_affirm_banner(self) -> bool:
        """Handle the 'I affirm' legal banner."""
        try:
            self.logger.log("Looking for affirm banner...")
            
            affirm_selectors = [
                "//div[contains(., 'By clicking this banner, I affirm')]",
                "//*[contains(text(), 'I affirm')]",
            ]
            
            for selector in affirm_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            self.safe_click(element)
                            self.logger.log("Clicked affirm banner", "success")
                            time.sleep(2)
                            self.wait_for_table_load()
                            return True
                except NoSuchElementException:
                    continue
            
            self.logger.log("No affirm banner found or already dismissed", "info")
            return True
        except Exception as e:
            self.logger.log(f"Error handling affirm banner: {e}", "warning")
            return True
    
    def filter_by_transaction(self) -> bool:
        """Filter the table to show only Transaction type."""
        try:
            self.dismiss_alert()
            self.logger.log("Filtering by Transaction type...")
            
            type_filter = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Filter Type']"))
            )
            
            type_filter.clear()
            type_filter.send_keys("Transaction")
            
            time.sleep(2)
            self.dismiss_alert()
            self.wait_for_table_load()
            
            self.logger.log("Applied Transaction filter", "success")
            return True
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.filter_by_transaction()
        except Exception as e:
            self.dismiss_alert()
            self.logger.log(f"Error filtering by transaction: {e}", "error")
            return False
    
    def sort_by_name(self) -> bool:
        """Sort the table by Name column (A-Z)."""
        try:
            self.dismiss_alert()
            self.logger.log("Sorting by Name column (A-Z)...")
            
            name_header = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//th[contains(., 'Name')]"))
            )
            
            self.safe_click(name_header)
            time.sleep(2)
            self.dismiss_alert()
            self.wait_for_table_load()
            
            # Check if sorting is ascending
            try:
                self.dismiss_alert()
                name_header = self.driver.find_element(By.XPATH, "//th[contains(., 'Name')]")
                aria_sort = name_header.get_attribute("aria-sort")
                
                if aria_sort == "descending":
                    self.logger.log("Clicking again for ascending order...")
                    self.safe_click(name_header)
                    time.sleep(2)
                    self.dismiss_alert()
                    self.wait_for_table_load()
            except:
                pass
            
            self.logger.log("Sorted by Name column (A-Z)", "success")
            return True
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.sort_by_name()
        except Exception as e:
            self.dismiss_alert()
            self.logger.log(f"Error sorting by name: {e}", "error")
            return False
    
    def navigate_to_page(self, page_number: int) -> bool:
        """Navigate to a specific page number."""
        try:
            self.dismiss_alert()
            
            if self.current_page == page_number:
                return True
            
            self.logger.log(f"Navigating to page {page_number}...")
            
            # Try to click the page number directly
            try:
                self.dismiss_alert()
                page_link = self.driver.find_element(
                    By.XPATH, f"//a[normalize-space()='{page_number}']"
                )
                if page_link.is_displayed():
                    self.safe_click(page_link)
                    time.sleep(2)
                    self.dismiss_alert()
                    self.wait_for_table_load()
                    self.current_page = page_number
                    self.logger.log(f"Navigated to page {page_number}", "success")
                    return True
            except (NoSuchElementException, UnexpectedAlertPresentException):
                self.dismiss_alert()
            
            # Navigate using Next button
            while self.current_page < page_number:
                try:
                    self.dismiss_alert()
                    
                    # Check if target page is now visible
                    try:
                        page_link = self.driver.find_element(
                            By.XPATH, f"//a[normalize-space()='{page_number}']"
                        )
                        if page_link.is_displayed():
                            self.safe_click(page_link)
                            time.sleep(2)
                            self.dismiss_alert()
                            self.wait_for_table_load()
                            self.current_page = page_number
                            self.logger.log(f"Navigated to page {page_number}", "success")
                            return True
                    except (NoSuchElementException, UnexpectedAlertPresentException):
                        self.dismiss_alert()
                    
                    # Click next to advance
                    next_btn = self.driver.find_element(By.XPATH, "//a[contains(text(), 'Next')]")
                    if next_btn.is_displayed():
                        self.safe_click(next_btn)
                        time.sleep(1.5)
                        self.dismiss_alert()
                        self.wait_for_table_load()
                        self.current_page += 1
                        
                        if self.current_page % 5 == 0:
                            self.logger.log(f"Progress: on page {self.current_page}...")
                    else:
                        break
                except UnexpectedAlertPresentException:
                    self.dismiss_alert()
                    continue
                except NoSuchElementException:
                    self.logger.log(f"Could not find Next button at page {self.current_page}", "error")
                    return False
            
            return self.current_page == page_number
            
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.navigate_to_page(page_number)
        except Exception as e:
            self.dismiss_alert()
            self.logger.log(f"Error navigating to page {page_number}: {e}", "error")
            return False
    
    def get_table_rows(self) -> list:
        """Get all data rows from the current table page."""
        try:
            time.sleep(0.5)
            rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
            return rows
        except Exception as e:
            self.logger.log(f"Error getting table rows: {e}", "warning")
            return []
    
    def sanitize_folder_name(self, name: str) -> str:
        """Sanitize a string for use as a folder name."""
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        return sanitized[:100]
    
    def get_target_folder(self, name: str, page_number: int = None) -> Path:
        """Get the target folder for saving a file."""
        person_folder = self.sanitize_folder_name(name)
        
        target_dir = self.downloads_root / person_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        
        return target_dir
    
    def download_file(self, download_link, name: str, page_number: int) -> bool:
        """Download a file directly using requests or Selenium."""
        try:
            # Get the href
            href = download_link.get_attribute('href')
            if not href:
                return False
            
            # Get target folder
            target_folder = self.get_target_folder(name, page_number)
            
            # Extract filename from URL or link text
            link_text = download_link.text.strip()
            if 'Transaction' in link_text:
                # Extract date if present
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', link_text)
                date_str = date_match.group(1).replace('/', '-') if date_match else datetime.now().strftime('%Y%m%d')
                filename = f"{self.sanitize_folder_name(name)}_Transaction_{date_str}.pdf"
            else:
                # Use URL to get filename
                url_filename = href.split('/')[-1].split('?')[0]
                if url_filename.endswith('.pdf'):
                    filename = url_filename
                else:
                    filename = f"{self.sanitize_folder_name(name)}_document.pdf"
            
            # Check if file already exists
            target_path = target_folder / filename
            if target_path.exists():
                self.logger.log(f"⏭️  SKIPPED (exists): {filename} for {name}", "skip")
                self.logger.log_download(name, page_number, filename, 'skipped')
                self.total_skipped += 1
                return True
            
            # Store main window
            main_window = self.driver.current_window_handle
            
            # Open link in new tab to trigger download
            self.driver.execute_script("window.open(arguments[0], '_blank');", href)
            time.sleep(2)
            
            # Switch to new tab
            new_tabs = [h for h in self.driver.window_handles if h != main_window]
            if new_tabs:
                self.driver.switch_to.window(new_tabs[0])
                time.sleep(3)
                
                # Try to get the PDF content via JavaScript or just let it download
                # For PDFs that open in browser, we need to save them
                try:
                    # Check if it's a PDF viewer
                    current_url = self.driver.current_url
                    
                    if '.pdf' in current_url.lower():
                        # Use CDP to download
                        import urllib.request
                        urllib.request.urlretrieve(current_url, str(target_path))
                        self.logger.log(f"📥 Downloaded: {filename} for {name}", "download")
                        self.logger.log_download(name, page_number, filename, 'downloaded')
                        self.total_downloaded += 1
                except Exception as e:
                    self.logger.log(f"Download method fallback for {filename}: {str(e)[:50]}", "warning")
                
                # Close the tab
                try:
                    self.driver.close()
                except:
                    pass
                
                # Switch back to main window
                self.driver.switch_to.window(main_window)
            
            # Check if file was downloaded to temp folder and move it
            temp_folder = self.downloads_root / "_temp"
            time.sleep(2)
            
            # Find any new PDF in temp folder
            for f in temp_folder.glob("*.pdf"):
                if f.is_file():
                    # Move to target folder
                    import shutil
                    dest_path = target_folder / f.name
                    if not dest_path.exists():
                        shutil.move(str(f), str(dest_path))
                        self.logger.log(f"📥 Downloaded: {f.name} for {name}", "download")
                        self.logger.log_download(name, page_number, f.name, 'downloaded')
                        self.total_downloaded += 1
                        return True
            
            return True
            
        except Exception as e:
            self.logger.log(f"Error downloading file for {name}: {e}", "error")
            return False
    
    def close_all_extra_tabs(self, main_window: str):
        """Close all tabs except the main window."""
        try:
            self.driver.switch_to.window(main_window)
            time.sleep(0.3)
            
            handles_to_close = [h for h in self.driver.window_handles if h != main_window]
            for handle in handles_to_close:
                try:
                    self.driver.switch_to.window(handle)
                    try:
                        self.driver.switch_to.alert.dismiss()
                    except:
                        pass
                    self.driver.close()
                except:
                    pass
            
            self.driver.switch_to.window(main_window)
            return True
        except Exception as e:
            self.logger.log(f"Error closing tabs: {e}", "warning")
            return False
    
    def download_from_popup(self, name: str, page_number: int) -> int:
        """Download all directly available files from the popup.
        
        Returns:
            Number of files downloaded
        """
        downloaded_count = 0
        
        try:
            # Look for "(click to download)" links in the popup
            download_links = self.driver.find_elements(
                By.XPATH, "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'click to download')]"
            )
            
            if not download_links:
                return 0
            
            self.logger.log(f"Found {len(download_links)} downloadable files in popup for {name}", "info")
            
            # Get target folder
            target_folder = self.get_target_folder(name, page_number)
            
            # Collect all href links first to avoid stale element issues
            links_to_download = []
            for link in download_links:
                try:
                    href = link.get_attribute('href')
                    link_text = link.text.strip()
                    if href:
                        links_to_download.append((href, link_text))
                except:
                    continue
            
            # Store current window
            popup_window = self.driver.current_window_handle
            
            for href, link_text in links_to_download:
                try:
                    # Extract filename from link text
                    # Format: "Ethics Agreement (click to download)" -> "Ethics_Agreement"
                    clean_name = link_text.replace('(click to download)', '').strip()
                    clean_name = self.sanitize_folder_name(clean_name)
                    filename = f"{self.sanitize_folder_name(name)}_{clean_name}.pdf"
                    
                    target_path = target_folder / filename
                    
                    # Skip if already exists
                    if target_path.exists():
                        self.logger.log(f"⏭️  SKIPPED (exists): {filename}", "skip")
                        self.logger.log_download(name, page_number, filename, 'skipped')
                        self.total_skipped += 1
                        continue
                    
                    # Download using urllib
                    import urllib.request
                    try:
                        urllib.request.urlretrieve(href, str(target_path))
                        self.logger.log(f"📥 Downloaded: {filename}", "download")
                        self.logger.log_download(name, page_number, filename, 'downloaded')
                        self.total_downloaded += 1
                        downloaded_count += 1
                    except Exception as e:
                        # Try opening in new tab as fallback
                        self.driver.execute_script("window.open(arguments[0], '_blank');", href)
                        time.sleep(2)
                        
                        new_tabs = [h for h in self.driver.window_handles if h != popup_window]
                        if new_tabs:
                            self.driver.switch_to.window(new_tabs[-1])
                            time.sleep(2)
                            
                            # Check temp folder for downloads
                            temp_folder = self.downloads_root / "_temp"
                            for f in temp_folder.glob("*.pdf"):
                                if f.is_file():
                                    import shutil
                                    dest = target_folder / f.name
                                    if not dest.exists():
                                        shutil.move(str(f), str(dest))
                                        self.logger.log(f"📥 Downloaded: {f.name}", "download")
                                        self.logger.log_download(name, page_number, f.name, 'downloaded')
                                        self.total_downloaded += 1
                                        downloaded_count += 1
                            
                            try:
                                self.driver.close()
                            except:
                                pass
                            self.driver.switch_to.window(popup_window)
                        
                except Exception as e:
                    self.logger.log(f"Error downloading {link_text}: {str(e)[:50]}", "warning")
                    try:
                        self.driver.switch_to.window(popup_window)
                    except:
                        pass
            
            return downloaded_count
            
        except Exception as e:
            self.logger.log(f"Error in download_from_popup: {e}", "warning")
            return downloaded_count
    
    def process_request_form_for_downloads(self, request_url: str, name: str, page_number: int) -> int:
        """Open the request form and download any directly available files.
        
        Does NOT submit any forms - only downloads files marked "(click to download)".
        
        Returns:
            Number of files downloaded
        """
        downloaded_count = 0
        main_window = self.driver.current_window_handle
        
        try:
            # Open form in new tab
            self.driver.execute_script("window.open(arguments[0], '_blank');", request_url)
            time.sleep(3)
            
            # Switch to new tab
            new_tabs = [h for h in self.driver.window_handles if h != main_window]
            if not new_tabs:
                self.logger.log("Failed to open form tab", "warning")
                return 0
            
            form_tab = new_tabs[0]
            self.driver.switch_to.window(form_tab)
            time.sleep(3)
            
            # Wait for the "Find Individual by Name" button
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='Find Individual by Name']")))
            except:
                time.sleep(2)
            
            # Click "Find Individual by Name" to open popup
            try:
                windows_before = set(self.driver.window_handles)
                find_btn = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@value='Find Individual by Name']"))
                )
                self.safe_click(find_btn)
                time.sleep(3)
                
                # Check for popup
                windows_after = set(self.driver.window_handles)
                new_windows = windows_after - windows_before
                
                if not new_windows:
                    self.logger.log("No popup opened", "warning")
                    self.close_all_extra_tabs(main_window)
                    return 0
                
                popup_window = new_windows.pop()
                self.driver.switch_to.window(popup_window)
                time.sleep(2)
                
                # Get all individuals from popup
                # Store index instead of element reference to avoid stale element issues
                radio_buttons = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
                
                individuals = []
                for idx, radio in enumerate(radio_buttons):
                    try:
                        if not radio.is_displayed():
                            continue
                        parent = radio.find_element(By.XPATH, "./..")
                        label_text = parent.text.strip()
                        if label_text:
                            individuals.append((idx, label_text))
                    except:
                        continue
                
                if not individuals:
                    self.logger.log(f"No individuals found in popup for {name}", "warning")
                    self.close_all_extra_tabs(main_window)
                    return 0
                
                self.logger.log(f"Found {len(individuals)} individual(s) in popup", "info")
                
                # Extract individual names and store them for this row (if not already stored)
                individual_names = [ind_name for _, ind_name in individuals]
                if name not in self.row_individuals:
                    self.store_individuals_for_row(name, individual_names)
                    self.logger.log(f"Stored {len(individual_names)} individuals for row: {name}", "info")
                
                # Process each individual
                for idx, individual_name in individuals:
                    try:
                        # Check if this individual has already been processed
                        if self.is_individual_seen(individual_name):
                            self.logger.log(f"⏭️  SKIPPED (already processed): {individual_name}", "skip")
                            self.total_seen_skipped += 1
                            continue
                        
                        # Re-find radio button to avoid stale element reference
                        radio_buttons_fresh = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
                        if idx >= len(radio_buttons_fresh):
                            self.logger.log(f"Could not find radio button at index {idx} for {individual_name}", "warning")
                            continue
                        radio = radio_buttons_fresh[idx]
                        
                        # Click to select this individual
                        self.safe_click(radio)
                        time.sleep(2)
                        
                        # Download any directly available files for this individual
                        count = self.download_from_popup(individual_name, page_number)
                        downloaded_count += count
                        
                        # Mark this individual as processed
                        self.mark_individual_as_seen(individual_name)
                        self.logger.log(f"✓ Marked {individual_name} as processed", "success")
                        
                    except Exception as e:
                        self.logger.log(f"Error processing individual {individual_name[:30]}: {e}", "warning")
                        continue
                
                # Close popup
                try:
                    self.driver.close()
                except:
                    pass
                
            except TimeoutException:
                self.logger.log("Could not find 'Find Individual by Name' button", "warning")
            except Exception as e:
                self.logger.log(f"Error in popup handling: {e}", "warning")
            
            # Close form tab and return to main
            self.close_all_extra_tabs(main_window)
            return downloaded_count
            
        except Exception as e:
            self.logger.log(f"Error processing form: {e}", "error")
            self.close_all_extra_tabs(main_window)
            return downloaded_count
    
    def process_row(self, row, page_number: int, row_index: int) -> bool:
        """Process a single table row for direct downloads."""
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 5:
                return False
            
            # Extract row data
            date_added = cells[0].text.strip()
            title = cells[1].text.strip()
            type_cell = cells[2]
            type_text = type_cell.text.strip()
            name = cells[3].text.strip()
            agency = cells[4].text.strip()
            
            # Check if it's a Transaction type
            if "Transaction" not in type_text:
                return False
            
            # Check if this row has been fully processed (all individuals done)
            if self.is_row_finished(name):
                self.logger.log(f"⏭️  SKIPPED (row fully processed): {name}", "skip")
                self.total_seen_skipped += 1
                return False
            
            # First check for direct download link in the main table (PDF link)
            download_link = None
            request_link = None
            
            try:
                links = type_cell.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href") or ""
                    link_text = link.text.strip().lower()
                    
                    # Check for "Request this Document" link
                    if "request" in link_text:
                        request_link = link
                        continue
                    
                    # Check for PDF links or direct transaction links
                    if ".pdf" in href.lower() or ("transaction" in link_text and "request" not in link_text):
                        download_link = link
            except:
                pass
            
            downloaded_something = False
            
            # If there's a direct download link in the table, download it
            # Note: We don't track direct downloads because the same person can have 
            # multiple different files (e.g., different transaction dates)
            if download_link:
                self.logger.log(f"Found direct table download for: {name}", "info")
                if self.download_file(download_link, name, page_number):
                    downloaded_something = True
                self.logger.log(f"✓ Downloaded direct file for {name} (no tracking for direct downloads)", "info")
            
            # If there's a request link, open the form to find "(click to download)" files
            # Note: Individual tracking happens inside process_request_form_for_downloads
            # These ARE tracked because popup content doesn't change over time
            if request_link:
                request_url = request_link.get_attribute('href')
                if request_url:
                    self.logger.log(f"Checking form for downloadable files: {name}", "info")
                    count = self.process_request_form_for_downloads(request_url, name, page_number)
                    if count > 0:
                        downloaded_something = True
                    
                    # Check if all individuals for this row have been processed
                    row_individuals = self.get_individuals_for_row(name)
                    if row_individuals:
                        all_processed = all(self.is_individual_seen(ind) for ind in row_individuals)
                        if all_processed:
                            self.mark_row_as_finished(name)
                            self.logger.log(f"✓ All individuals processed, row marked as finished: {name}", "success")
            
            if not downloaded_something and not download_link and not request_link:
                self.total_no_download += 1
            
            return downloaded_something
            
        except StaleElementReferenceException:
            return False
        except Exception as e:
            self.logger.log(f"Error processing row {row_index}: {e}", "error")
            return False
    
    def process_page(self, page_number: int) -> int:
        """Process all rows on a given page."""
        downloads_on_page = 0
        
        self.logger.log(f"=== Processing Page {page_number} ===", "start")
        
        rows = self.get_table_rows()
        total_rows = len(rows)
        self.logger.log(f"Found {total_rows} rows on page {page_number}")
        
        row_index = 0
        while row_index < total_rows:
            try:
                # Re-fetch rows to avoid stale references
                rows = self.get_table_rows()
                if not rows or row_index >= len(rows):
                    break
                
                row = rows[row_index]
                if self.process_row(row, page_number, row_index):
                    downloads_on_page += 1
                
                row_index += 1
                
            except StaleElementReferenceException:
                time.sleep(1)
                continue
            except Exception as e:
                self.logger.log(f"Error processing row {row_index}: {e}", "error")
                row_index += 1
        
        self.logger.log(f"Page {page_number} complete. Downloads attempted: {downloads_on_page}", "info")
        return downloads_on_page
    
    def run(self):
        """Main execution method."""
        try:
            # Load tracking data
            if not self.load_seen_rows():
                return
            if not self.load_row_individuals():
                return
            if not self.load_finished_rows():
                return
            
            self.setup_driver()
            self.navigate_to_main_page()
            self.handle_affirm_banner()
            
            # Apply filters
            if not self.filter_by_transaction():
                self.logger.log("Warning: Transaction filter may not have been applied", "warning")
            
            # Sort by name
            if not self.sort_by_name():
                self.logger.log("Warning: Name sorting may not have been applied", "warning")
            
            # Process pages
            for page in range(START_PAGE, END_PAGE + 1):
                if not self.navigate_to_page(page):
                    self.logger.log(f"Could not navigate to page {page}, stopping.", "error")
                    break
                
                self.process_page(page)
                time.sleep(1)
            
            # Save logs
            self.logger.save_csv_log()
            self.logger.log_summary(self.total_downloaded, self.total_skipped, self.total_no_download, self.total_seen_skipped)
            
            # Final summary
            self.logger.log("=== DIRECT DOWNLOAD COMPLETE ===", "success")
            self.logger.log(f"Total files downloaded: {self.total_downloaded}", "info")
            self.logger.log(f"Total files skipped (already exist): {self.total_skipped}", "info")
            self.logger.log(f"Total individuals skipped (already seen): {self.total_seen_skipped}", "info")
            self.logger.log(f"Rows without direct download: {self.total_no_download}", "info")
            self.logger.log(f"Files saved to: {self.downloads_root}", "info")
            
        except Exception as e:
            self.logger.log(f"Critical error: {e}", "error")
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                try:
                    import sys
                    if sys.stdin.isatty():
                        input("\n⏸️  Press Enter to close the browser...")
                except (EOFError, Exception):
                    pass
                finally:
                    self.driver.quit()
                    self.logger.log("Browser closed", "info")


def main():
    """Entry point for the script."""
    import argparse
    parser = argparse.ArgumentParser(description='OGE Direct File Downloader')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    args = parser.parse_args()
    
    print("=" * 60)
    print("OGE Direct File Downloader")
    print("=" * 60)
    print(f"Pages to process: {START_PAGE} to {END_PAGE}")
    print(f"Tracking files:")
    print(f"  - {SEEN_ROWS_FILE} (processed individuals)")
    print(f"  - {ROW_INDIVIDUAL_FILE} (row-to-individuals mapping)")
    print(f"  - {FINISHED_ROWS_FILE} (completed rows)")
    print(f"Downloads to: {DOWNLOADS_ROOT}")
    print("=" * 60)
    print()
    print("This script will:")
    print("   1. Navigate to the OGE website")
    print("   2. Filter by 'Transaction' type")
    print("   3. Sort by Name (A-Z)")
    print(f"   4. Navigate to pages {START_PAGE}-{END_PAGE}")
    print("   5. Download direct table files (always, no tracking)")
    print("   6. For popup files: Skip rows already fully processed")
    print("   7. For popup files: Extract all individuals (first time only)")
    print("   8. For popup files: Process each individual, skip already-processed ones")
    print("   9. Download ONLY directly available files (no form submission)")
    print("   10. Organize files by individual: direct_downloads/<name>/")
    print("   11. Mark popup rows as complete when all individuals processed")
    print()
    
    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")
    
    downloader = OGEDirectDownloader(headless=args.headless)
    downloader.run()


if __name__ == "__main__":
    main()

