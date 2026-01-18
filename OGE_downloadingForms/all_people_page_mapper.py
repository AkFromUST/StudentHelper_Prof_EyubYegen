#!/usr/bin/env python3
"""
OGE All People to Page Mapper Script

A script that:
1. Navigates to the OGE website
2. Filters by Transaction type and sorts by Name
3. For each UNIQUE person (by name), opens the request form popup
4. Clicks "Find Individual by Name"
5. Collects ALL individuals from the popup list
6. Maps each individual's full name to their page number (as a hashmap)
7. Saves after EVERY row to peopleToPage.json for persistent tracking

Features:
- Loads existing mapping on startup (resume capability)
- Saves after every row (no data loss)
- Uses hashmap logic (no duplicate keys - only first occurrence is recorded)
- Tracks processed names in peopleSeen.json to skip duplicate rows for same person
  (e.g., if "Abbott, James" has 3 rows, only the first one is processed)
- Does NOT submit any requests - only collects mapping data

Output Files:
- peopleToPage.json: Maps individual full names to page numbers
- peopleSeen.json: Tracks which names have been processed (to skip duplicates)
"""

import json
import time
import os
from datetime import datetime
from typing import Dict, Set

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

import config

# Configuration
OUTPUT_FILE = "peopleToPage.json"
PEOPLE_SEEN_FILE = "peopleSeen.json"


