#!/usr/bin/env python3
"""
OGE Document Request Automation Script
Automates the process of requesting transaction documents from the 
U.S. Office of Government Ethics website.

Pages 36-39 (sorted by Name, filtered by Transaction)
"""

import csv
import time
import os
import re
import json
import urllib.parse
import glob
from datetime import datetime
from typing import Optional, List, Dict, Set

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
    ElementClickInterceptedException,
    UnexpectedAlertPresentException,
    NoAlertPresentException
)
from webdriver_manager.chrome import ChromeDriverManager

import config


class RequestLogger:
    """Handles logging of requests to CSV and progress to Markdown."""
    
    def __init__(self, log_file: str = config.LOG_FILE, progress_file: str = config.PROGRESS_FILE):
        self.log_file = log_file
        self.progress_file = progress_file
        self.processed_entries = set()
        self._load_existing_log()
        self._init_progress_file()
    
    def _load_existing_log(self):
        """Load previously processed entries to avoid duplicates."""
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = f"{row.get('name', '')}|{row.get('title', '')}|{row.get('date_added', '')}|{row.get('file_name', '')}"
                    self.processed_entries.add(key)
            print(f"📂 Loaded {len(self.processed_entries)} previously processed entries from log")
    
    def _init_progress_file(self):
        """Initialize the progress markdown file."""
        if not os.path.exists(self.progress_file):
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                f.write("# OGE Document Request Progress\n\n")
                f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**Configuration:**\n")
                f.write(f"- User: {config.USER_NAME}\n")
                f.write(f"- Email: {config.USER_EMAIL}\n")
                f.write(f"- Pages: {config.START_PAGE} to {config.END_PAGE}\n\n")
                f.write("---\n\n")
    
    def is_duplicate(self, name: str, title: str, date_added: str, file_name: str = "") -> bool:
        """Check if an entry has already been processed."""
        key = f"{name}|{title}|{date_added}|{file_name}"
        return key in self.processed_entries
    
    def log_request(self, name: str, title: str, date_added: str, agency: str, 
                    files_requested: list, status: str, page: int, row: int):
        """Log a request to the CSV file."""
        file_exists = os.path.exists(self.log_file)
        
        with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['timestamp', 'page', 'row', 'name', 'title', 'date_added', 
                         'agency', 'file_name', 'status', 'batch_size']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            for file_name_item in files_requested:
                key = f"{name}|{title}|{date_added}|{file_name_item}"
                self.processed_entries.add(key)
                
                writer.writerow({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'page': page,
                    'row': row,
                    'name': name,
                    'title': title,
                    'date_added': date_added,
                    'agency': agency,
                    'file_name': file_name_item,
                    'status': status,
                    'batch_size': len(files_requested)
                })
    
    def log_progress(self, message: str, level: str = "info"):
        """Log progress to the markdown file."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "start": "🚀"}
        icon = icons.get(level, "•")
        
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"- `{timestamp}` {icon} {message}\n")
        
        print(f"{icon} [{timestamp}] {message}")
    
    def log_page_summary(self, page: int, requests_made: int, skipped: int, downloaded: int):
        """Log summary for a completed page."""
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"\n### Page {page} Summary\n")
            f.write(f"- Requests submitted: {requests_made}\n")
            f.write(f"- Direct downloads: {downloaded}\n")
            f.write(f"- Skipped (duplicates/non-transaction): {skipped}\n")
            f.write("---\n\n")


class OGEAutomation:
    """Main automation class for OGE document requests."""
    
    def __init__(self, headless: bool = False):
        self.driver = None
        self.wait = None
        self.logger = RequestLogger()
        self.headless = headless
        self.current_page = 1
        self.requests_since_restart = 0
        self.max_requests_before_restart = 10  # Restart browser every 10 requests to prevent memory issues
        self.requested_docs_tracker = self.load_requested_docs_tracker()
    
    def get_individual_key(self, individual_full_name: str) -> str:
        """Generate a unique key for tracking documents per individual.
        
        Uses the full individual name from the popup like:
        'Aber, Jessica D Department Of Justice, U.S. Attorney Virginia Eastern District'
        """
        # Normalize to lowercase for consistent matching
        return individual_full_name.strip().lower()
    
    def load_requested_docs_tracker(self) -> Dict[str, List[str]]:
        """Load the persistent tracker of requested documents."""
        try:
            if os.path.exists(config.REQUESTED_DOCS_FILE):
                with open(config.REQUESTED_DOCS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.logger.log_progress(f"Loaded {len(data)} entries from requested docs tracker", "info")
                    return data
        except Exception as e:
            self.logger.log_progress(f"Error loading requested docs tracker: {e}", "warning")
        return {}
    
    def save_requested_docs_tracker(self):
        """Save the requested documents tracker to disk."""
        try:
            with open(config.REQUESTED_DOCS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.requested_docs_tracker, f, indent=2)
        except Exception as e:
            self.logger.log_progress(f"Error saving requested docs tracker: {e}", "warning")
    
    def get_requested_docs_for_individual(self, individual_full_name: str) -> Set[str]:
        """Get the set of already requested documents for a specific individual."""
        key = self.get_individual_key(individual_full_name)
        docs = self.requested_docs_tracker.get(key, [])
        return set(docs)
    
    def add_requested_docs_for_individual(self, individual_full_name: str, doc_names: List[str]):
        """Add requested documents to the tracker and save to disk."""
        key = self.get_individual_key(individual_full_name)
        if key not in self.requested_docs_tracker:
            self.requested_docs_tracker[key] = []
        
        for doc in doc_names:
            if doc not in self.requested_docs_tracker[key]:
                self.requested_docs_tracker[key].append(doc)
        
        # Save immediately to disk
        self.save_requested_docs_tracker()
        self.logger.log_progress(f"Saved {len(doc_names)} docs to tracker for: {individual_full_name[:50]}...", "info")
    
    def setup_driver(self):
        """Initialize the Chrome WebDriver."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            # Force PDF downloads instead of opening in browser
            "plugins.always_open_pdf_externally": True,
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
        self.wait = WebDriverWait(self.driver, config.ELEMENT_WAIT_TIMEOUT)
        
        self.logger.log_progress("Chrome WebDriver initialized", "start")
    
    def sanitize_folder_name(self, name: str) -> str:
        """Sanitize a string for use as a folder name."""
        # Remove or replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        return sanitized[:100]  # Limit length
    
    def create_download_folder(self, page: int, row_index: int, row_data: Dict) -> str:
        """Create a folder for downloading files for a specific individual."""
        name = row_data.get('name', 'Unknown').replace(',', '').replace(' ', '_')
        agency = row_data.get('agency', 'Unknown').replace(' ', '_')[:30]
        
        # Format: page{page}_{name}_{agency}_row{row}
        folder_name = f"page{page}_{self.sanitize_folder_name(name)}_{self.sanitize_folder_name(agency)}_row{row_index}"
        
        folder_path = os.path.join(os.getcwd(), config.DOWNLOADS_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        
        return folder_path
    
    def set_download_directory(self, download_path: str):
        """Change Chrome's download directory."""
        try:
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                'behavior': 'allow',
                'downloadPath': download_path
            })
            return True
        except Exception as e:
            self.logger.log_progress(f"Could not set download directory: {e}", "warning")
            return False
    
    def wait_for_download(self, download_dir: str, timeout: int = 30) -> Optional[str]:
        """Wait for a download to complete and return the filename."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check for any new files (not .crdownload)
            files = glob.glob(os.path.join(download_dir, "*"))
            for f in files:
                if not f.endswith('.crdownload') and os.path.isfile(f):
                    # Check if file was modified recently (within last 30 seconds)
                    if os.path.getmtime(f) > start_time:
                        time.sleep(0.5)  # Give it a moment to finish
                        return os.path.basename(f)
            time.sleep(0.5)
        return None
    
    def download_direct_links(self, row_data: Dict, page: int, row_index: int) -> int:
        """Download files that have direct download links in the popup."""
        downloaded_count = 0
        
        try:
            # Create folder for this individual
            download_folder = self.create_download_folder(page, row_index, row_data)
            self.set_download_directory(download_folder)
            
            # Find all direct download links (containing "click to download")
            download_links = self.driver.find_elements(
                By.XPATH, "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'click to download')]"
            )
            
            if not download_links:
                return 0
            
            self.logger.log_progress(f"Found {len(download_links)} direct download links", "info")
            
            # Collect all href links first to avoid stale element issues
            links_to_download = []
            for link in download_links:
                try:
                    link_text = link.text.strip()
                    href = link.get_attribute('href')
                    if href:
                        links_to_download.append((href, link_text))
                except:
                    continue
            
            # Store current window handle
            current_window = self.driver.current_window_handle
            
            for href, link_text in links_to_download:
                try:
                    # Use JavaScript to trigger download directly
                    # Create a temporary anchor element with download attribute
                    file_name = link_text.replace('(click to download)', '').strip()
                    file_name = self.sanitize_folder_name(file_name) + '.pdf'
                    
                    # Open link in new tab to trigger download
                    self.driver.execute_script(f"window.open('{href}', '_blank');")
                    time.sleep(2)
                    
                    # Switch to new tab and wait
                    new_handles = [h for h in self.driver.window_handles if h != current_window]
                    if new_handles:
                        new_tab = new_handles[-1]
                        self.driver.switch_to.window(new_tab)
                        time.sleep(3)  # Wait for PDF to load or download
                        
                        # Close the tab and switch back
                        try:
                            self.driver.close()
                        except:
                            pass
                        self.driver.switch_to.window(current_window)
                    
                    # Wait for download to complete
                    downloaded_file = self.wait_for_download(download_folder, timeout=10)
                    
                    if downloaded_file:
                        self.logger.log_progress(f"Downloaded: {downloaded_file}", "success")
                        
                        # Log the download
                        self.logger.log_request(
                            name=row_data.get('name', 'Unknown'),
                            title=row_data.get('title', 'Unknown'),
                            date_added=row_data.get('date_added', ''),
                            agency=row_data.get('agency', 'Unknown'),
                            files_requested=[downloaded_file],
                            status='downloaded',
                            page=page,
                            row=row_index
                        )
                        downloaded_count += 1
                    else:
                        # File might have opened in browser instead of downloading
                        # Log it anyway as attempted
                        self.logger.log_progress(f"Download pending/opened in browser: {link_text}", "info")
                        
                except Exception as e:
                    self.logger.log_progress(f"Error downloading {link_text}: {str(e)[:50]}", "warning")
                    # Make sure we're on the right window
                    try:
                        self.driver.switch_to.window(current_window)
                    except:
                        pass
                    continue
            
            return downloaded_count
            
        except Exception as e:
            self.logger.log_progress(f"Error in download_direct_links: {e}", "warning")
            return downloaded_count
    
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
            except (StaleElementReferenceException, ElementClickInterceptedException) as e:
                self.dismiss_alert()
                if attempt < retries - 1:
                    time.sleep(0.5)
                else:
                    raise e
        return False
    
    def wait_for_table_load(self):
        """Wait for the table to finish loading."""
        try:
            # First dismiss any alerts
            self.dismiss_alert()
            
            # Wait for "Loading" text to disappear
            WebDriverWait(self.driver, 20).until_not(
                EC.presence_of_element_located((By.XPATH, "//td[contains(text(), 'Loading')]"))
            )
            time.sleep(1)  # Extra buffer for data to populate
        except TimeoutException:
            pass  # Table might already be loaded
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
    
    def dismiss_alert(self):
        """Dismiss any alert dialogs that may appear."""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            self.logger.log_progress(f"Dismissing alert: {alert_text[:50]}...", "warning")
            alert.accept()
            time.sleep(0.5)
            return True
        except NoAlertPresentException:
            return False
        except Exception:
            return False
    
    def safe_operation(self, operation, *args, max_retries: int = 3, **kwargs):
        """Execute an operation with alert handling and retry logic."""
        for attempt in range(max_retries):
            try:
                # First dismiss any pending alerts
                self.dismiss_alert()
                return operation(*args, **kwargs)
            except UnexpectedAlertPresentException:
                self.dismiss_alert()
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            except Exception as e:
                if attempt < max_retries - 1:
                    self.dismiss_alert()
                    time.sleep(1)
                    continue
                raise e
        return None
    
    def navigate_to_main_page(self):
        """Navigate to the OGE main search page."""
        self.logger.log_progress("Navigating to OGE website...")
        self.driver.get(config.BASE_URL)
        time.sleep(2)
    
    def handle_affirm_banner(self) -> bool:
        """Handle the 'I affirm' legal banner by clicking on it."""
        try:
            self.logger.log_progress("Looking for affirm banner...")
            
            # The affirm banner is a clickable div with the legal text
            affirm_selectors = [
                "//div[contains(., 'By clicking this banner, I affirm')]",
                "//*[contains(text(), 'I affirm')]",
                "//div[contains(@class, 'cursor') and contains(., 'prohibitions')]"
            ]
            
            for selector in affirm_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            self.safe_click(element)
                            self.logger.log_progress("Clicked affirm banner", "success")
                            time.sleep(2)
                            self.wait_for_table_load()
                            return True
                except NoSuchElementException:
                    continue
            
            self.logger.log_progress("No affirm banner found or already dismissed", "info")
            return True
        except Exception as e:
            self.logger.log_progress(f"Error handling affirm banner: {e}", "warning")
            return True
    
    def filter_by_transaction(self) -> bool:
        """Filter the table to show only Transaction type."""
        try:
            self.dismiss_alert()
            self.logger.log_progress("Filtering by Transaction type...")
            
            # Find the Type filter input (it has placeholder "Filter Type")
            type_filter = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Filter Type']"))
            )
            
            type_filter.clear()
            type_filter.send_keys("Transaction")
            
            time.sleep(2)
            self.dismiss_alert()
            self.wait_for_table_load()
            
            self.logger.log_progress("Applied Transaction filter", "success")
            return True
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.filter_by_transaction()
        except Exception as e:
            self.dismiss_alert()
            self.logger.log_progress(f"Error filtering by transaction: {e}", "error")
            return False
    
    def sort_by_name(self) -> bool:
        """Sort the table by Name column (alphabetical order)."""
        try:
            self.dismiss_alert()
            self.logger.log_progress("Sorting by Name column (A-Z)...")
            
            # Find the Name column header and click it
            name_header = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//th[contains(., 'Name')]"))
            )
            
            self.safe_click(name_header)
            time.sleep(2)
            self.dismiss_alert()
            self.wait_for_table_load()
            
            # Check if sorting is ascending (A-Z). If not, click again.
            # Look for the aria-sort attribute or sorting class
            try:
                self.dismiss_alert()
                name_header = self.driver.find_element(By.XPATH, "//th[contains(., 'Name')]")
                aria_sort = name_header.get_attribute("aria-sort")
                
                if aria_sort == "descending":
                    self.logger.log_progress("Clicking again for ascending order...")
                    self.safe_click(name_header)
                    time.sleep(2)
                    self.dismiss_alert()
                    self.wait_for_table_load()
            except (UnexpectedAlertPresentException, NoAlertPresentException):
                self.dismiss_alert()
            except:
                pass
            
            self.logger.log_progress("Sorted by Name column (A-Z)", "success")
            return True
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.sort_by_name()
        except Exception as e:
            self.dismiss_alert()
            self.logger.log_progress(f"Error sorting by name: {e}", "error")
            return False
    
    def navigate_to_page(self, page_number: int) -> bool:
        """Navigate to a specific page number."""
        try:
            # Dismiss any pending alerts first
            self.dismiss_alert()
            
            if self.current_page == page_number:
                return True
            
            self.logger.log_progress(f"Navigating to page {page_number}...")
            
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
                    self.logger.log_progress(f"Navigated to page {page_number}", "success")
                    return True
            except (NoSuchElementException, UnexpectedAlertPresentException):
                self.dismiss_alert()
            
            # If page number not visible, navigate using Next button or ellipsis
            # First, try clicking ellipsis to expand page range
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
                            self.logger.log_progress(f"Navigated to page {page_number}", "success")
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
                            self.logger.log_progress(f"Progress: on page {self.current_page}...")
                    else:
                        break
                except UnexpectedAlertPresentException:
                    self.dismiss_alert()
                    continue
                except NoSuchElementException:
                    self.logger.log_progress(f"Could not find Next button at page {self.current_page}", "error")
                    return False
            
            if self.current_page == page_number:
                self.logger.log_progress(f"Navigated to page {page_number}", "success")
                return True
            
            return False
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            # Retry navigation after dismissing alert
            return self.navigate_to_page(page_number)
        except Exception as e:
            self.dismiss_alert()
            self.logger.log_progress(f"Error navigating to page {page_number}: {e}", "error")
            return False
    
    def get_table_rows(self) -> list:
        """Get all data rows from the current table page."""
        try:
            time.sleep(0.5)
            rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
            return rows
        except Exception as e:
            self.logger.log_progress(f"Error getting table rows: {e}", "warning")
            return []
    
    def extract_row_data(self, row) -> Optional[Dict]:
        """Extract data from a table row."""
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 5:
                type_cell = cells[2]
                type_text = type_cell.text.strip()
                
                # Check if it's a Transaction type
                is_transaction = "Transaction" in type_text
                
                # Check for request link
                request_link = None
                download_link = None
                
                try:
                    request_link = type_cell.find_element(By.XPATH, ".//a[contains(text(), 'Request this Document')]")
                except NoSuchElementException:
                    pass
                
                try:
                    # Direct download link (like "278 Transaction" that links to PDF)
                    links = type_cell.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        href = link.get_attribute("href") or ""
                        if ".pdf" in href.lower():
                            download_link = link
                            break
                except:
                    pass
                
                return {
                    'date_added': cells[0].text.strip(),
                    'title': cells[1].text.strip(),
                    'type': type_text,
                    'name': cells[3].text.strip(),
                    'agency': cells[4].text.strip(),
                    'level': cells[5].text.strip() if len(cells) > 5 else 'n/a',
                    'is_transaction': is_transaction,
                    'request_link': request_link,
                    'download_link': download_link,
                    'row_element': row
                }
        except (StaleElementReferenceException, Exception) as e:
            pass
        return None
    
    def close_all_extra_tabs(self, main_window: str):
        """Simple helper: Go to main window and close ALL other tabs."""
        try:
            # First, switch to main window
            self.driver.switch_to.window(main_window)
            time.sleep(0.5)
            
            # Now close all other tabs
            handles_to_close = [h for h in self.driver.window_handles if h != main_window]
            for handle in handles_to_close:
                try:
                    self.driver.switch_to.window(handle)
                    # Dismiss any alerts
                    try:
                        self.driver.switch_to.alert.dismiss()
                    except:
                        pass
                    self.driver.close()
                except:
                    pass
            
            # Switch back to main
            self.driver.switch_to.window(main_window)
            
            remaining = len(self.driver.window_handles)
            self.logger.log_progress(f"Closed extra tabs. Now have {remaining} tab(s)", "info")
            return remaining == 1
        except Exception as e:
            self.logger.log_progress(f"Error closing tabs: {e}", "warning")
            return False
    
    def process_request_form(self, row_data: Dict, page: int, row_index: int) -> tuple:
        """Process the request form for a document.
        
        Handles MULTIPLE individuals in the popup (e.g., Abbott James - Member, Abbott James - Member 2).
        For each individual, requests all their documents (in batches of 5).
        Moves to next individual when current one is done.
        
        Returns:
            tuple: (success: bool, download_count: int)
        """
        self.popup_download_count = 0
        batch_number = 0
        total_submitted = 0
        
        # Track ALL individuals found in popup (populated on first open)
        all_individuals = None
        # Track which individuals are fully processed
        processed_individuals = set()
        
        try:
            self.logger.log_progress(f"Processing request for: {row_data['name']} - {row_data['title']}")
            
            # Click the request link
            request_link = row_data['request_link']
            request_url = request_link.get_attribute('href')
            
            # Store main window handle
            main_window = self.driver.current_window_handle
            
            # STEP 1: Ensure we start with only the main tab
            self.close_all_extra_tabs(main_window)
            
            # Extract last name from the name (format: "LastName, FirstName")
            name_parts = row_data['name'].split(',')
            last_name = name_parts[0].strip()
            first_name = name_parts[1].strip() if len(name_parts) > 1 else ""
            
            # MAIN LOOP: Keep processing until all individuals are done
            while True:
                batch_number += 1
                
                # STEP 2: Open form in new tab
                self.logger.log_progress(f"Opening form (batch {batch_number})...", "info")
                self.driver.execute_script("window.open(arguments[0], '_blank');", request_url)
                time.sleep(3)
                
                # Switch to new tab
                new_tabs = [h for h in self.driver.window_handles if h != main_window]
                if not new_tabs:
                    self.logger.log_progress("Failed to open form tab", "warning")
                    break
                
                self.driver.switch_to.window(new_tabs[0])
                time.sleep(5)  # Wait for page to load and auto-fill last name
                
                # Wait for the "Find Individual by Name" button
                try:
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='Find Individual by Name']")))
                except:
                    time.sleep(3)
                
                # STEP 3: Click "Find Individual by Name" to open popup
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
                        self.logger.log_progress("No popup opened - may need to enter last name", "warning")
                        self.close_all_extra_tabs(main_window)
                        break
                    
                    popup_window = new_windows.pop()
                    self.driver.switch_to.window(popup_window)
                    time.sleep(2)
                    
                    # STEP 4: Get ALL individuals from popup (only on first iteration)
                    if all_individuals is None:
                        all_individuals = self.get_all_individuals_from_popup(last_name, first_name)
                        if not all_individuals:
                            self.logger.log_progress("No matching individuals found in popup", "warning")
                            self.close_all_extra_tabs(main_window)
                            break
                        self.logger.log_progress(f"Found {len(all_individuals)} individual(s) to process", "info")
                    
                    # STEP 5: Find the first individual that still has unrequested documents
                    found_work = False
                    current_individual = None
                    
                    for individual_full_name in all_individuals:
                        # Skip if already fully processed
                        if individual_full_name.lower() in processed_individuals:
                            continue
                        
                        # Check how many docs we've already requested for this individual
                        requested_docs = self.get_requested_docs_for_individual(individual_full_name)
                        
                        # Select this individual
                        if not self.select_individual_by_name(individual_full_name):
                            self.logger.log_progress(f"Could not select: {individual_full_name[:40]}...", "warning")
                            continue
                        
                        current_individual = individual_full_name
                        
                        # STEP 6: Select files from popup
                        files_selected, popup_downloads, selected_names = self.select_files_from_popup(
                            row_data, page, row_index, requested_docs
                        )
                        self.popup_download_count += popup_downloads
                        
                        if files_selected and selected_names:
                            # Found work to do for this individual
                            found_work = True
                            
                            # Close popup
                            try:
                                self.driver.close()
                            except:
                                pass
                            
                            # Switch back to form tab
                            form_tabs = [h for h in self.driver.window_handles if h != main_window]
                            if form_tabs:
                                self.driver.switch_to.window(form_tabs[0])
                            time.sleep(1)
                            
                            # Add to tracking
                            self.add_requested_docs_for_individual(individual_full_name, selected_names)
                            
                            # Fill and submit form
                            self.fill_request_form()
                            if self.submit_request():
                                total_submitted += 1
                                self.logger.log_request(
                                    name=row_data['name'],
                                    title=row_data['title'],
                                    date_added=row_data['date_added'],
                                    agency=row_data['agency'],
                                    files_requested=[f'{individual_full_name[:30]}...batch_{batch_number}'],
                                    status='submitted',
                                    page=page,
                                    row=row_index
                                )
                            
                            # Go back to main and close ALL extra tabs
                            self.logger.log_progress("Form submitted. Returning to main page...", "info")
                            self.close_all_extra_tabs(main_window)
                            time.sleep(1)
                            break  # Exit for loop to continue while loop
                            
                        else:
                            # No more files for this individual - mark as processed
                            self.logger.log_progress(f"Individual done: {individual_full_name[:50]}...", "success")
                            processed_individuals.add(individual_full_name.lower())
                            # Continue to next individual in the for loop
                    
                    if not found_work:
                        # All individuals are done!
                        self.logger.log_progress(f"All {len(all_individuals)} individual(s) processed ({total_submitted} batches total)", "success")
                        # Close popup if still open
                        try:
                            self.driver.close()
                        except:
                            pass
                        self.close_all_extra_tabs(main_window)
                        return (True, self.popup_download_count)
                        
                except TimeoutException:
                    self.logger.log_progress("Could not find 'Find Individual by Name' button", "warning")
                    self.close_all_extra_tabs(main_window)
                    break
                except Exception as e:
                    self.logger.log_progress(f"Error in form processing: {e}", "warning")
                    self.close_all_extra_tabs(main_window)
                    break
            
            # Final cleanup
            self.close_all_extra_tabs(main_window)
            return (total_submitted > 0, self.popup_download_count)
            
        except Exception as e:
            self.logger.log_progress(f"Error processing request form: {e}", "error")
            self.recover_to_main_window()
            return (False, self.popup_download_count)
    
    def close_form_tab_and_return(self, main_window: str):
        """Close ALL extra tabs and switch back to the main window."""
        self.close_all_extra_tabs(main_window)
        time.sleep(1)
        self.wait_for_table_load()
    
    def cleanup_windows(self, main_window: str):
        """Close all windows except the main window."""
        try:
            current_handles = self.driver.window_handles
            for handle in current_handles:
                if handle != main_window:
                    try:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    except:
                        pass
            
            if main_window in self.driver.window_handles:
                self.driver.switch_to.window(main_window)
            elif self.driver.window_handles:
                self.driver.switch_to.window(self.driver.window_handles[0])
        except Exception as e:
            self.logger.log_progress(f"Error cleaning up windows: {e}", "warning")
    
    def recover_to_main_window(self):
        """Attempt to recover to a working main window."""
        try:
            handles = self.driver.window_handles
            
            if not handles:
                # All windows closed, need to restart
                self.logger.log_progress("All windows closed, navigating back to main page", "warning")
                self.setup_driver()
                self.navigate_to_main_page()
                self.handle_affirm_banner()
                self.filter_by_transaction()
                self.sort_by_name()
                return
            
            # Switch to first available window
            self.driver.switch_to.window(handles[0])
            
            # Check if we're on the main OGE page
            if 'oge.gov' not in self.driver.current_url.lower():
                self.navigate_to_main_page()
                self.handle_affirm_banner()
                self.filter_by_transaction()
                self.sort_by_name()
                
        except Exception as e:
            self.logger.log_progress(f"Recovery failed: {e}", "error")
    
    def get_all_individuals_from_popup(self, last_name: str, first_name: str) -> List[str]:
        """Get ALL matching individuals from the popup.
        
        Returns:
            List of full name strings for all matching individuals
        """
        individuals = []
        
        try:
            time.sleep(2)
            radio_buttons = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
            
            for radio in radio_buttons:
                try:
                    if not radio.is_displayed():
                        continue
                    
                    # Get the full name text
                    label_text_original = ""
                    try:
                        parent = radio.find_element(By.XPATH, "./..")
                        label_text_original = parent.text.strip()
                    except:
                        continue
                    
                    if not label_text_original:
                        continue
                    
                    label_text = label_text_original.lower()
                    
                    # Check if this matches our search (by last name)
                    if last_name.lower() in label_text:
                        individuals.append(label_text_original)
                except:
                    continue
            
            self.logger.log_progress(f"Found {len(individuals)} individuals in popup for '{last_name}'", "info")
            
        except Exception as e:
            self.logger.log_progress(f"Error getting individuals from popup: {e}", "warning")
        
        return individuals
    
    def select_individual_by_name(self, target_full_name: str) -> bool:
        """Select a specific individual from the popup by their full name.
        
        Args:
            target_full_name: The exact full name to select
            
        Returns:
            bool: True if successfully selected
        """
        try:
            radio_buttons = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
            
            for radio in radio_buttons:
                try:
                    if not radio.is_displayed():
                        continue
                    
                    # Get the full name text
                    label_text_original = ""
                    try:
                        parent = radio.find_element(By.XPATH, "./..")
                        label_text_original = parent.text.strip()
                    except:
                        continue
                    
                    # Check if this is our target individual
                    if label_text_original.lower() == target_full_name.lower():
                        self.safe_click(radio)
                        time.sleep(2)  # Wait for documents to load
                        self.logger.log_progress(f"Selected: {label_text_original}", "success")
                        return True
                        
                except Exception:
                    continue
            
            self.logger.log_progress(f"Could not find individual: {target_full_name[:50]}...", "warning")
            return False
            
        except Exception as e:
            self.logger.log_progress(f"Error selecting individual: {e}", "warning")
            return False
    
    def select_individual_from_popup(self, row_data: Dict, last_name: str, first_name: str) -> tuple:
        """Select individual from the popup search results window.
        
        Returns:
            tuple: (success: bool, individual_full_name: str or None)
        """
        try:
            self.logger.log_progress(f"Looking for individual in popup: {last_name}, {first_name}")
            time.sleep(2)
            
            # The popup has radio buttons for selecting individuals
            # Format: "LastName, FirstName Department, Position"
            radio_buttons = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
            
            for radio in radio_buttons:
                try:
                    if not radio.is_displayed():
                        continue
                    
                    # Get the text label associated with this radio button (FULL NAME)
                    label_text = ""
                    label_text_original = ""
                    try:
                        # Try to get text from parent element
                        parent = radio.find_element(By.XPATH, "./..")
                        label_text_original = parent.text.strip()
                        label_text = label_text_original.lower()
                    except:
                        pass
                    
                    # Check if this is our individual
                    if last_name.lower() in label_text:
                        # If we have first name, try to match it too
                        if first_name and first_name.lower()[:3] not in label_text:
                            # Multiple people with same last name, skip if first name doesn't match
                            continue
                        
                        self.safe_click(radio)
                        time.sleep(2)  # Wait for documents to load
                        self.logger.log_progress(f"Selected individual: {label_text_original}", "success")
                        return (True, label_text_original)
                        
                except Exception:
                    continue
            
            # Fallback: Try any link or clickable element with the name
            search_selectors = [
                f"//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{last_name.lower()}')]",
                f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{last_name.lower()}')]",
            ]
            
            for selector in search_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            element_text = element.text.strip() if element.text else "Unknown Individual"
                            self.safe_click(element)
                            time.sleep(2)
                            self.logger.log_progress(f"Selected individual: {element_text[:50]}", "success")
                            return (True, element_text)
                except:
                    continue
            
            self.logger.log_progress(f"Could not find individual {last_name} in popup", "warning")
            return (False, None)
            
        except Exception as e:
            self.logger.log_progress(f"Error selecting individual from popup: {e}", "warning")
            return (False, None)
    
    def select_files_from_popup(self, row_data: Dict, page: int, row_index: int, already_requested: set = None) -> tuple:
        """Select available files from the popup after selecting an individual.
        
        Args:
            row_data: Data about the current row
            page: Current page number
            row_index: Current row index
            already_requested: Set of document names that have already been requested (to skip)
        
        Returns:
            tuple: (files_selected: bool, direct_download_count: int, selected_file_names: list)
        """
        direct_downloads = 0
        selected_file_names = []
        
        if already_requested is None:
            already_requested = set()
        
        try:
            time.sleep(2)
            
            # NOTE: Direct download links are skipped for now - only requesting documents
            # TODO: Implement direct download functionality later
            
            # Select checkbox files for request (up to MAX_FILES_PER_BATCH)
            all_files = []
            
            # Find all checkboxes in the table
            checkboxes = self.driver.find_elements(By.XPATH, "//table//input[@type='checkbox']")
            
            for cb in checkboxes:
                try:
                    if not cb.is_displayed():
                        continue
                    
                    # Get surrounding text (usually in the same cell)
                    cell_text = ""
                    try:
                        cell = cb.find_element(By.XPATH, "./ancestor::td[1]")
                        cell_text = cell.text.strip()
                    except:
                        try:
                            cell_text = cb.find_element(By.XPATH, "./..").text.strip()
                        except:
                            cell_text = "unknown_file"
                    
                    all_files.append((cb, cell_text))
                        
                except Exception:
                    continue
            
            if not all_files:
                self.logger.log_progress("No file checkboxes found in popup table", "warning")
                # Return True if we downloaded files directly, even if no checkboxes
                return (direct_downloads > 0, direct_downloads, selected_file_names)
            
            # Filter out files that have already been requested
            available_files = []
            for cb, file_name in all_files:
                # Normalize the file name for comparison
                normalized_name = file_name.strip().lower()
                if normalized_name not in already_requested:
                    available_files.append((cb, file_name))
                else:
                    self.logger.log_progress(f"Skipping already requested: {file_name[:30]}...", "info")
            
            if not available_files:
                self.logger.log_progress("All documents for this individual have been requested", "info")
                return (False, direct_downloads, selected_file_names)
            
            # Select files (up to MAX_FILES_PER_BATCH)
            selected_count = 0
            
            for cb, file_name in available_files[:config.MAX_FILES_PER_BATCH]:
                try:
                    if not cb.is_selected():
                        self.safe_click(cb)
                        selected_count += 1
                        selected_file_names.append(file_name.strip().lower())  # Track for the set
                        time.sleep(0.3)
                except:
                    continue
            
            if selected_count > 0:
                self.logger.log_progress(f"Selected {selected_count} NEW files (batch), {len(already_requested)} already requested", "info")
                
                # Click "Add to Cart" button
                try:
                    add_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Add to Cart')]")
                    self.safe_click(add_btn)
                    self.logger.log_progress("Clicked Add to Cart button", "success")
                    time.sleep(2)
                    return (True, direct_downloads, selected_file_names)
                except NoSuchElementException:
                    pass
                
                # Try input button
                try:
                    add_btn = self.driver.find_element(By.XPATH, "//input[@value='Add to Cart']")
                    self.safe_click(add_btn)
                    self.logger.log_progress("Clicked Add to Cart button", "success")
                    time.sleep(2)
                    return (True, direct_downloads, selected_file_names)
                except NoSuchElementException:
                    pass
                
                self.logger.log_progress("Could not find Add to Cart button", "warning")
                return (True, direct_downloads, selected_file_names)  # Files were selected
            
            # No checkbox files selected, but maybe we downloaded some
            return (direct_downloads > 0, direct_downloads, selected_file_names)
            
        except Exception as e:
            self.logger.log_progress(f"Error selecting files from popup: {e}", "warning")
            return (direct_downloads > 0, direct_downloads, selected_file_names)
    
    def find_and_select_files(self, row_data: Dict, page: int, row_index: int) -> bool:
        """Find and select available files for the individual."""
        try:
            # Look for file checkboxes - they should NOT be in the "Type of applicant" section
            # File checkboxes are typically in a table or list showing document types/dates
            
            # Exclude applicant type checkboxes by looking for specific patterns
            file_checkbox_selectors = [
                # Checkboxes in a table (not in the Type of applicant section)
                "//table[contains(@class, 'file') or contains(@id, 'file')]//input[@type='checkbox']",
                # Checkboxes with labels containing file-related terms
                "//input[@type='checkbox' and (following-sibling::*[contains(text(), '278')] or following-sibling::*[contains(text(), 'Transaction')] or following-sibling::*[contains(text(), 'Annual')] or following-sibling::*[contains(text(), 'Termination')])]",
                # Checkboxes in a div/section that looks like file selection
                "//div[contains(@class, 'document') or contains(@class, 'file')]//input[@type='checkbox']",
            ]
            
            file_checkboxes = []
            for selector in file_checkbox_selectors:
                try:
                    checkboxes = self.driver.find_elements(By.XPATH, selector)
                    for cb in checkboxes:
                        if cb.is_displayed() and not cb.is_selected():
                            # Verify this is not an applicant type checkbox
                            try:
                                parent_text = cb.find_element(By.XPATH, "./ancestor::*[5]").text.lower()
                                if "type of applicant" not in parent_text and "news media" not in parent_text:
                                    file_checkboxes.append(cb)
                            except:
                                file_checkboxes.append(cb)
                except:
                    continue
            
            if not file_checkboxes:
                self.logger.log_progress("No file checkboxes found on this page", "info")
                return False
            
            # Process files in batches
            return self.process_files_in_batches(row_data, page, row_index)
            
        except Exception as e:
            self.logger.log_progress(f"Error finding files: {e}", "warning")
            return False
    
    def process_files_in_batches(self, row_data: Dict, page: int, row_index: int) -> bool:
        """Process available files in batches of 5."""
        try:
            batch_number = 0
            total_files_processed = 0
            
            # List of text patterns to exclude (applicant type checkboxes)
            exclude_patterns = [
                'news media', 'private citizen', 'public interest', 'law firm',
                'other private organization', 'government', 'type of applicant',
                'i am aware'
            ]
            
            while True:
                # Find all available checkboxes for transaction files
                all_checkboxes = self.driver.find_elements(
                    By.XPATH, 
                    "//input[@type='checkbox' and not(@disabled)]"
                )
                
                # Filter out "Type of applicant" and other non-file checkboxes
                file_checkboxes = []
                for cb in all_checkboxes:
                    try:
                        # Check the surrounding text to determine if this is a file checkbox
                        parent_text = ""
                        try:
                            parent_text = cb.find_element(By.XPATH, "./ancestor::*[3]").text.lower()
                        except:
                            pass
                        
                        # Skip if any exclude pattern is found in parent text
                        is_excluded = any(pattern in parent_text for pattern in exclude_patterns)
                        
                        if not is_excluded and cb.is_displayed():
                            file_checkboxes.append(cb)
                    except:
                        continue
                
                if not file_checkboxes:
                    if batch_number == 0:
                        self.logger.log_progress("No document file checkboxes found", "warning")
                    break
                
                # Filter out already checked boxes
                unchecked = [cb for cb in file_checkboxes if not cb.is_selected()]
                
                if not unchecked:
                    self.logger.log_progress("All files already selected or processed", "info")
                    break
                
                # Select up to 5 files
                batch = unchecked[:config.MAX_FILES_PER_BATCH]
                batch_files = []
                
                for checkbox in batch:
                    try:
                        # Get file name from label or nearby text
                        file_name = ""
                        try:
                            # Try to get the associated label
                            checkbox_id = checkbox.get_attribute("id")
                            if checkbox_id:
                                label = self.driver.find_element(
                                    By.XPATH, f"//label[@for='{checkbox_id}']"
                                )
                                file_name = label.text.strip()
                        except:
                            pass
                        
                        if not file_name:
                            try:
                                parent = checkbox.find_element(By.XPATH, "./..")
                                file_name = parent.text.strip()[:100]  # Limit length
                            except:
                                file_name = f"file_{batch_number}_{len(batch_files)}"
                        
                        # Check if this file is a duplicate
                        if self.logger.is_duplicate(row_data['name'], row_data['title'], 
                                                    row_data['date_added'], file_name):
                            self.logger.log_progress(f"Skipping duplicate: {file_name[:50]}...", "info")
                            continue
                        
                        self.safe_click(checkbox)
                        batch_files.append(file_name)
                        time.sleep(0.3)
                    except StaleElementReferenceException:
                        continue
                
                if not batch_files:
                    break
                
                batch_number += 1
                self.logger.log_progress(f"Selected batch {batch_number}: {len(batch_files)} files")
                
                # Click "Add to Cart"
                try:
                    add_cart_btn = self.driver.find_element(
                        By.XPATH, "//input[@value='Add to Cart'] | //button[contains(text(), 'Add to Cart')]"
                    )
                    self.safe_click(add_cart_btn)
                    time.sleep(2)
                except NoSuchElementException:
                    self.logger.log_progress("Could not find 'Add to Cart' button", "warning")
                    continue
                
                # Fill in the form
                self.fill_request_form()
                
                # Submit the request
                if self.submit_request():
                    self.logger.log_request(
                        name=row_data['name'],
                        title=row_data['title'],
                        date_added=row_data['date_added'],
                        agency=row_data['agency'],
                        files_requested=batch_files,
                        status='submitted',
                        page=page,
                        row=row_index
                    )
                    total_files_processed += len(batch_files)
                    self.logger.log_progress(f"Batch {batch_number} submitted successfully", "success")
                else:
                    self.logger.log_request(
                        name=row_data['name'],
                        title=row_data['title'],
                        date_added=row_data['date_added'],
                        agency=row_data['agency'],
                        files_requested=batch_files,
                        status='failed',
                        page=page,
                        row=row_index
                    )
                    self.logger.log_progress(f"Batch {batch_number} submission failed", "error")
                
                time.sleep(2)
                
                # After submitting, we might need to go back to select more files
                # Check if there are more unchecked file checkboxes (excluding applicant type)
                all_remaining = self.driver.find_elements(
                    By.XPATH, "//input[@type='checkbox' and not(@disabled)]"
                )
                remaining_unchecked = []
                for cb in all_remaining:
                    try:
                        if cb.is_selected():
                            continue
                        parent_text = ""
                        try:
                            parent_text = cb.find_element(By.XPATH, "./ancestor::*[3]").text.lower()
                        except:
                            pass
                        is_excluded = any(pattern in parent_text for pattern in exclude_patterns)
                        if not is_excluded and cb.is_displayed():
                            remaining_unchecked.append(cb)
                    except:
                        continue
                
                if not remaining_unchecked or len(unchecked) <= config.MAX_FILES_PER_BATCH:
                    break
                    
            return total_files_processed > 0
            
        except Exception as e:
            self.logger.log_progress(f"Error in batch processing: {e}", "error")
            return False
    
    def fill_request_form(self):
        """Fill in the personal information form."""
        try:
            time.sleep(2)  # Wait for form to be ready
            
            # Dismiss any pending alerts first
            self.dismiss_alert()
            
            # The form has fields with specific IDs:
            # - Name field: id="Name"
            # - Email field: id="Email"
            # - Occupation field: id="Occupation"
            
            # Fill Name field using ID
            try:
                name_field = self.driver.find_element(By.ID, "Name")
                name_field.clear()
                time.sleep(0.2)
                name_field.send_keys(config.USER_NAME)
                self.logger.log_progress(f"Filled Name: {config.USER_NAME}", "info")
            except NoSuchElementException:
                self.logger.log_progress("Could not find Name field by ID", "warning")
            
            time.sleep(0.3)
            
            # Fill Email field using ID
            try:
                email_field = self.driver.find_element(By.ID, "Email")
                email_field.clear()
                time.sleep(0.2)
                email_field.send_keys(config.USER_EMAIL)
                self.logger.log_progress(f"Filled Email: {config.USER_EMAIL}", "info")
            except NoSuchElementException:
                self.logger.log_progress("Could not find Email field by ID", "warning")
            
            time.sleep(0.3)
            
            # Fill Occupation field using ID
            try:
                occupation_field = self.driver.find_element(By.ID, "Occupation")
                occupation_field.clear()
                time.sleep(0.2)
                occupation_field.send_keys(config.USER_OCCUPATION)
                self.logger.log_progress(f"Filled Occupation: {config.USER_OCCUPATION}", "info")
            except NoSuchElementException:
                self.logger.log_progress("Could not find Occupation field by ID", "warning")
            
            # Check the "Private citizen" checkbox in "Type of applicant" section
            try:
                # Try to find by label text
                private_citizen_selectors = [
                    "//input[@type='checkbox' and following-sibling::text()[contains(., 'Private citizen')]]",
                    "//input[@type='checkbox'][following-sibling::*[contains(text(), 'Private citizen')]]",
                    "//label[contains(text(), 'Private citizen')]//input[@type='checkbox']",
                    "//label[contains(text(), 'Private citizen')]/preceding-sibling::input[@type='checkbox']",
                    "//input[@type='checkbox'][../text()[contains(., 'Private citizen')]]",
                ]
                
                private_citizen_found = False
                for selector in private_citizen_selectors:
                    try:
                        checkboxes = self.driver.find_elements(By.XPATH, selector)
                        for cb in checkboxes:
                            if cb.is_displayed() and not cb.is_selected():
                                self.safe_click(cb)
                                self.logger.log_progress("Checked 'Private citizen' checkbox", "info")
                                private_citizen_found = True
                                break
                        if private_citizen_found:
                            break
                    except:
                        continue
                
                # Fallback: Find all checkboxes and look for one near "Private citizen" text
                if not private_citizen_found:
                    all_checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                    for cb in all_checkboxes:
                        try:
                            parent = cb.find_element(By.XPATH, "./..")
                            parent_text = parent.text.lower()
                            if 'private citizen' in parent_text and cb.is_displayed():
                                if not cb.is_selected():
                                    self.safe_click(cb)
                                self.logger.log_progress("Checked 'Private citizen' checkbox (fallback)", "info")
                                private_citizen_found = True
                                break
                        except:
                            continue
                
                if not private_citizen_found:
                    self.logger.log_progress("Could not find 'Private citizen' checkbox", "warning")
                    
            except Exception as e:
                self.logger.log_progress(f"Error checking Private citizen checkbox: {e}", "warning")
            
            # Check the REQUIRED awareness checkbox using its ID: "CheckBoxAgree"
            try:
                awareness_checkbox = self.driver.find_element(By.ID, "CheckBoxAgree")
                if not awareness_checkbox.is_selected():
                    self.safe_click(awareness_checkbox)
                self.logger.log_progress("Checked required awareness checkbox", "info")
            except NoSuchElementException:
                self.logger.log_progress("Warning: Could not find awareness checkbox by ID", "warning")
            
            self.logger.log_progress("Form filled with personal information", "info")
            time.sleep(0.5)
            
        except Exception as e:
            self.logger.log_progress(f"Error filling form: {e}", "warning")
    
    def submit_request(self) -> bool:
        """Submit the request form."""
        try:
            # The submit button is an input with value "Submit Request"
            submit_selectors = [
                "//input[@value='Submit Request']",
                "//input[contains(@value, 'Submit')]",
                "//button[contains(text(), 'Submit')]",
                "//*[contains(@aria-label, 'Submit')]"
            ]
            
            for selector in submit_selectors:
                try:
                    submit_btn = self.driver.find_element(By.XPATH, selector)
                    if submit_btn.is_displayed():
                        self.safe_click(submit_btn)
                        time.sleep(2)
                        
                        # Handle the confirmation dialog that appears after submission
                        # Dialog says: "Your form has been submitted. You can expect to receive 
                        # the requested documents within 2 business days"
                        try:
                            alert = self.driver.switch_to.alert
                            alert_text = alert.text
                            self.logger.log_progress(f"Confirmation: {alert_text[:60]}...", "info")
                            alert.accept()  # Click OK
                            self.logger.log_progress("Clicked OK on confirmation dialog", "success")
                            time.sleep(1)
                        except NoAlertPresentException:
                            # No alert present, that's fine
                            pass
                        except Exception as e:
                            self.logger.log_progress(f"Alert handling: {str(e)[:30]}", "warning")
                        
                        self.logger.log_progress("Form submitted", "success")
                        return True
                except NoSuchElementException:
                    continue
            
            self.logger.log_progress("Could not find Submit button", "warning")
            return False
            
        except Exception as e:
            self.logger.log_progress(f"Error submitting form: {e}", "error")
            return False
    
    def download_direct_file(self, row_data: Dict, page: int, row_index: int) -> bool:
        """Download a file that has a direct download link."""
        try:
            download_link = row_data['download_link']
            file_url = download_link.get_attribute('href')
            
            self.logger.log_progress(f"Direct download: {row_data['name']} - {row_data['title']}")
            
            # Click the download link
            self.safe_click(download_link)
            time.sleep(2)
            
            # Log the download
            self.logger.log_request(
                name=row_data['name'],
                title=row_data['title'],
                date_added=row_data['date_added'],
                agency=row_data['agency'],
                files_requested=['direct_download'],
                status='downloaded',
                page=page,
                row=row_index
            )
            
            self.logger.log_progress(f"Downloaded: {row_data['name']} - {row_data['title']}", "success")
            return True
            
        except Exception as e:
            self.logger.log_progress(f"Download failed: {e}", "error")
            return False
    
    def process_page(self, page_number: int) -> tuple:
        """Process all rows on a given page."""
        requests_made = 0
        downloaded = 0
        skipped = 0
        
        self.logger.log_progress(f"=== Processing Page {page_number} ===", "start")
        
        rows = self.get_table_rows()
        total_rows = len(rows)
        self.logger.log_progress(f"Found {total_rows} rows on page {page_number}")
        
        row_index = 0
        while row_index < total_rows:
            try:
                # Validate browser state before processing each row
                try:
                    handles = self.driver.window_handles
                    if not handles:
                        self.logger.log_progress("Browser window lost, recovering...", "warning")
                        self.recover_to_main_window()
                        self.navigate_to_page(page_number)
                        time.sleep(2)
                except Exception:
                    self.logger.log_progress("Browser session error, recovering...", "warning")
                    self.recover_to_main_window()
                    self.navigate_to_page(page_number)
                    time.sleep(2)
                
                # Re-fetch rows to avoid stale references
                rows = self.get_table_rows()
                if not rows or row_index >= len(rows):
                    break
                
                row = rows[row_index]
                row_data = self.extract_row_data(row)
                
                if not row_data:
                    row_index += 1
                    continue
                
                # Skip non-transaction types
                if not row_data['is_transaction']:
                    skipped += 1
                    row_index += 1
                    continue
                
                # Check for duplicate entry
                if self.logger.is_duplicate(row_data['name'], row_data['title'], row_data['date_added']):
                    self.logger.log_progress(
                        f"Skipping duplicate: {row_data['name']} - {row_data['title'][:30]}...", 
                        "info"
                    )
                    skipped += 1
                    row_index += 1
                    continue
                
                # Process based on link type
                if row_data['download_link']:
                    # Direct download available
                    if self.download_direct_file(row_data, page_number, row_index):
                        downloaded += 1
                    else:
                        skipped += 1
                
                elif row_data['request_link']:
                    # Need to submit request
                    success, popup_downloads = self.process_request_form(row_data, page_number, row_index)
                    downloaded += popup_downloads  # Count direct downloads from popup
                    if success:
                        requests_made += 1
                    else:
                        skipped += 1
                    
                    # Allow time for page to stabilize
                    time.sleep(1)
                else:
                    skipped += 1
                
                row_index += 1
                
            except StaleElementReferenceException:
                time.sleep(1)
                continue
            except Exception as e:
                self.logger.log_progress(f"Error processing row {row_index}: {e}", "error")
                row_index += 1
        
        self.logger.log_page_summary(page_number, requests_made, skipped, downloaded)
        return requests_made, skipped, downloaded
    
    def run(self):
        """Main execution method."""
        try:
            self.setup_driver()
            self.navigate_to_main_page()
            self.handle_affirm_banner()
            
            # Apply filters
            if not self.filter_by_transaction():
                self.logger.log_progress("Warning: Transaction filter may not have been applied", "warning")
            
            # Sort by name
            if not self.sort_by_name():
                self.logger.log_progress("Warning: Name sorting may not have been applied", "warning")
            
            total_requests = 0
            total_skipped = 0
            total_downloaded = 0
            
            # Process pages 36 to 39
            for page in range(config.START_PAGE, config.END_PAGE + 1):
                # Verify we're on a valid window before navigating
                try:
                    _ = self.driver.current_url
                except Exception:
                    self.logger.log_progress("Window lost, attempting recovery...", "warning")
                    self.recover_to_main_window()
                    self.navigate_to_page(self.current_page)
                
                if not self.navigate_to_page(page):
                    # Try recovery once
                    self.logger.log_progress(f"Navigation failed, attempting recovery...", "warning")
                    self.recover_to_main_window()
                    
                    # Try navigation again
                    if not self.navigate_to_page(page):
                        self.logger.log_progress(f"Could not navigate to page {page}, stopping.", "error")
                        break
                
                requests, skipped, downloaded = self.process_page(page)
                total_requests += requests
                total_skipped += skipped
                total_downloaded += downloaded
                
                # Save progress after each page
                self.logger.log_progress(f"Completed page {page}: {requests} requests, {skipped} skipped", "info")
            
            # Final summary
            self.logger.log_progress(f"=== AUTOMATION COMPLETE ===", "success")
            self.logger.log_progress(f"Total requests submitted: {total_requests}", "info")
            self.logger.log_progress(f"Total direct downloads: {total_downloaded}", "info")
            self.logger.log_progress(f"Total skipped: {total_skipped}", "info")
            
            with open(config.PROGRESS_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n## Final Summary\n")
                f.write(f"- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"- **Total requests submitted:** {total_requests}\n")
                f.write(f"- **Total direct downloads:** {total_downloaded}\n")
                f.write(f"- **Total skipped:** {total_skipped}\n")
                f.write(f"- **Pages processed:** {config.START_PAGE} to {config.END_PAGE}\n")
            
        except Exception as e:
            self.logger.log_progress(f"Critical error: {e}", "error")
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                try:
                    # Only wait for user input if running interactively
                    import sys
                    if sys.stdin.isatty():
                        input("\n⏸️  Press Enter to close the browser...")
                except EOFError:
                    pass
                except Exception:
                    pass
                finally:
                    self.driver.quit()
                    self.logger.log_progress("Browser closed", "info")


def main():
    """Entry point for the script."""
    import argparse
    parser = argparse.ArgumentParser(description='OGE Document Request Automation')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    args = parser.parse_args()
    
    print("=" * 60)
    print("OGE Document Request Automation")
    print("=" * 60)
    print(f"User: {config.USER_NAME}")
    print(f"Email: {config.USER_EMAIL}")
    print(f"Pages to process: {config.START_PAGE} to {config.END_PAGE}")
    print(f"Max files per batch: {config.MAX_FILES_PER_BATCH}")
    print("=" * 60)
    print()
    print("⚠️  This script will:")
    print("   1. Navigate to the OGE website")
    print("   2. Filter by 'Transaction' type")
    print("   3. Sort by Name (A-Z)")
    print("   4. Navigate to pages 36-39")
    print("   5. Submit requests for transaction documents")
    print("   6. You will receive files via email later")
    print()
    
    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")
    
    automation = OGEAutomation(headless=False)
    automation.run()


if __name__ == "__main__":
    main()
