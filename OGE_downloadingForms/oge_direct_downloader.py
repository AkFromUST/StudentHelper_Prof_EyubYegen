#!/usr/bin/env python3
"""
OGE Direct Downloader Script

Downloads files that are directly available (no form submission required)
from the OGE website and organizes them into the OGE_Documents folder
structure based on peopleToPage_actual.json mapping.

Pages 37-39 (sorted by Name, filtered by Transaction)
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
START_PAGE = 37
END_PAGE = 39
PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT_TIMEOUT = 15

# File paths
MAPPING_FILE = "peopleToPage.json"
DOWNLOADS_ROOT = Path(__file__).parent / "OGE_Documents"
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
    
    def log_summary(self, total_downloaded: int, total_skipped: int, total_no_download: int):
        """Log final summary."""
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"\n## Final Summary\n")
            f.write(f"- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Files downloaded:** {total_downloaded}\n")
            f.write(f"- **Files skipped (already exist):** {total_skipped}\n")
            f.write(f"- **Rows without direct download:** {total_no_download}\n")


class OGEDirectDownloader:
    """Downloads directly available files from OGE website."""
    
    def __init__(self, headless: bool = False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self.current_page = 1
        self.logger = DirectDownloadLogger()
        self.mapping: Dict[str, int] = {}
        self.downloads_root = DOWNLOADS_ROOT
        
        # Statistics
        self.total_downloaded = 0
        self.total_skipped = 0
        self.total_no_download = 0
    
    def load_mapping(self) -> bool:
        """Load the people to page mapping from JSON file."""
        try:
            mapping_path = Path(__file__).parent / MAPPING_FILE
            if not mapping_path.exists():
                self.logger.log(f"Mapping file not found: {mapping_path}", "error")
                return False
            
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.mapping = json.load(f)
            
            self.logger.log(f"Loaded {len(self.mapping)} entries from {MAPPING_FILE}", "success")
            return True
        except Exception as e:
            self.logger.log(f"Error loading mapping: {e}", "error")
            return False
    
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
    
    def find_person_in_mapping(self, name: str) -> Optional[int]:
        """Find the page number for a person from the mapping."""
        # Direct match
        if name in self.mapping:
            return self.mapping[name]
        
        # Case-insensitive match
        name_lower = name.lower()
        for key, page in self.mapping.items():
            if key.lower() == name_lower:
                return page
        
        # Partial match (last name, first name start)
        name_parts = name.split(',')
        if len(name_parts) >= 2:
            last_name = name_parts[0].strip().lower()
            first_name_start = name_parts[1].strip().lower()[:3]
            
            for key, page in self.mapping.items():
                key_parts = key.split(',')
                if len(key_parts) >= 2:
                    key_last = key_parts[0].strip().lower()
                    key_first = key_parts[1].strip().lower()
                    
                    if key_last == last_name and key_first.startswith(first_name_start):
                        return page
        
        return None
    
    def get_target_folder(self, name: str, page_number: int) -> Path:
        """Get the target folder for saving a file."""
        page_folder = f"Page_{page_number:02d}"
        person_folder = self.sanitize_folder_name(name)
        
        target_dir = self.downloads_root / page_folder / person_folder
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
                radio_buttons = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
                
                individuals = []
                for radio in radio_buttons:
                    try:
                        if not radio.is_displayed():
                            continue
                        parent = radio.find_element(By.XPATH, "./..")
                        label_text = parent.text.strip()
                        if label_text:
                            individuals.append((radio, label_text))
                    except:
                        continue
                
                if not individuals:
                    self.logger.log(f"No individuals found in popup for {name}", "warning")
                    self.close_all_extra_tabs(main_window)
                    return 0
                
                self.logger.log(f"Found {len(individuals)} individual(s) in popup", "info")
                
                # Process each individual
                for radio, individual_name in individuals:
                    try:
                        # Click to select this individual
                        self.safe_click(radio)
                        time.sleep(2)
                        
                        # Download any directly available files for this individual
                        count = self.download_from_popup(individual_name, page_number)
                        downloaded_count += count
                        
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
            
            # Find the page number for this person from mapping
            mapped_page = self.find_person_in_mapping(name)
            if mapped_page is None:
                mapped_page = page_number
            
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
            if download_link:
                self.logger.log(f"Found direct table download for: {name}", "info")
                if self.download_file(download_link, name, mapped_page):
                    downloaded_something = True
            
            # If there's a request link, open the form to find "(click to download)" files
            if request_link:
                request_url = request_link.get_attribute('href')
                if request_url:
                    self.logger.log(f"Checking form for downloadable files: {name}", "info")
                    count = self.process_request_form_for_downloads(request_url, name, mapped_page)
                    if count > 0:
                        downloaded_something = True
            
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
            # Load mapping first
            if not self.load_mapping():
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
            self.logger.log_summary(self.total_downloaded, self.total_skipped, self.total_no_download)
            
            # Final summary
            self.logger.log("=== DIRECT DOWNLOAD COMPLETE ===", "success")
            self.logger.log(f"Total files downloaded: {self.total_downloaded}", "info")
            self.logger.log(f"Total files skipped (already exist): {self.total_skipped}", "info")
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
    print(f"Mapping file: {MAPPING_FILE}")
    print(f"Downloads to: {DOWNLOADS_ROOT}")
    print("=" * 60)
    print()
    print("This script will:")
    print("   1. Navigate to the OGE website")
    print("   2. Filter by 'Transaction' type")
    print("   3. Sort by Name (A-Z)")
    print(f"   4. Navigate to pages {START_PAGE}-{END_PAGE}")
    print("   5. Download ONLY directly available files (no form submission)")
    print("   6. Organize files by Page/PersonName")
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