class AllPeoplePageMapper:
    """Maps ALL individuals (from request form popups) to their page numbers."""
    
    def __init__(self, headless: bool = False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self.current_page = 1
        self.people_to_page: Dict[str, int] = {}
        self.people_seen: Dict[str, bool] = {}  # Hashmap to track names we've already processed
        self.processed_rows: Set[str] = set()  # Track processed rows to avoid duplicates
        self.load_existing_mapping()  # Load existing data if available
        self.load_people_seen()  # Load existing people seen tracking
    
    def log(self, message: str, level: str = "info"):
        """Simple logging to console."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "start": "🚀"}
        icon = icons.get(level, "•")
        print(f"{icon} [{timestamp}] {message}")
    
    def load_existing_mapping(self):
        """Load existing mapping from file if it exists (for recovery/resume)."""
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    self.people_to_page = json.load(f)
                print(f"📂 Loaded {len(self.people_to_page)} existing entries from {OUTPUT_FILE}")
            except Exception as e:
                print(f"⚠️  Could not load existing mapping: {e}")
                self.people_to_page = {}
        else:
            print(f"ℹ️  No existing mapping file found. Starting fresh.")
    
    def load_people_seen(self):
        """Load existing people seen tracking from file if it exists."""
        if os.path.exists(PEOPLE_SEEN_FILE):
            try:
                with open(PEOPLE_SEEN_FILE, 'r', encoding='utf-8') as f:
                    self.people_seen = json.load(f)
                print(f"📂 Loaded {len(self.people_seen)} names from {PEOPLE_SEEN_FILE}")
            except Exception as e:
                print(f"⚠️  Could not load people seen tracking: {e}")
                self.people_seen = {}
        else:
            print(f"ℹ️  No people seen tracking file found. Starting fresh.")
    
    def save_people_seen(self, verbose: bool = False):
        """Save the people seen tracking to JSON file (hashmap persistence).
        
        Args:
            verbose: If True, log the save operation
        """
        try:
            with open(PEOPLE_SEEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.people_seen, f, indent=2, ensure_ascii=False, sort_keys=True)
            if verbose:
                self.log(f"💾 Saved {len(self.people_seen)} names to {PEOPLE_SEEN_FILE}", "success")
        except Exception as e:
            self.log(f"Error saving people seen tracking: {e}", "error")
    
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
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
        self.wait = WebDriverWait(self.driver, config.ELEMENT_WAIT_TIMEOUT)
        
        self.log("Chrome WebDriver initialized", "start")
    
    def dismiss_alert(self):
        """Dismiss any alert dialogs that may appear."""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            self.log(f"Dismissing alert: {alert_text[:50]}...", "warning")
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
        self.log("Navigating to OGE website...")
        self.driver.get(config.BASE_URL)
        time.sleep(2)
    
    def handle_affirm_banner(self) -> bool:
        """Handle the 'I affirm' legal banner by clicking on it."""
        try:
            self.log("Looking for affirm banner...")
            
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
                            self.log("Clicked affirm banner", "success")
                            time.sleep(2)
                            self.wait_for_table_load()
                            return True
                except NoSuchElementException:
                    continue
            
            self.log("No affirm banner found or already dismissed", "info")
            return True
        except Exception as e:
            self.log(f"Error handling affirm banner: {e}", "warning")
            return True
    
    def filter_by_transaction(self) -> bool:
        """Filter the table to show only Transaction type."""
        try:
            self.dismiss_alert()
            self.log("Filtering by Transaction type...")
            
            type_filter = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Filter Type']"))
            )
            
            type_filter.clear()
            type_filter.send_keys("Transaction")
            
            time.sleep(2)
            self.dismiss_alert()
            self.wait_for_table_load()
            
            self.log("Applied Transaction filter", "success")
            return True
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.filter_by_transaction()
        except Exception as e:
            self.dismiss_alert()
            self.log(f"Error filtering by transaction: {e}", "error")
            return False
    
    def sort_by_name(self) -> bool:
        """Sort the table by Name column (alphabetical order)."""
        try:
            self.dismiss_alert()
            self.log("Sorting by Name column (A-Z)...")
            
            name_header = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//th[contains(., 'Name')]"))
            )
            
            self.safe_click(name_header)
            time.sleep(2)
            self.dismiss_alert()
            self.wait_for_table_load()
            
            # Check if sorting is ascending (A-Z). If not, click again.
            try:
                self.dismiss_alert()
                name_header = self.driver.find_element(By.XPATH, "//th[contains(., 'Name')]")
                aria_sort = name_header.get_attribute("aria-sort")
                
                if aria_sort == "descending":
                    self.log("Clicking again for ascending order...")
                    self.safe_click(name_header)
                    time.sleep(2)
                    self.dismiss_alert()
                    self.wait_for_table_load()
            except (UnexpectedAlertPresentException, NoAlertPresentException):
                self.dismiss_alert()
            except:
                pass
            
            self.log("Sorted by Name column (A-Z)", "success")
            return True
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.sort_by_name()
        except Exception as e:
            self.dismiss_alert()
            self.log(f"Error sorting by name: {e}", "error")
            return False
    
    def navigate_to_page(self, page_number: int) -> bool:
        """Navigate to a specific page number."""
        try:
            self.dismiss_alert()
            
            if self.current_page == page_number:
                return True
            
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
                    else:
                        break
                except UnexpectedAlertPresentException:
                    self.dismiss_alert()
                    continue
                except NoSuchElementException:
                    self.log(f"Could not find Next button at page {self.current_page}", "warning")
                    return False
            
            return self.current_page == page_number
            
        except UnexpectedAlertPresentException:
            self.dismiss_alert()
            return self.navigate_to_page(page_number)
        except Exception as e:
            self.dismiss_alert()
            self.log(f"Error navigating to page {page_number}: {e}", "error")
            return False
    
    def has_next_page(self) -> bool:
        """Check if there's a next page available."""
        try:
            next_btn = self.driver.find_element(By.XPATH, "//a[contains(text(), 'Next')]")
            parent = next_btn.find_element(By.XPATH, "./..")
            classes = parent.get_attribute("class") or ""
            return "disabled" not in classes.lower()
        except NoSuchElementException:
            return False
        except Exception:
            return False
    
    def get_table_rows(self) -> list:
        """Get all data rows from the current table page."""
        try:
            time.sleep(0.5)
            rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
            return rows
        except Exception as e:
            self.log(f"Error getting table rows: {e}", "warning")
            return []
    
    def extract_row_data(self, row) -> dict:
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
                try:
                    request_link = type_cell.find_element(By.XPATH, ".//a[contains(text(), 'Request this Document')]")
                except NoSuchElementException:
                    pass
                
                return {
                    'date_added': cells[0].text.strip(),
                    'title': cells[1].text.strip(),
                    'type': type_text,
                    'name': cells[3].text.strip(),
                    'agency': cells[4].text.strip(),
                    'is_transaction': is_transaction,
                    'request_link': request_link,
                }
        except (StaleElementReferenceException, Exception):
            pass
        return None
    
    def close_all_extra_tabs(self, main_window: str):
        """Close ALL extra tabs and return to main window."""
        try:
            self.driver.switch_to.window(main_window)
            time.sleep(0.5)
            
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
            self.log(f"Error closing tabs: {e}", "warning")
            return False
    
    def get_all_individuals_from_popup(self, page_number: int) -> int:
        """Get ALL individuals from the popup and add them to the mapping.
        
        Returns:
            Number of individuals found and added
        """
        individuals_found = 0
        
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
                    
                    # Only record the FIRST occurrence of each individual (hashmap - no duplicates)
                    if label_text_original not in self.people_to_page:
                        self.people_to_page[label_text_original] = page_number
                        individuals_found += 1
                        self.log(f"  Added: {label_text_original[:60]}... → page {page_number}", "info")
                    else:
                        self.log(f"  Skipped (already exists): {label_text_original[:60]}...", "info")
                        
                except:
                    continue
            
        except Exception as e:
            self.log(f"Error getting individuals from popup: {e}", "warning")
        
        return individuals_found
    
    def process_row_for_individuals(self, row_data: dict, page_number: int) -> int:
        """Process a single row to extract all individuals from the popup.
        
        Returns:
            Number of individuals found
        """
        individuals_found = 0
        
        try:
            request_link = row_data['request_link']
            request_url = request_link.get_attribute('href')
            
            # Store main window handle
            main_window = self.driver.current_window_handle
            
            # Ensure we start with only the main tab
            self.close_all_extra_tabs(main_window)
            
            # Extract last name from the name
            name_parts = row_data['name'].split(',')
            last_name = name_parts[0].strip()
            
            # Open form in new tab
            self.log(f"Opening form for: {row_data['name']}...", "info")
            self.driver.execute_script("window.open(arguments[0], '_blank');", request_url)
            time.sleep(3)
            
            # Switch to new tab
            new_tabs = [h for h in self.driver.window_handles if h != main_window]
            if not new_tabs:
                self.log("Failed to open form tab", "warning")
                return 0
            
            self.driver.switch_to.window(new_tabs[0])
            time.sleep(5)  # Wait for page to load
            
            # Wait for the "Find Individual by Name" button
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='Find Individual by Name']")))
            except:
                time.sleep(3)
            
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
                    self.log("No popup opened", "warning")
                    self.close_all_extra_tabs(main_window)
                    return 0
                
                popup_window = new_windows.pop()
                self.driver.switch_to.window(popup_window)
                time.sleep(2)
                
                # Get all individuals from popup and add to mapping
                individuals_found = self.get_all_individuals_from_popup(page_number)
                self.log(f"Found {individuals_found} individual(s) for {row_data['name']}", "success")
                
                # Close popup and all extra tabs
                self.close_all_extra_tabs(main_window)
                
            except TimeoutException:
                self.log("Could not find 'Find Individual by Name' button", "warning")
                self.close_all_extra_tabs(main_window)
                return 0
            except Exception as e:
                self.log(f"Error in form processing: {e}", "warning")
                self.close_all_extra_tabs(main_window)
                return 0
            
            return individuals_found
            
        except Exception as e:
            self.log(f"Error processing row: {e}", "error")
            try:
                main_window = self.driver.window_handles[0]
                self.close_all_extra_tabs(main_window)
            except:
                pass
            return 0
    
    def process_page(self, page_number: int) -> int:
        """Process all rows on a given page.
        
        Returns:
            Total individuals found on this page
        """
        total_individuals = 0
        
        self.log(f"=== Processing Page {page_number} ===", "start")
        
        rows = self.get_table_rows()
        total_rows = len(rows)
        self.log(f"Found {total_rows} rows on page {page_number}")
        
        for row_index, row in enumerate(rows):
            try:
                row_data = self.extract_row_data(row)
                
                if not row_data:
                    continue
                
                # Skip non-transaction types
                if not row_data['is_transaction']:
                    continue
                
                # Skip if no request link
                if not row_data['request_link']:
                    continue
                
                # Check if we've already processed this person's name (hashmap check)
                person_name = row_data['name']
                if person_name in self.people_seen:
                    self.log(f"⏭️  Skipping {person_name[:40]}... (already processed)", "info")
                    continue
                
                # Create unique key for this row to avoid duplicates
                row_key = f"{row_data['name']}|{row_data['title']}|{row_data['date_added']}"
                if row_key in self.processed_rows:
                    self.log(f"Skipping duplicate row: {row_data['name'][:30]}...", "info")
                    continue
                
                self.processed_rows.add(row_key)
                
                # Process this row to get all individuals
                individuals_found = self.process_row_for_individuals(row_data, page_number)
                total_individuals += individuals_found
                
                # Mark this person as seen in the hashmap
                self.people_seen[person_name] = True
                
                # Save both files after EVERY row for persistent tracking (silent save)
                self.save_mapping(verbose=False)
                self.save_people_seen(verbose=False)
                self.log(f"💾 Row {row_index + 1}/{total_rows} complete. Total: {len(self.people_to_page)} individuals, {len(self.people_seen)} names processed", "info")
                
                # Small delay between rows
                time.sleep(1)
                
            except StaleElementReferenceException:
                time.sleep(1)
                continue
            except Exception as e:
                self.log(f"Error processing row {row_index}: {e}", "error")
                continue
        
        self.log(f"Page {page_number} complete: {total_individuals} new individuals found", "success")
        return total_individuals
    
    def save_mapping(self, verbose: bool = False):
        """Save the people to page mapping to JSON file (hashmap persistence).
        
        Args:
            verbose: If True, log the save operation
        """
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.people_to_page, f, indent=2, ensure_ascii=False, sort_keys=True)
            if verbose:
                self.log(f"💾 Saved {len(self.people_to_page)} entries to {OUTPUT_FILE}", "success")
        except Exception as e:
            self.log(f"Error saving mapping: {e}", "error")
    
    def run(self, start_page: int = None, end_page: int = None):
        """Main execution method.
        
        Args:
            start_page: Page to start from (default: config.START_PAGE)
            end_page: Page to end at (default: config.END_PAGE)
        """
        if start_page is None:
            start_page = config.START_PAGE
        if end_page is None:
            end_page = config.END_PAGE
            
        try:
            self.setup_driver()
            self.navigate_to_main_page()
            self.handle_affirm_banner()
            
            # Apply filters
            if not self.filter_by_transaction():
                self.log("Warning: Transaction filter may not have been applied", "warning")
            
            # Sort by name
            if not self.sort_by_name():
                self.log("Warning: Name sorting may not have been applied", "warning")
            
            # Navigate to start page if needed
            if start_page > 1:
                self.log(f"Navigating to start page {start_page}...")
                if not self.navigate_to_page(start_page):
                    self.log(f"Could not navigate to page {start_page}", "error")
                    return
            
            total_individuals = 0
            
            for page in range(start_page, end_page + 1):
                self.log(f"Starting page {page}...")
                
                # Navigate to page
                if not self.navigate_to_page(page):
                    self.log(f"Could not navigate to page {page}, stopping", "warning")
                    break
                
                # Process all rows on this page
                individuals_found = self.process_page(page)
                total_individuals += individuals_found
                
                # Save progress after each page (verbose)
                self.save_mapping(verbose=True)
                self.save_people_seen(verbose=True)
            
            # Final save (verbose)
            self.save_mapping(verbose=True)
            self.save_people_seen(verbose=True)
            
            self.log(f"=== MAPPING COMPLETE ===", "success")
            self.log(f"Total unique individuals collected: {len(self.people_to_page)}", "info")
            self.log(f"Total unique names processed: {len(self.people_seen)}", "info")
            self.log(f"Pages processed: {start_page} to {page}", "info")
            self.log(f"Output saved to: {OUTPUT_FILE}", "info")
            self.log(f"Names tracking saved to: {PEOPLE_SEEN_FILE}", "info")
            
        except Exception as e:
            self.log(f"Critical error: {e}", "error")
            import traceback
            traceback.print_exc()
            # Save whatever we have (verbose)
            self.save_mapping(verbose=True)
            self.save_people_seen(verbose=True)
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
                    self.log("Browser closed", "info")


