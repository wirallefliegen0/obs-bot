"""
Debug script to analyze OBS login page with visible browser.
Run this to see how the page looks and find the captcha.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

OBS_LOGIN_URL = "https://obs.btu.edu.tr/oibs/std/login.aspx"

# Setup browser (NOT headless - we want to see it)
options = Options()
options.add_argument("--window-size=1400,900")
options.add_argument("--disable-blink-features=AutomationControlled")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    print("[*] Opening OBS login page...")
    driver.get(OBS_LOGIN_URL)
    
    # Wait for page to load
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "txtParamT01"))
    )
    
    time.sleep(2)
    
    print("\n" + "="*60)
    print("PAGE ANALYSIS")
    print("="*60)
    
    # Get page title
    print(f"\nPage Title: {driver.title}")
    
    # Find all input elements
    print("\n--- INPUT ELEMENTS ---")
    inputs = driver.find_elements(By.TAG_NAME, "input")
    for inp in inputs:
        inp_id = inp.get_attribute("id")
        inp_name = inp.get_attribute("name")
        inp_type = inp.get_attribute("type")
        inp_visible = inp.is_displayed()
        if inp_id:
            print(f"  ID: {inp_id:25} | Type: {inp_type:10} | Visible: {inp_visible}")
    
    # Look for captcha-related elements
    print("\n--- SEARCHING FOR CAPTCHA ---")
    
    # Check for images
    images = driver.find_elements(By.TAG_NAME, "img")
    print(f"\nFound {len(images)} images:")
    for img in images:
        img_id = img.get_attribute("id") or "no-id"
        img_src = img.get_attribute("src") or "no-src"
        img_alt = img.get_attribute("alt") or ""
        if img.is_displayed():
            print(f"  ID: {img_id} | Alt: {img_alt} | Src: {img_src[:80]}...")
    
    # Look for canvas elements (often used for captcha)
    canvases = driver.find_elements(By.TAG_NAME, "canvas")
    print(f"\nFound {len(canvases)} canvas elements")
    
    # Look for spans near txtSecCode
    print("\n--- ELEMENTS NEAR CAPTCHA INPUT ---")
    try:
        sec_code_input = driver.find_element(By.ID, "txtSecCode")
        parent = sec_code_input.find_element(By.XPATH, "./..")
        print(f"Parent element: {parent.tag_name}")
        print(f"Parent text: {parent.text}")
        
        # Get siblings
        siblings = parent.find_elements(By.XPATH, "./*")
        print(f"\nSiblings ({len(siblings)}):")
        for sib in siblings:
            print(f"  Tag: {sib.tag_name:10} | ID: {sib.get_attribute('id') or 'no-id':20} | Text: {sib.text[:50] if sib.text else 'no-text'}")
    except Exception as e:
        print(f"Error finding captcha area: {e}")
    
    # Get all visible text
    print("\n--- ALL VISIBLE TEXT (looking for numbers) ---")
    body_text = driver.find_element(By.TAG_NAME, "body").text
    lines = [line.strip() for line in body_text.split('\n') if line.strip()]
    for line in lines:
        # Only show lines with numbers
        if any(c.isdigit() for c in line):
            print(f"  {line}")
    
    # Take screenshot
    screenshot_path = "c:/Users/userl/Desktop/oku/obs_screenshot.png"
    driver.save_screenshot(screenshot_path)
    print(f"\n[+] Screenshot saved to: {screenshot_path}")
    
    print("\n[*] Browser will stay open for 30 seconds for manual inspection...")
    print("    Look at the captcha and tell me what you see!")
    time.sleep(30)
    
except Exception as e:
    print(f"[!] Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    driver.quit()
    print("\n[*] Browser closed")
