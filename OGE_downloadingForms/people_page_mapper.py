#!/usr/bin/env python3
"""
OGE People to Page Mapper Script

A lightweight script that:
1. Navigates to the OGE website
2. Filters by Transaction type and sorts by Name
3. Collects all person names and maps them to their page numbers
4. Saves the mapping to peopleToPage.json
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


class PeoplePageMapper:
    """Maps people names to their page numbers on the OGE website."""
    
    def __init__(self, headless: bool = False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self.current_page = 1
        self.people_to_page: Dict[str, int] = {}
        self.seen_names: Set[str] = set()  # Track unique names per page
    
    def log(self, message: str, level: str = "info"):
        """Simple logging to console."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "start": "🚀"}
        icon = icons.get(level, "•")
        print(f"{icon} [{timestamp}] {message}")
    
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
    
    def get_total_pages(self) -> int:
        """Get the total number of pages available."""
        try:
            # Look for pagination info - usually shows "Page X of Y" or similar
            # Or find the last page number link
            page_links = self.driver.find_elements(By.XPATH, "//a[contains(@class, 'paginate')]")
            
            max_page = 1
            for link in page_links:
                try:
                    text = link.text.strip()
                    if text.isdigit():
                        max_page = max(max_page, int(text))
                except:
                    continue
            
            # Also check for "..." followed by a number
            try:
                last_link = self.driver.find_element(By.XPATH, "//span[@class='paginate_button' and contains(text(), '...')]/following-sibling::a[1]")
                last_num = last_link.text.strip()
                if last_num.isdigit():
                    max_page = max(max_page, int(last_num))
            except:
                pass
            
            self.log(f"Detected approximately {max_page}+ pages", "info")
            return max_page
        except Exception as e:
            self.log(f"Could not determine total pages: {e}", "warning")
            return 100  # Default to a high number, we'll stop when no more pages
    
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
            # Check if the Next button is disabled
            parent = next_btn.find_element(By.XPATH, "./..")
            classes = parent.get_attribute("class") or ""
            return "disabled" not in classes.lower()
        except NoSuchElementException:
            return False
        except Exception:
            return False
    
    def extract_names_from_page(self, page_number: int) -> int:
        """Extract all names from the current page and add to mapping."""
        names_found = 0
        
        try:
            rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
            
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 4:
                        # Name is in the 4th column (index 3)
                        name = cells[3].text.strip()
                        
                        if name and name != "Loading":
                            # Only record the FIRST occurrence of each name
                            if name not in self.people_to_page:
                                self.people_to_page[name] = page_number
                                names_found += 1
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
            
        except Exception as e:
            self.log(f"Error extracting names: {e}", "warning")
        
        return names_found
    
    def save_mapping(self):
        """Save the people to page mapping to JSON file."""
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.people_to_page, f, indent=2, ensure_ascii=False)
            self.log(f"Saved {len(self.people_to_page)} entries to {OUTPUT_FILE}", "success")
        except Exception as e:
            self.log(f"Error saving mapping: {e}", "error")
    
    def run(self, start_page: int = None, end_page: int = None):
        """Main execution method.
        
        Args:
            start_page: Page to start from (default: config.START_PAGE)
            end_page: Page to end at (default: config.END_PAGE)
        """
        # Use config values as defaults
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
            
            page = start_page
            total_names = 0
            
            while True:
                self.log(f"Processing page {page}...")
                
                # Extract names from current page
                names_found = self.extract_names_from_page(page)
                total_names += names_found
                
                self.log(f"Page {page}: Found {names_found} new unique names (Total: {len(self.people_to_page)})")
                
                # Save progress periodically (every 10 pages)
                if page % 10 == 0:
                    self.save_mapping()
                
                # Check if we should stop
                if end_page and page >= end_page:
                    self.log(f"Reached end page {end_page}", "info")
                    break
                
                # Check if there's a next page
                if not self.has_next_page():
                    self.log("No more pages available", "info")
                    break
                
                # Navigate to next page
                page += 1
                if not self.navigate_to_page(page):
                    self.log(f"Could not navigate to page {page}, stopping", "warning")
                    break
            
            # Final save
            self.save_mapping()
            
            self.log(f"=== MAPPING COMPLETE ===", "success")
            self.log(f"Total unique names collected: {len(self.people_to_page)}", "info")
            self.log(f"Pages processed: {start_page} to {page}", "info")
            self.log(f"Output saved to: {OUTPUT_FILE}", "info")
            
        except Exception as e:
            self.log(f"Critical error: {e}", "error")
            import traceback
            traceback.print_exc()
            # Save whatever we have
            self.save_mapping()
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
    parser = argparse.ArgumentParser(description='OGE People to Page Mapper')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--start', type=int, default=None, help=f'Start page number (default: {config.START_PAGE} from config)')
    parser.add_argument('--end', type=int, default=None, help=f'End page number (default: {config.END_PAGE} from config)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    args = parser.parse_args()
    
    # Use config values if not specified
    start_page = args.start if args.start is not None else config.START_PAGE
    end_page = args.end if args.end is not None else config.END_PAGE
    
    print("=" * 60)
    print("OGE People to Page Mapper")
    print("=" * 60)
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Start page: {start_page}")
    print(f"End page: {end_page}")
    print("=" * 60)
    print()
    print("This script will:")
    print("   1. Navigate to the OGE website")
    print("   2. Filter by 'Transaction' type")
    print("   3. Sort by Name (A-Z)")
    print(f"   4. Process pages {start_page} to {end_page}")
    print("   5. Collect all names and their page numbers")
    print("   6. Save mapping to peopleToPage.json")
    print()
    
    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")
    
    mapper = PeoplePageMapper(headless=args.headless)
    mapper.run(start_page=start_page, end_page=end_page)


if __name__ == "__main__":
    main()