def main():
    """Entry point for the script."""
    import argparse
    parser = argparse.ArgumentParser(description='OGE All People to Page Mapper')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--start', type=int, default=None, help=f'Start page number (default: {config.START_PAGE} from config)')
    parser.add_argument('--end', type=int, default=None, help=f'End page number (default: {config.END_PAGE} from config)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    args = parser.parse_args()
    
    # Use config values if not specified
    start_page = args.start if args.start is not None else config.START_PAGE
    end_page = args.end if args.end is not None else config.END_PAGE
    
    print("=" * 60)
    print("OGE All People to Page Mapper")
    print("=" * 60)
    print(f"Individual mapping output: {OUTPUT_FILE}")
    print(f"Names tracking output: {PEOPLE_SEEN_FILE}")
    print(f"Start page: {start_page}")
    print(f"End page: {end_page}")
    print("=" * 60)
    print()
    print("This script will:")
    print("   1. Navigate to the OGE website")
    print("   2. Filter by 'Transaction' type")
    print("   3. Sort by Name (A-Z)")
    print(f"   4. Process pages {start_page} to {end_page}")
    print("   5. For each unique person (skip duplicate names):")
    print("      - Open the request form")
    print("      - Click 'Find Individual by Name'")
    print("      - Collect ALL individuals from the popup")
    print("      - Map each individual to their page number")
    print("   6. Save mapping to peopleToPage.json after every row")
    print("   7. Track seen names in peopleSeen.json (skip duplicates)")
    print()
    print("⚠️  NOTE: This script will NOT submit any requests!")
    print("   It only collects the individual-to-page mapping.")
    print("   Multiple rows for same person = only first row processed.")
    print()
    
    # Check if there's existing data
    existing_individuals = 0
    existing_names = 0
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f:
                existing_data = json.load(f)
                existing_individuals = len(existing_data)
        except:
            pass
    
    if os.path.exists(PEOPLE_SEEN_FILE):
        try:
            with open(PEOPLE_SEEN_FILE, 'r') as f:
                existing_seen = json.load(f)
                existing_names = len(existing_seen)
        except:
            pass
    
    if existing_individuals > 0 or existing_names > 0:
        print(f"📂 Found existing data:")
        if existing_individuals > 0:
            print(f"   - {existing_individuals} individuals in {OUTPUT_FILE}")
        if existing_names > 0:
            print(f"   - {existing_names} names already processed in {PEOPLE_SEEN_FILE}")
        print("   Script will resume and add new data (no duplicates)")
        print()
    
    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")
    
    mapper = AllPeoplePageMapper(headless=args.headless)
    mapper.run(start_page=start_page, end_page=end_page)


if __name__ == "__main__":
    main()
