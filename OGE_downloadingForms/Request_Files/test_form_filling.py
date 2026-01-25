#!/usr/bin/env python3
"""
Test script to verify form filling works with exact HTML selectors.
This script will:
1. Navigate to the form page
2. Enter a test last name
3. Click Find Individual by Name
4. Handle the popup (select first individual)
5. Select first available document
6. Fill the form using EXACT HTML selectors
7. STOP before submitting (so you can verify)
"""

import os
import sys
import time

# Add parent directory to path to import config
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

import config

def setup_driver():
    """Initialize the Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    
    return driver

def main():
    print("=" * 70)
    print("OGE Form Filling Test - Using Exact HTML Selectors")
    print("=" * 70)
    print()
    print("This script will test form filling with the exact HTML elements.")
    print("It will STOP before submitting so you can verify.")
    print()
    
    test_name = input("Enter a last name to test (e.g., 'hamilton'): ").strip()
    if not test_name:
        print("No name provided, using 'hamilton' as default")
        test_name = "hamilton"
    
    print()
    print(f"Testing with name: {test_name}")
    print()
    
    driver = setup_driver()
    wait = WebDriverWait(driver, 15)
    
    try:
        # Navigate to form
        print("1. Navigating to form page...")
        form_url = "https://extapps2.oge.gov/201/Presiden.nsf/201%20Request?OpenForm"
        driver.get(form_url)
        time.sleep(3)
        print(f"   Current URL: {driver.current_url}")
        
        # Enter last name
        # HTML: <input name="LastName" value="" id="LastName" class="usa-input" title="LastName">
        print(f"\n2. Entering last name: {test_name}")
        last_name_field = driver.find_element(By.ID, "LastName")
        last_name_field.clear()
        last_name_field.send_keys(test_name)
        print("   ✓ Last name entered")
        time.sleep(1)
        
        # Click Find Individual by Name
        # HTML: <input class="usa-button" value="Find Individual by Name" onclick="getdocs();">
        print("\n3. Clicking 'Find Individual by Name' button...")
        windows_before = set(driver.window_handles)
        find_btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@class='usa-button' and @value='Find Individual by Name']"))
        )
        find_btn.click()
        time.sleep(3)
        
        # Check for popup
        windows_after = set(driver.window_handles)
        new_windows = windows_after - windows_before
        
        if not new_windows:
            print("   ✗ No popup opened")
            return
        
        print(f"   ✓ Popup opened ({len(new_windows)} new window)")
        
        # Switch to popup
        popup_window = new_windows.pop()
        driver.switch_to.window(popup_window)
        time.sleep(2)
        
        # Find and select first individual
        print("\n4. Looking for individuals in popup...")
        radio_buttons = driver.find_elements(By.XPATH, "//input[@type='radio']")
        
        if not radio_buttons:
            print("   ✗ No individuals found")
            return
        
        print(f"   Found {len(radio_buttons)} individual(s)")
        
        # Select first one
        first_radio = radio_buttons[0]
        parent = first_radio.find_element(By.XPATH, "./..")
        individual_name = parent.text.strip()
        print(f"   Selecting: {individual_name[:70]}...")
        first_radio.click()
        time.sleep(2)
        
        # Find and select first checkbox
        print("\n5. Looking for documents...")
        checkboxes = driver.find_elements(By.XPATH, "//table//input[@type='checkbox']")
        
        if not checkboxes:
            print("   ✗ No document checkboxes found")
            return
        
        print(f"   Found {len(checkboxes)} document(s)")
        
        # Select first one
        first_cb = checkboxes[0]
        cell = first_cb.find_element(By.XPATH, "./ancestor::td[1]")
        doc_name = cell.text.strip()
        print(f"   Selecting: {doc_name[:50]}...")
        first_cb.click()
        time.sleep(1)
        
        # Click Add to Cart
        print("\n6. Clicking 'Add to Cart'...")
        try:
            add_btn = driver.find_element(By.XPATH, "//input[@value='Add to Cart']")
            add_btn.click()
            time.sleep(2)
            print("   ✓ Clicked Add to Cart")
        except:
            print("   ✗ Could not find Add to Cart button")
            return
        
        # Close popup
        driver.close()
        
        # Switch back to form
        form_tabs = [h for h in driver.window_handles if h not in windows_before]
        if form_tabs:
            driver.switch_to.window(form_tabs[0])
        time.sleep(1)
        
        # Fill form using EXACT HTML selectors
        print("\n" + "=" * 70)
        print("7. Filling form fields using EXACT HTML selectors...")
        print("=" * 70)
        
        # Name
        # HTML: <input name="Name" value="" id="Name" class="usa-input">
        print("\na) Name field:")
        try:
            name_field = driver.find_element(By.ID, "Name")
            name_field.clear()
            time.sleep(0.2)
            name_field.send_keys(config.USER_NAME)
            print(f"   ✓ Name: {config.USER_NAME}")
        except Exception as e:
            print(f"   ✗ Could not fill Name field: {e}")
        
        time.sleep(0.3)
        
        # Email
        # HTML: <input name="Email" value="" id="Email" class="usa-input">
        print("\nb) Email field:")
        try:
            email_field = driver.find_element(By.ID, "Email")
            email_field.clear()
            time.sleep(0.2)
            email_field.send_keys(config.USER_EMAIL)
            print(f"   ✓ Email: {config.USER_EMAIL}")
        except Exception as e:
            print(f"   ✗ Could not fill Email field: {e}")
        
        time.sleep(0.3)
        
        # Occupation
        # HTML: <input name="Occupation" value="" id="Occupation" class="usa-input">
        print("\nc) Occupation field:")
        try:
            occupation_field = driver.find_element(By.ID, "Occupation")
            occupation_field.clear()
            time.sleep(0.2)
            occupation_field.send_keys(config.USER_OCCUPATION)
            print(f"   ✓ Occupation: {config.USER_OCCUPATION}")
        except Exception as e:
            print(f"   ✗ Could not fill Occupation field: {e}")
        
        time.sleep(0.3)
        
        # Radio button (No) - skipping for now as it's usually default
        print("\nd) 'No' radio button:")
        print("   ℹ  Skipping (usually selected by default)")
        
        time.sleep(0.3)
        
        # Private citizen checkbox
        # HTML: <input type="checkbox" name="RequestorOrgType" value="Private citizen" id="RequestorOrgType" class="usa-checkbox">
        print("\ne) 'Private citizen' checkbox:")
        try:
            private_cb = driver.find_element(By.XPATH, "//input[@type='checkbox' and @value='Private citizen']")
            if not private_cb.is_selected():
                private_cb.click()
                print("   ✓ Checked 'Private citizen'")
            else:
                print("   ✓ 'Private citizen' already checked")
        except NoSuchElementException:
            print("   ✗ Could not find 'Private citizen' checkbox by value")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        time.sleep(0.3)
        
        # Awareness checkbox
        # HTML: <input type="checkbox" name="CheckBoxAgree" value="I am aware of the above statutes and regulations. (required)" id="CheckBoxAgree">
        print("\nf) Awareness checkbox:")
        try:
            awareness_checkbox = driver.find_element(By.ID, "CheckBoxAgree")
            if not awareness_checkbox.is_selected():
                awareness_checkbox.click()
                print("   ✓ Checked awareness checkbox")
            else:
                print("   ✓ Awareness checkbox already checked")
        except NoSuchElementException:
            print("   ✗ Could not find awareness checkbox")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print("\n" + "=" * 70)
        print("FORM FILLED - STOPPED BEFORE SUBMISSION")
        print("=" * 70)
        print("\nSubmit button HTML:")
        print('  <input class="usa-button" value="Submit Request" onclick="return validate201new2();">')
        print()
        print("Please verify the form in the browser window:")
        print("  ✓ Name: " + config.USER_NAME)
        print("  ✓ Email: " + config.USER_EMAIL)
        print("  ✓ Occupation: " + config.USER_OCCUPATION)
        print("  ✓ 'Private citizen' checkbox checked")
        print("  ✓ 'I am aware...' checkbox checked")
        print()
        print("If everything looks correct, the full script should work!")
        print()
        print("Press Enter to close the browser...")
        input()
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\nPress Enter to close the browser...")
        input()
    finally:
        driver.quit()
        print("Browser closed")

if __name__ == "__main__":
    main()
