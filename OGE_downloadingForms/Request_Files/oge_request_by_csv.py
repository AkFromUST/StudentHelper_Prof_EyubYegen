#!/usr/bin/env python3
"""
OGE Document Request Automation Script - CSV Based
Automates the process of requesting documents from the 
U.S. Office of Government Ethics website using a CSV list of names.

Reads names from not_found_in_all_reqs.csv and processes each one.
"""

import csv
import time
import os
import re
import json
import sys
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

# Add parent directory to path to import config
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

try:
    import config
    print(f"✓ Config loaded successfully from: {parent_dir}")
    print(f"  - User: {config.USER_NAME}")
    print(f"  - Email: {config.USER_EMAIL}")
except ImportError as e:
    print(f"✗ Error importing config: {e}")
    print(f"  - Tried to import from: {parent_dir}")
    sys.exit(1)


class RequestLogger:
    """Handles logging of requests to CSV and progress to Markdown."""
    
    def __init__(self, log_file: str = "request_files_log.csv", progress_file: str = "request_files_progress.md"):
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
                    key = f"{row.get('name', '')}|{row.get('individual_full_name', '')}|{row.get('file_name', '')}"
                    self.processed_entries.add(key)
            print(f"📂 Loaded {len(self.processed_entries)} previously processed entries from log")
    
    def _init_progress_file(self):
        """Initialize the progress markdown file."""
        if not os.path.exists(self.progress_file):
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                f.write("# OGE Document Request Progress (CSV Based)\n\n")
                f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**Configuration:**\n")
                f.write(f"- User: {config.USER_NAME}\n")
                f.write(f"- Email: {config.USER_EMAIL}\n")
                f.write(f"- CSV File: ./AutomationComparison/results/not_found_in_all_reqs.csv\n\n")
                f.write("---\n\n")
    
    def is_duplicate(self, name: str, individual_full_name: str, file_name: str = "") -> bool:
        """Check if an entry has already been processed."""
        key = f"{name}|{individual_full_name}|{file_name}"
        return key in self.processed_entries
    
    def log_request(self, name: str, individual_full_name: str, 
                    files_requested: list, status: str, batch_number: int):
        """Log a request to the CSV file."""
        file_exists = os.path.exists(self.log_file)
        
        with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['timestamp', 'csv_name', 'individual_full_name', 
                         'file_name', 'status', 'batch_number']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            for file_name_item in files_requested:
                key = f"{name}|{individual_full_name}|{file_name_item}"
                self.processed_entries.add(key)
                
                writer.writerow({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'csv_name': name,
                    'individual_full_name': individual_full_name,
                    'file_name': file_name_item,
                    'status': status,
                    'batch_number': batch_number
                })
    
    def log_progress(self, message: str, level: str = "info"):
        """Log progress to the markdown file."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "start": "🚀"}
        icon = icons.get(level, "•")
        
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"- `{timestamp}` {icon} {message}\n")
        
        print(f"{icon} [{timestamp}] {message}")
    
    def log_name_summary(self, name: str, batches_made: int, individuals_processed: int):
        """Log summary for a completed name."""
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"\n### Name '{name}' Summary\n")
            f.write(f"- Batches submitted: {batches_made}\n")
            f.write(f"- Individuals processed: {individuals_processed}\n")
            f.write("---\n\n")


class OGERequestByCSV:
    """Main automation class for OGE document requests from CSV."""
    
    def __init__(self, headless: bool = False):
        self.driver = None
        self.wait = None
        self.logger = RequestLogger()
        self.headless = headless
        self.requested_docs_tracker = self.load_requested_docs_tracker()
        self.form_url = "https://extapps2.oge.gov/201/Presiden.nsf/201%20Request?OpenForm"
    
    def get_individual_key(self, individual_full_name: str) -> str:
        """Generate a unique key for tracking documents per individual."""
        return individual_full_name.strip().lower()
    
    def load_requested_docs_tracker(self) -> Dict[str, List[str]]:
        """Load the persistent tracker of requested documents."""
        tracker_file = os.path.join(os.path.dirname(__file__), "requested_documents.json")
        try:
            if os.path.exists(tracker_file):
                with open(tracker_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.logger.log_progress(f"Loaded {len(data)} entries from requested docs tracker", "info")
                    return data
        except Exception as e:
            self.logger.log_progress(f"Error loading requested docs tracker: {e}", "warning")
        return {}
    
    def save_requested_docs_tracker(self):
        """Save the requested documents tracker to disk."""
        tracker_file = os.path.join(os.path.dirname(__file__), "requested_documents.json")
        try:
            with open(tracker_file, 'w', encoding='utf-8') as f:
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
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
        self.wait = WebDriverWait(self.driver, config.ELEMENT_WAIT_TIMEOUT)
        
        self.logger.log_progress("Chrome WebDriver initialized", "start")
    
    def safe_click(self, element, retries: int = 3):
        """Safely click an element with retry logic."""
        for attempt in range(retries):
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
                element.click()
                return True
            except (StaleElementReferenceException, ElementClickInterceptedException) as e:
                if attempt < retries - 1:
                    time.sleep(0.5)
                else:
                    raise e
        return False
    
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
    
    def navigate_to_form_page(self):
        """Navigate to the OGE request form page."""
        self.logger.log_progress(f"Navigating to OGE request form page: {self.form_url}")
        self.driver.get(self.form_url)
        time.sleep(3)
        
        # Verify page loaded
        try:
            current_url = self.driver.current_url
            self.logger.log_progress(f"Current URL: {current_url}", "info")
        except Exception as e:
            self.logger.log_progress(f"Error getting current URL: {e}", "warning")
    
    def close_all_extra_tabs(self, main_window: str):
        """Close ALL extra tabs and switch back to main window."""
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
    
    def read_csv_names(self, csv_path: str) -> List[str]:
        """Read names from the CSV file."""
        names = []
        # Get the script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Build the full path
        full_path = os.path.normpath(os.path.join(script_dir, csv_path))
        
        self.logger.log_progress(f"Reading CSV from: {full_path}", "info")
        
        try:
            if not os.path.exists(full_path):
                self.logger.log_progress(f"CSV file not found: {full_path}", "error")
                return []
            
            with open(full_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get('Name', '').strip()
                    if name:
                        names.append(name)
            
            self.logger.log_progress(f"Read {len(names)} names from CSV: {names}", "info")
        except Exception as e:
            self.logger.log_progress(f"Error reading CSV: {e}", "error")
            import traceback
            self.logger.log_progress(f"Traceback: {traceback.format_exc()}", "error")
        
        return names
    
    def get_all_individuals_from_popup(self, last_name: str) -> List[str]:
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
        """Select a specific individual from the popup by their full name."""
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
    
    def select_files_from_popup(self, individual_full_name: str, already_requested: set = None) -> tuple:
        """Select available files from the popup after selecting an individual.
        
        Returns:
            tuple: (files_selected: bool, selected_file_names: list)
        """
        selected_file_names = []
        
        if already_requested is None:
            already_requested = set()
        
        try:
            time.sleep(2)
            
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
                return (False, selected_file_names)
            
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
                return (False, selected_file_names)
            
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
                    return (True, selected_file_names)
                except NoSuchElementException:
                    pass
                
                # Try input button
                try:
                    add_btn = self.driver.find_element(By.XPATH, "//input[@value='Add to Cart']")
                    self.safe_click(add_btn)
                    self.logger.log_progress("Clicked Add to Cart button", "success")
                    time.sleep(2)
                    return (True, selected_file_names)
                except NoSuchElementException:
                    pass
                
                self.logger.log_progress("Could not find Add to Cart button", "warning")
                return (True, selected_file_names)  # Files were selected
            
            return (False, selected_file_names)
            
        except Exception as e:
            self.logger.log_progress(f"Error selecting files from popup: {e}", "warning")
            return (False, selected_file_names)
    
    def fill_request_form(self):
        """Fill in the personal information form."""
        try:
            # Verify we're on a valid window
            try:
                current_url = self.driver.current_url
                self.logger.log_progress(f"Current URL before filling: {current_url}", "info")
            except Exception as e:
                self.logger.log_progress(f"Cannot access current window: {e}", "error")
                return
            
            time.sleep(2)
            
            # Fill Name: <input name="Name" value="" id="Name" class="usa-input">
            try:
                name_field = self.driver.find_element(By.ID, "Name")
                name_field.clear()
                name_field.send_keys(config.USER_NAME)
                self.logger.log_progress(f"Filled Name: {config.USER_NAME}", "success")
            except Exception as e:
                self.logger.log_progress(f"Error filling Name: {e}", "error")
                return
            
            time.sleep(0.5)
            
            # Fill Email: <input name="Email" value="" id="Email" class="usa-input">
            try:
                email_field = self.driver.find_element(By.ID, "Email")
                email_field.clear()
                email_field.send_keys(config.USER_EMAIL)
                self.logger.log_progress(f"Filled Email: {config.USER_EMAIL}", "success")
            except Exception as e:
                self.logger.log_progress(f"Error filling Email: {e}", "error")
                return
            
            time.sleep(0.5)
            
            # Fill Occupation: <input name="Occupation" value="" id="Occupation" class="usa-input">
            try:
                occupation_field = self.driver.find_element(By.ID, "Occupation")
                occupation_field.clear()
                occupation_field.send_keys(config.USER_OCCUPATION)
                self.logger.log_progress(f"Filled Occupation: {config.USER_OCCUPATION}", "success")
            except Exception as e:
                self.logger.log_progress(f"Error filling Occupation: {e}", "error")
                return
            
            time.sleep(0.5)
            
            # Check Private citizen: <input type="checkbox" name="RequestorOrgType" value="Private citizen">
            try:
                private_cb = self.driver.find_element(By.XPATH, "//input[@type='checkbox' and @value='Private citizen']")
                if not private_cb.is_selected():
                    private_cb.click()
                    self.logger.log_progress("Checked 'Private citizen'", "success")
                else:
                    self.logger.log_progress("'Private citizen' already checked", "info")
            except Exception as e:
                self.logger.log_progress(f"Error checking Private citizen: {e}", "error")
                return
            
            time.sleep(0.5)
            
            # Check Awareness: <input type="checkbox" name="CheckBoxAgree" id="CheckBoxAgree">
            try:
                awareness_cb = self.driver.find_element(By.ID, "CheckBoxAgree")
                if not awareness_cb.is_selected():
                    awareness_cb.click()
                    self.logger.log_progress("Checked awareness checkbox", "success")
                else:
                    self.logger.log_progress("Awareness already checked", "info")
            except Exception as e:
                self.logger.log_progress(f"Error checking awareness: {e}", "error")
                return
            
            self.logger.log_progress("Form filled successfully", "success")
            time.sleep(1)
            
        except Exception as e:
            self.logger.log_progress(f"Error in fill_request_form: {e}", "error")
            import traceback
            self.logger.log_progress(f"Traceback: {traceback.format_exc()[:200]}", "error")
    
    def submit_request(self) -> bool:
        """Submit the request form."""
        try:
            # Verify we're on a valid window
            try:
                current_url = self.driver.current_url
                self.logger.log_progress(f"Current URL before submit: {current_url}", "info")
            except Exception as e:
                self.logger.log_progress(f"Cannot access window for submit: {e}", "error")
                return False
            
            # Find Submit button: <input class="usa-button" value="Submit Request">
            try:
                submit_btn = self.driver.find_element(By.XPATH, "//input[@class='usa-button' and @value='Submit Request']")
                self.logger.log_progress("Found Submit button", "info")
            except Exception as e:
                self.logger.log_progress(f"Cannot find Submit button: {e}", "error")
                return False
            
            # Click it
            try:
                submit_btn.click()
                self.logger.log_progress("Clicked Submit button", "success")
                time.sleep(3)
            except Exception as e:
                self.logger.log_progress(f"Error clicking Submit: {e}", "error")
                return False
            
            # Handle alert
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                self.logger.log_progress(f"Alert: {alert_text[:60]}...", "info")
                alert.accept()
                self.logger.log_progress("Clicked OK", "success")
                time.sleep(1)
            except NoAlertPresentException:
                self.logger.log_progress("No alert appeared", "warning")
            except Exception as e:
                self.logger.log_progress(f"Alert error: {e}", "warning")
            
            return True
            
        except Exception as e:
            self.logger.log_progress(f"Error in submit_request: {e}", "error")
            return False
    
    def process_name_from_csv(self, last_name: str) -> tuple:
        """Process a name from the CSV file.
        
        Returns:
            tuple: (batches_submitted: int, individuals_processed: int)
        """
        batches_submitted = 0
        individuals_processed_set = set()
        
        try:
            self.logger.log_progress(f"=== Processing name: {last_name} ===", "start")
            
            # Track ALL individuals found in popup (populated on first open)
            all_individuals = None
            # Track which individuals are fully processed
            processed_individuals = set()
            
            # Store main window handle
            main_window = self.driver.current_window_handle
            
            # Ensure we start with only the main tab
            self.close_all_extra_tabs(main_window)
            
            # Navigate to form page (only once at the start)
            self.navigate_to_form_page()
            time.sleep(2)
            
            # MAIN LOOP: Keep processing until all individuals are done
            batch_count = 0
            while True:
                batch_count += 1
                self.logger.log_progress(f"Starting batch {batch_count} for '{last_name}'", "info")
                
                # Verify we're still on a valid page
                try:
                    current_url = self.driver.current_url
                    self.logger.log_progress(f"Current URL: {current_url}", "info")
                except Exception as e:
                    self.logger.log_progress(f"Window error: {e}", "error")
                    break
                
                # Wait for the "Find Individual by Name" button
                try:
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@class='usa-button' and @value='Find Individual by Name']")))
                except:
                    time.sleep(3)
                
                # Enter last name in the field (using ID: LastName)
                try:
                    self.logger.log_progress("Looking for LastName input field (ID='LastName')...", "info")
                    last_name_field = self.driver.find_element(By.ID, "LastName")
                    self.logger.log_progress("Found LastName field, clearing and entering text...", "info")
                    last_name_field.clear()
                    last_name_field.send_keys(last_name)
                    self.logger.log_progress(f"Successfully entered last name: {last_name}", "success")
                    time.sleep(1)
                except NoSuchElementException as e:
                    self.logger.log_progress(f"LastName field not found by ID. Error: {e}", "error")
                    # Try alternate method
                    try:
                        self.logger.log_progress("Trying to find by name attribute...", "info")
                        last_name_field = self.driver.find_element(By.NAME, "LastName")
                        last_name_field.clear()
                        last_name_field.send_keys(last_name)
                        self.logger.log_progress(f"Successfully entered last name via name attribute: {last_name}", "success")
                        time.sleep(1)
                    except Exception as e2:
                        self.logger.log_progress(f"Could not find last name field by any method: {e2}", "error")
                        break
                except Exception as e:
                    self.logger.log_progress(f"Error with last name field: {e}", "error")
                    break
                
                # Click "Find Individual by Name" to open popup
                try:
                    self.logger.log_progress("Looking for 'Find Individual by Name' button...", "info")
                    windows_before = set(self.driver.window_handles)
                    self.logger.log_progress(f"Windows before click: {len(windows_before)}", "info")
                    
                    # Try to find the button
                    find_btn = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@class='usa-button' and @value='Find Individual by Name']"))
                    )
                    self.logger.log_progress("Found button, clicking...", "info")
                    self.safe_click(find_btn)
                    time.sleep(3)
                    
                    # Check for popup
                    windows_after = set(self.driver.window_handles)
                    new_windows = windows_after - windows_before
                    self.logger.log_progress(f"Windows after click: {len(windows_after)}, New windows: {len(new_windows)}", "info")
                    
                    if not new_windows:
                        self.logger.log_progress("No popup opened after clicking button", "warning")
                        break
                    
                    popup_window = new_windows.pop()
                    self.driver.switch_to.window(popup_window)
                    time.sleep(2)
                    
                    # Get ALL individuals from popup (only on first iteration)
                    if all_individuals is None:
                        all_individuals = self.get_all_individuals_from_popup(last_name)
                        if not all_individuals:
                            self.logger.log_progress("No matching individuals found in popup", "warning")
                            self.close_all_extra_tabs(main_window)
                            break
                        self.logger.log_progress(f"Found {len(all_individuals)} individual(s) to process", "info")
                    
                    # Find the first individual that still has unrequested documents
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
                        individuals_processed_set.add(individual_full_name)
                        
                        # Select files from popup
                        files_selected, selected_names = self.select_files_from_popup(
                            individual_full_name, requested_docs
                        )
                        
                        if files_selected and selected_names:
                            # Found work to do for this individual
                            found_work = True
                            
                            # Close popup and switch back to main window
                            try:
                                self.driver.close()
                            except:
                                pass
                            
                            # Make sure we're back on the main window
                            time.sleep(1)
                            try:
                                self.driver.switch_to.window(main_window)
                                self.logger.log_progress("Switched back to main window", "info")
                            except Exception as e:
                                self.logger.log_progress(f"Error switching to main window: {e}", "error")
                                # Try to find any valid window
                                handles = self.driver.window_handles
                                if handles:
                                    self.driver.switch_to.window(handles[0])
                            
                            time.sleep(2)  # Give form time to load
                            
                            # Add to tracking
                            self.add_requested_docs_for_individual(individual_full_name, selected_names)
                            
                            # Fill and submit form
                            self.fill_request_form()
                            if self.submit_request():
                                batches_submitted += 1
                                self.logger.log_request(
                                    name=last_name,
                                    individual_full_name=individual_full_name,
                                    files_requested=selected_names,
                                    status='submitted',
                                    batch_number=batches_submitted
                                )
                                self.logger.log_progress(f"Batch {batches_submitted} submitted successfully", "success")
                            else:
                                self.logger.log_progress("Form submission failed", "warning")
                            
                            # Ensure we're back on main window and close any extra tabs
                            try:
                                self.driver.switch_to.window(main_window)
                            except:
                                # If main window is gone, get any available window
                                handles = self.driver.window_handles
                                if handles:
                                    self.driver.switch_to.window(handles[0])
                                    main_window = handles[0]
                            
                            # Close any extra windows
                            all_handles = self.driver.window_handles
                            for handle in all_handles:
                                if handle != main_window:
                                    try:
                                        self.driver.switch_to.window(handle)
                                        self.driver.close()
                                    except:
                                        pass
                            
                            # Make sure we're on main window
                            try:
                                self.driver.switch_to.window(main_window)
                            except:
                                handles = self.driver.window_handles
                                if handles:
                                    self.driver.switch_to.window(handles[0])
                                    main_window = handles[0]
                            
                            time.sleep(2)
                            self.logger.log_progress("Ready for next batch", "info")
                            break  # Exit for loop to continue while loop
                            
                        else:
                            # No more files for this individual - mark as processed
                            self.logger.log_progress(f"Individual done: {individual_full_name[:50]}...", "success")
                            processed_individuals.add(individual_full_name.lower())
                            # Continue to next individual in the for loop
                    
                    if not found_work:
                        # All individuals are done!
                        self.logger.log_progress(f"All {len(all_individuals)} individual(s) processed ({batches_submitted} batches total)", "success")
                        # Close popup if still open
                        try:
                            self.driver.close()
                        except:
                            pass
                        self.close_all_extra_tabs(main_window)
                        break
                        
                except TimeoutException:
                    self.logger.log_progress("Could not find 'Find Individual by Name' button", "warning")
                    self.close_all_extra_tabs(main_window)
                    break
                except Exception as e:
                    self.logger.log_progress(f"Error in form processing: {e}", "warning")
                    self.close_all_extra_tabs(main_window)
                    break
            
            return (batches_submitted, len(individuals_processed_set))
            
        except Exception as e:
            self.logger.log_progress(f"Error processing name '{last_name}': {e}", "error")
            return (batches_submitted, len(individuals_processed_set))
    
    def run(self):
        """Main execution method."""
        try:
            self.setup_driver()
            
            # Read names from CSV
            csv_path = "../AutomationComparison/results/not_found_in_all_reqs.csv"
            names = self.read_csv_names(csv_path)
            
            if not names:
                self.logger.log_progress("No names found in CSV file", "error")
                return
            
            total_batches = 0
            total_individuals = 0
            
            # Process each name
            for idx, name in enumerate(names, 1):
                self.logger.log_progress(f"Processing name {idx}/{len(names)}: {name}", "start")
                
                batches, individuals = self.process_name_from_csv(name)
                total_batches += batches
                total_individuals += individuals
                
                self.logger.log_name_summary(name, batches, individuals)
                
                # Small delay between names
                time.sleep(2)
            
            # Final summary
            self.logger.log_progress(f"=== AUTOMATION COMPLETE ===", "success")
            self.logger.log_progress(f"Total names processed: {len(names)}", "info")
            self.logger.log_progress(f"Total batches submitted: {total_batches}", "info")
            self.logger.log_progress(f"Total individuals processed: {total_individuals}", "info")
            
            with open(self.logger.progress_file, 'a', encoding='utf-8') as f:
                f.write(f"\n## Final Summary\n")
                f.write(f"- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"- **Total names processed:** {len(names)}\n")
                f.write(f"- **Total batches submitted:** {total_batches}\n")
                f.write(f"- **Total individuals processed:** {total_individuals}\n")
            
        except Exception as e:
            self.logger.log_progress(f"Critical error: {e}", "error")
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                try:
                    # Only wait for user input if running interactively
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
    parser = argparse.ArgumentParser(description='OGE Document Request Automation (CSV Based)')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    args = parser.parse_args()
    
    print("=" * 60)
    print("OGE Document Request Automation (CSV Based)")
    print("=" * 60)
    print(f"User: {config.USER_NAME}")
    print(f"Email: {config.USER_EMAIL}")
    print(f"CSV File: ./AutomationComparison/results/not_found_in_all_reqs.csv")
    print(f"Max files per batch: {config.MAX_FILES_PER_BATCH}")
    print("=" * 60)
    print()
    print("⚠️  This script will:")
    print("   1. Read names from not_found_in_all_reqs.csv")
    print("   2. For each name, navigate to the OGE request form")
    print("   3. Search for individuals with that last name")
    print("   4. Request all available documents (in batches of 5)")
    print("   5. Track progress in requested_documents.json")
    print("   6. You will receive files via email later")
    print()
    
    if not args.yes:
        response = input("Do you want to proceed? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted by user.")
            return
    else:
        print("✓ Auto-confirmed with --yes flag")
    
    automation = OGERequestByCSV(headless=args.headless)
    automation.run()


if __name__ == "__main__":
    main()
