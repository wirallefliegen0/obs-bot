"""
BTU OBS Web Scraper Module - Selenium + Gemini Vision Edition.
Handles login and grade fetching from the OBS system using Selenium and Gemini Vision for captcha.
"""
"""
import os
import re
import time
import io
import base64
from typing import Optional
from PIL import Image
import pytesseract
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, UnexpectedAlertPresentException, NoAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager
import config

# Try to import Gemini (new SDK)
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ... (omitted parts)



# Set Tesseract path - check environment variable first, then use OS default
tesseract_path = os.getenv('TESSERACT_PATH')
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
elif os.name == 'nt':  # Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# Linux uses default path (/usr/bin/tesseract) which pytesseract finds automatically


class OBSSession:
    """Manages authenticated session with BTU OBS system using Selenium."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.logged_in = False
    
    def _init_driver(self):
        """Initialize Chrome WebDriver."""
        if self.driver:
            return
        
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    def _dismiss_alerts(self, accept: bool = True) -> bool:
        """
        Dismiss any native browser alerts/confirms/prompts.
        
        Args:
            accept: If True, click OK/Accept. If False, click Cancel/Dismiss.
        
        Returns:
            True if an alert was handled, False otherwise.
        """
        handled = False
        max_attempts = 5  # Handle multiple stacked alerts
        for _ in range(max_attempts):
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                print(f"[*] Found browser alert: '{alert_text}'")
                if accept:
                    alert.accept()
                    print("[*] Alert accepted (OK clicked)")
                else:
                    alert.dismiss()
                    print("[*] Alert dismissed (Cancel clicked)")
                handled = True
                time.sleep(0.5)
            except NoAlertPresentException:
                break
            except Exception as e:
                print(f"[!] Error handling alert: {e}")
                break
        return handled
    
    def _preprocess_captcha_image(self, image: Image.Image, threshold: int = 128, aggressive: bool = False) -> Image.Image:
        """
        Preprocess captcha image for better OCR results.
        BTU OBS captcha has noisy colorful dots that need to be removed.
        """
        from PIL import ImageFilter
        
        # Convert to grayscale
        image = image.convert('L')
        
        # Apply median filter to reduce noise (dots)
        if aggressive:
            image = image.filter(ImageFilter.MedianFilter(size=3))
        
        # Resize for better OCR (larger = more detail)
        width, height = image.size
        image = image.resize((width * 4, height * 4), Image.Resampling.LANCZOS)
        
        # Apply threshold to binarize
        image = image.point(lambda p: 255 if p > threshold else 0)
        
        # Additional cleanup for aggressive mode
        if aggressive:
            # Erode then dilate to remove small dots
            image = image.filter(ImageFilter.MaxFilter(size=3))
            image = image.filter(ImageFilter.MinFilter(size=3))
        
        return image
    
    def _solve_captcha_with_gemini(self, image: Image.Image) -> Optional[str]:
        """Solve captcha using Gemini Vision API (google-genai SDK)."""
        if not GEMINI_AVAILABLE:
            print("[!] Gemini API (google-genai) not available")
            return None
        
        if not config.GEMINI_API_KEY:
            print("[!] GEMINI_API_KEY not configured")
            return None
        
        try:
            # Configure Gemini Client
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            
            # Convert image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            # Create the prompt
            prompt = """Bu bir matematik captcha görüntüsüdür. """
Görüntüdeki matematik işlemini çöz ve SADECE sayısal cevabı ver.
Örnek: Eğer görüntü "25+17=?" ise, sadece "42" yaz.
Başka hiçbir şey yazma, sadece sonuç sayısını yaz."""

            # Try multiple models in order of preference/availability
            # Updated model names based on current Gemini API (2025)
            models_to_try = [
                'gemini-2.0-flash',           # Latest stable flash
                'gemini-2.0-flash-exp',       # Experimental flash variant
                'gemini-1.5-flash',           # Stable flash (widely available)
                'gemini-1.5-flash-latest',    # Latest 1.5 flash
                'gemini-1.5-pro',             # Stable pro (more capable)
                'gemini-1.5-pro-latest',      # Latest 1.5 pro
                'gemini-pro',                 # Base pro model
                'models/gemini-1.5-flash',    # Full model path format
                'models/gemini-1.5-pro',      # Full model path format
            ]
            
            response = None
            used_model = None
            last_error = None
            
            for model_id in models_to_try:
                try:
                    print(f"[*] Trying Gemini model: {model_id}")
                    
                    max_gemini_retries = 2
                    for i in range(max_gemini_retries):
                        try:
                            response = client.models.generate_content(
                                model=model_id,
                                contents=[
                                    prompt,
                                    types.Part.from_bytes(
                                        data=img_byte_arr.getvalue(),
                                        mime_type="image/png"
                                    )
                                ]
                            )
                            used_model = model_id
                            break # Success for this model
                        except Exception as e:
                            last_error = str(e)
                            # Rate limit handling
                            if "429" in str(e) and i < max_gemini_retries - 1:
                                wait_time = 5 * (i + 1)
                                print(f"[*] Rate limited, waiting {wait_time}s...")
                                time.sleep(wait_time)
                                img_byte_arr.seek(0)
                            else:
                                raise e # Re-raise to try next model
                    
                    if response:
                        break # Found a working model and got response
                        
                except Exception as e:
                    last_error = str(e)
                    error_str = str(e).lower()
                    # Log the actual error for debugging
                    if "404" in error_str or "not found" in error_str:
                        print(f"[!] Model {model_id}: Not found")
                    elif "403" in error_str or "permission" in error_str:
                        print(f"[!] Model {model_id}: Permission denied")
                    elif "invalid" in error_str:
                        print(f"[!] Model {model_id}: Invalid request - {str(e)[:100]}")
                    else:
                        print(f"[!] Model {model_id}: Error - {str(e)[:100]}")
                    continue
            
            if not response:
                print(f"[!] All Gemini models failed. Last error: {last_error[:200] if last_error else 'Unknown'}")
                return None
            
            # Extract the answer
            if response and response.text:
                answer = response.text.strip()
                # Clean up - only keep digits
                answer = re.sub(r'[^0-9]', '', answer)
                
                if answer:
                    print(f"[*] Gemini Vision ({used_model}) answer: {answer}")
                    return answer
            
            print(f"[!] Gemini returned empty or invalid response")
            return None
                
        except Exception as e:
            print(f"[!] Gemini Vision error: {e}")
            return None
    
    def _try_multiple_ocr_approaches(self, original_image: Image.Image) -> list[str]:
        """Try multiple preprocessing approaches and return all results."""
        results = []
        
        # Try different thresholds
        thresholds = [90, 110, 128, 150, 180]
        
        # Prepare different image variants to try
        images_to_try = [original_image]
        
        # Color-based filtering: BTU captcha has colored dots as noise
        # The text is usually dark on lighter background
        # Try extracting just the darkest parts
        try:
            rgb_img = original_image.convert('RGB')
            # Create mask for pixels that are predominantly dark (text)
            # Filter out colorful noise by checking if pixel is more grayscale
            def is_text_pixel(r, g, b):
                # Text tends to be dark and grayscale
                brightness = (r + g + b) / 3
                color_variance = max(abs(r - brightness), abs(g - brightness), abs(b - brightness))
                # Accept dark pixels with low color variance (grayscale-ish)
                return brightness < 120 and color_variance < 50
            
            width, height = rgb_img.size
            filtered = Image.new('L', (width, height), 255)
            filtered_pixels = filtered.load()
            rgb_pixels = rgb_img.load()
            for y in range(height):
                for x in range(width):
                    r, g, b = rgb_pixels[x, y]
                    if is_text_pixel(r, g, b):
                        filtered_pixels[x, y] = 0
            images_to_try.append(filtered.convert('RGB'))
        except Exception as e:
            pass
        
        # Also try inverted image
        inverted = original_image.copy().convert('L')
        inverted = Image.eval(inverted, lambda x: 255 - x)
        images_to_try.append(inverted.convert('RGB'))
        
        # Try aggressive modes: with and without noise removal
        aggressive_modes = [False, True]
        
        for img in images_to_try:
            for thresh in thresholds:
                for aggressive in aggressive_modes:
                    processed = self._preprocess_captcha_image(img.copy(), threshold=thresh, aggressive=aggressive)
                    
                    # Try different OCR configs
                    configs = [
                        r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789+=?',
                        r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789+=?',
                        r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789+=?',
                    ]
                    
                    for cfg in configs:
                        try:
                            text = pytesseract.image_to_string(processed, config=cfg)
                            text = text.strip().replace(' ', '').replace('\n', '')
                            # Remove leading/trailing non-digits
                            text = re.sub(r'^[^0-9]*', '', text)
                            text = re.sub(r'[^0-9+\-=?]*$', '', text)
                            if text and any(c.isdigit() for c in text):
                                results.append(text)
                        except:
                            continue
        
        return list(set(results))  # Remove duplicates
    
    def _get_captcha_answer(self) -> Optional[str]:
        """Get captcha answer using Gemini Vision (preferred) or OCR fallback."""
        try:
            # Find the captcha image element
            captcha_img = self.driver.find_element(By.ID, "imgCaptchaImg")
            
            if not captcha_img:
                print("[!] Captcha image not found")
                return None
            
            # Take screenshot of the captcha element
            captcha_png = captcha_img.screenshot_as_png
            
            # Convert to PIL Image
            image = Image.open(io.BytesIO(captcha_png))
            
            # Save original for debugging
            image.save("captcha_original.png")
            
            # Try Gemini Vision first (most accurate)
            if config.GEMINI_API_KEY and GEMINI_AVAILABLE:
                print("[*] Trying Gemini Vision for captcha...")
                answer = self._solve_captcha_with_gemini(image)
                if answer:
                    return answer
                print("[!] Gemini Vision failed, falling back to OCR...")
            
            # Fallback to OCR
            print("[*] Using OCR for captcha...")
            results = self._try_multiple_ocr_approaches(image)
            
            print(f"[*] OCR found {len(results)} different readings: {results}")
            
            # Score each result based on how "captcha-like" it is
            # BTU OBS captcha format: NN+MM=? (e.g., 61+8=?)
            def score_result(text):
                score = 0
                
                # Best format: has + sign
                if '+' in text:
                    score += 15
                elif '-' in text:
                    score += 12
                
                # Bonus for having =? at end
                if '=?' in text:
                    score += 10
                elif '=' in text:
                    score += 5
                
                # Extract numbers
                nums = re.findall(r'\d+', text)
                if len(nums) >= 2:
                    try:
                        # Typical captcha uses small-ish numbers
                        if all(1 <= int(n) < 200 for n in nums[:2]):
                            score += 8
                        # Prefer if first number is 2 digits (like 61, 38, etc.)
                        if len(nums[0]) >= 2:
                            score += 3
                    except ValueError:
                        pass
                
                # Penalize if only 1 number found
                if len(nums) < 2:
                    score -= 10
                
                # Penalize very long results (probably junk)
                if len(text) > 12:
                    score -= 5
                
                # Penalize very short results
                if len(text) < 4:
                    score -= 5
                
                return score
            
            if results:
                # Sort results by score (descending)
                scored_results = [(r, score_result(r)) for r in results]
                scored_results.sort(key=lambda x: -x[1])
                
                # Display top candidates
                print("[*] Top OCR candidates:")
                for r, s in scored_results[:5]:
                    print(f"    '{r}' (score: {s})")
                
                best = scored_results[0][0]
                print(f"[*] Selected best: '{best}' (score: {scored_results[0][1]})")
                # Solve the math from OCR result
                return self.solve_math_captcha(best)
            
            return None
            
        except Exception as e:
            print(f"[!] Error getting captcha answer: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def solve_math_captcha(self, captcha_text: str) -> Optional[str]:
        """
        Solve simple math captcha like "42+5=?" or "12-4=?".
        If operator is not found, assumes addition (most common for BTU OBS).
        """
        captcha_text = captcha_text.strip()
        print(f"[*] Attempting to solve captcha: '{captcha_text}'")
        
        # Extract all numbers
        numbers = re.findall(r'\d+', captcha_text)
        
        if len(numbers) >= 2:
            num1 = int(numbers[0])
            num2 = int(numbers[1])
            
            # Determine operator
            if '+' in captcha_text:
                result = num1 + num2
                print(f"[*] Solving: {num1} + {num2} = {result}")
            elif '-' in captcha_text:
                result = num1 - num2
                print(f"[*] Solving: {num1} - {num2} = {result}")
            elif '*' in captcha_text or 'x' in captcha_text.lower():
                result = num1 * num2
                print(f"[*] Solving: {num1} * {num2} = {result}")
            else:
                # Default to addition for BTU OBS (most common)
                result = num1 + num2
                print(f"[*] No operator found, assuming addition: {num1} + {num2} = {result}")
            
            return str(result)
        
        elif len(numbers) == 1:
            # Special case: OCR might have merged everything
            # Try to split the number intelligently
            num_str = numbers[0]
            if len(num_str) >= 2:
                # Try splitting in different positions
                for i in range(1, len(num_str)):
                    num1 = int(num_str[:i])
                    num2 = int(num_str[i:])
                    if num1 < 100 and num2 < 100:  # Reasonable captcha numbers
                        result = num1 + num2
                        print(f"[*] Split guess: {num1} + {num2} = {result}")
                        return str(result)
        
        print(f"[!] Cannot solve captcha: {captcha_text}")
        return None
    
    def login(self, max_retries: int = 5) -> bool:
        """
        Login to BTU OBS system with retry mechanism.
        Retries on captcha failure since OCR might misread.
        """
        for attempt in range(1, max_retries + 1):
            print(f"\n[*] Login attempt {attempt}/{max_retries}")
            if self._attempt_login():
                return True
            
            if attempt < max_retries:
                print(f"[*] Retrying with fresh captcha...")
                time.sleep(2)
        
        print(f"[!] All {max_retries} login attempts failed")
        return False
    
    def _attempt_login(self) -> bool:
        """
        Login to BTU OBS system using Selenium with OCR captcha solving.
        Returns True if successful, False otherwise.
        """
        try:
            self._init_driver()
            
            print("[*] Navigating to login page...")
            self.driver.get(config.OBS_LOGIN_URL)
            
            # Wait for page to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "txtParamT01"))
            )
            
            # Wait for all elements to be ready
            time.sleep(3)
            
            # Fill username
            print("[*] Filling credentials...")
            username_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "txtParamT01"))
            )
            username_field.click()
            username_field.clear()
            username_field.send_keys(config.OBS_USERNAME)
            
            # Fill password
            password_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "txtParamT02"))
            )
            password_field.click()
            password_field.clear()
            password_field.send_keys(config.OBS_PASSWORD)
            
            # Get captcha answer (tries Gemini first, then OCR)
            time.sleep(1)
            print("[*] Solving captcha...")
            captcha_answer = self._get_captcha_answer()
            
            if captcha_answer:
                print(f"[*] Entering captcha answer: {captcha_answer}")
                captcha_field = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "txtSecCode"))
                )
                captcha_field.click()
                captcha_field.clear()
                captcha_field.send_keys(captcha_answer)
            else:
                print("[!] Failed to solve captcha")
                return False
            
            # Click login button
            print("[*] Clicking login button...")
            login_button = self.driver.find_element(By.ID, "btnLogin")
            login_button.click()
            
            # Wait for response - give more time for redirect to main page
            time.sleep(6)
            
            # Additional wait for page to stabilize
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda d: 'login.aspx' not in d.current_url.lower() or 
                              'çıkış' in d.page_source.lower() or
                              'start.aspx' in d.current_url.lower()
                )
            except:
                pass  # Timeout is OK, we'll check manually
            
            # Check if login successful
            page_source = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            if "çıkış" in page_source or "logout" in page_source or "hoşgeldiniz" in page_source or "start.aspx" in current_url:
                print("[+] Login successful!")
                self.logged_in = True
                return True
            
            # Check for specific error messages
            try:
                error_elements = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'error') or contains(@class, 'hata') or contains(@id, 'lbl') and contains(text(), 'hata')]")
                for elem in error_elements:
                    if elem.text:
                        print(f"[!] Login error: {elem.text}")
            except:
                pass
            
            print("[!] Login failed - unknown reason")
            return False
            
        except TimeoutException:
            print("[!] Timeout waiting for page to load")
            return False
        except Exception as e:
            print(f"[!] Error during login: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def fetch_grades(self) -> list[dict]:
        """
        Fetch current grades from OBS (Not Listesi page).
        
        BTU OBS Table Structure (from screenshot):
        | # | Ders Kodu | Ders Adı | Sonuç/Durumu | Sınav Notları (Vize/Kısa Sınv/Final) | Örf | Not | Durumu |
        
        The "Not" column contains the final grade (e.g., 89, AA).
        Returns list of grade dictionaries.
        """
        if not self.logged_in:
            print("[!] Not logged in, attempting login...")
            if not self.login():
                return []
        
        try:
            # Wait a bit for the page to stabilize after login
            time.sleep(3)
            
            # Debug: Show current state after login
            current_url = self.driver.current_url
            print(f"[*] Current URL after login: {current_url}")
            print(f"[*] Page title: {self.driver.title}")
            
            # Take screenshot of post-login state
            try:
                self.driver.save_screenshot("obs_after_login.png")
                print("[*] Saved post-login screenshot to obs_after_login.png")
            except:
                pass
            
            # We need to navigate to 'Not Listesi' through the sidebar menu
            # Path: Ders ve Dönem İşlemleri -> Not Listesi
            print("[*] Navigating to 'Not Listesi' via menu...")
            
            # Step 1: First click on "Ders ve Dönem İşlemleri" to expand submenu
            parent_menu_clicked = False
            parent_menu_xpaths = [
                "//a[contains(text(), 'Ders ve Dönem')]",
                "//span[contains(text(), 'Ders ve Dönem')]",
                "//*[contains(text(), 'Ders ve Dönem İşlemleri')]",
                "//td[contains(text(), 'Ders ve Dönem')]",
                "//div[contains(text(), 'Ders ve Dönem')]",
            ]
            
            for xpath in parent_menu_xpaths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    for elem in elements:
                        if elem.is_displayed():
                            print(f"[*] Found 'Ders ve Dönem İşlemleri' menu: {xpath}")
                            elem.click()
                            parent_menu_clicked = True
                            time.sleep(2)  # Wait for submenu to expand
                            break
                except Exception as e:
                    continue
                if parent_menu_clicked:
                    break
            
            if not parent_menu_clicked:
                print("[!] Could not find 'Ders ve Dönem İşlemleri' menu")
            
            # Step 2: Now click on "Not Listesi" submenu
            menu_clicked = False
            submenu_xpaths = [
                "//a[contains(text(), 'Not Listesi')]",
                "//span[contains(text(), 'Not Listesi')]",
                "//*[contains(text(), 'Not Listesi')]",
                "//td[contains(text(), 'Not Listesi')]",
                "//a[contains(@href, 'Not')]",
                "//a[contains(@title, 'Not Listesi')]",
            ]
            
            for xpath in submenu_xpaths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    for elem in elements:
                        if elem.is_displayed():
                            elem_text = elem.text.strip().lower()
                            # Make sure it's specifically "Not Listesi" and not just contains "Not"
                            if 'not listesi' in elem_text or 'not list' in elem_text:
                                print(f"[*] Found 'Not Listesi' submenu: {xpath}")
                                elem.click()
                                menu_clicked = True
                                time.sleep(3)  # Wait for grades page to load
                                break
                except Exception as e:
                    continue
                if menu_clicked:
                    break
            
            if not menu_clicked:
                print("[!] Could not find 'Not Listesi' submenu - trying direct click on any 'Not' link...")
                # Last resort: click any link with "Not" in text
                try:
                    all_links = self.driver.find_elements(By.TAG_NAME, "a")
                    for link in all_links:
                        link_text = link.text.strip().lower()
                        if 'not listesi' in link_text:
                            print(f"[*] Found link: '{link.text}'")
                            link.click()
                            menu_clicked = True
                            time.sleep(3)
                            break
                except:
                    pass
            
            if menu_clicked:
                print("[*] Navigated to 'Not Listesi' page!")
            else:
                print("[!] Could not navigate to 'Not Listesi'")
            
            # Wait for page to load
            print("[*] Waiting for page content to load...")
            time.sleep(3)
            
            # CRITICAL: Close any popup/modal that appears on the page
            # The grades page shows a "Notlar" info popup that blocks the table
            print("[*] Checking for popups/modals to close...")
            
            # FIRST: Handle any native browser alerts that might be present
            # These alerts block all Selenium interactions and must be dismissed first
            if self._dismiss_alerts(accept=True):
                print("[*] Dismissed initial browser alert(s)")
                time.sleep(1)
            
            popup_closed = False
            close_button_xpaths = [
                "//button[contains(@class, 'close')]",
                "//a[contains(@class, 'close')]",
                "//span[contains(@class, 'close')]",
                "//*[contains(@onclick, 'close')]",
                "//*[contains(@onclick, 'hide')]",
                "//div[contains(@class, 'modal')]//button",
                "//div[contains(@class, 'popup')]//button",
                "//button[text()='X' or text()='x']",
                "//a[text()='X' or text()='x']",
                "//*[@aria-label='Close']",
                "//button[contains(@class, 'btn-close')]",
                # Turkish close buttons
                "//button[contains(text(), 'Kapat')]",
                "//a[contains(text(), 'Kapat')]",
                "//input[@value='Kapat']",
                # X in various containers
                "//div[contains(@class, 'panel')]//a[contains(@href, 'javascript')]",
            ]
            
            for xpath in close_button_xpaths:
                try:
                    close_buttons = self.driver.find_elements(By.XPATH, xpath)
                    for btn in close_buttons:
                        if btn.is_displayed():
                            print(f"[*] Found close button: {xpath}")
                            try:
                                btn.click()
                                popup_closed = True
                                time.sleep(0.5)
                                # Handle any confirmation alert that appears after clicking
                                self._dismiss_alerts(accept=True)
                                print("[*] Clicked close button!")
                            except UnexpectedAlertPresentException:
                                # Alert appeared - handle it and continue
                                self._dismiss_alerts(accept=True)
                                popup_closed = True
                                print("[*] Handled alert after button click!")
                            except:
                                # Try JavaScript click
                                try:
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    popup_closed = True
                                    time.sleep(0.5)
                                    self._dismiss_alerts(accept=True)
                                    print("[*] Clicked close button via JS!")
                                except UnexpectedAlertPresentException:
                                    self._dismiss_alerts(accept=True)
                                    popup_closed = True
                                except:
                                    pass
                except UnexpectedAlertPresentException:
                    self._dismiss_alerts(accept=True)
                    continue
                except:
                    continue
            
            # Also try pressing Escape key to close any modal
            try:
                from selenium.webdriver.common.keys import Keys
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.5)
                self._dismiss_alerts(accept=True)
            except:
                pass
            
            # Final check for any remaining alerts
            self._dismiss_alerts(accept=True)
            
            if popup_closed:
                print("[*] Popup closed, waiting for table to be visible...")
                time.sleep(2)
            
            # Wait longer for AJAX/dynamic content to load
            time.sleep(2)
            
            # Check for iframes - OBS loads content in IFRAME1
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            print(f"[*] Found {len(iframes)} iframe(s) on page")
            
            switched_to_iframe = False
            if iframes:
                # First, try to find and switch to IFRAME1 specifically (main content frame)
                for iframe in iframes:
                    iframe_id = iframe.get_attribute("id") or "no-id"
                    iframe_src = iframe.get_attribute("src") or "no-src"
                    print(f"[*] Iframe: id='{iframe_id}' src='{iframe_src[:80] if iframe_src else 'no-src'}'")
                    
                    # IFRAME1 is the main content frame with the grades
                    if iframe_id == "IFRAME1":
                        try:
                            print(f"[*] Switching to main content iframe (IFRAME1)...")
                            self.driver.switch_to.frame(iframe)
                            switched_to_iframe = True
                            time.sleep(2)
                            
                            # Verify we're in the right frame by checking for tables
                            iframe_tables = self.driver.find_elements(By.TAG_NAME, "table")
                            print(f"[*] Found {len(iframe_tables)} tables in IFRAME1")
                            
                            # Check if we're on the semester averages page (Dönem Ortalamaları)
                            # If so, we need to click on the latest semester to view individual grades
                            try:
                                semester_table = self.driver.find_element(By.ID, "grdOrtalamasi")
                                if semester_table:
                                    print("[*] Found semester averages table - need to click on a semester")
                                    # Get all data rows (skip header row)
                                    rows = semester_table.find_elements(By.TAG_NAME, "tr")
                                    # Find the last data row (most recent semester)
                                    # Skip header rows (usually first row and last pagination row)
                                    data_rows = [r for r in rows if r.get_attribute("onclick") or 
                                                any("Select$" in (td.get_attribute("onclick") or "") 
                                                    for td in r.find_elements(By.TAG_NAME, "td"))]
                                    
                                    if data_rows:
                                        latest_row = data_rows[-1]
                                        semester_name = latest_row.text.split('\n')[0] if latest_row.text else "unknown"
                                        print(f"[*] Clicking on latest semester: '{semester_name}'")
                                        
                                        # Click on the first cell to trigger the Select action
                                        cells = latest_row.find_elements(By.TAG_NAME, "td")
                                        if cells:
                                            cells[0].click()
                                            time.sleep(3)  # Wait for grades to load
                                            print("[*] Clicked on semester row, waiting for grades...")
                                            
                                            # Handle any alert that might appear
                                            self._dismiss_alerts(accept=True)
                                    else:
                                        print("[!] No clickable semester rows found")
                            except Exception as e:
                                print(f"[*] Not on semester averages page or no table found: {e}")
                            
                            break
                        except Exception as e:
                            print(f"[!] Error switching to IFRAME1: {e}")
                            try:
                                self.driver.switch_to.default_content()
                            except:
                                pass
                
                # If IFRAME1 wasn't found, try other iframes with grades-related src
                if not switched_to_iframe:
                    for iframe in iframes:
                        try:
                            iframe_id = iframe.get_attribute("id") or "no-id"
                            iframe_src = iframe.get_attribute("src") or ""
                            
                            # Skip overlay/popup frames
                            if 'overlay' in iframe_id.lower() or iframe_src == "":
                                continue
                            
                            # Try switching to iframes that might contain grades
                            if 'not' in iframe_src.lower() or 'start' in iframe_src.lower():
                                print(f"[*] Trying iframe: id='{iframe_id}'...")
                                self.driver.switch_to.frame(iframe)
                                time.sleep(2)
                                
                                iframe_tables = self.driver.find_elements(By.TAG_NAME, "table")
                                if len(iframe_tables) > 1:
                                    print(f"[*] Found {len(iframe_tables)} tables in iframe!")
                                    switched_to_iframe = True
                                    break
                                else:
                                    self.driver.switch_to.default_content()
                        except Exception as e:
                            print(f"[!] Error with iframe: {e}")
                            try:
                                self.driver.switch_to.default_content()
                            except:
                                pass
            
            # Save page source for debugging
            try:
                page_source = self.driver.page_source
                with open("obs_grades_page.html", "w", encoding="utf-8") as f:
                    f.write(page_source)
                print(f"[*] Saved page source ({len(page_source)} chars) to obs_grades_page.html")
            except:
                pass
            
            # Take screenshot for debugging
            try:
                self.driver.save_screenshot("obs_grades_page.png")
                print("[*] Saved screenshot to obs_grades_page.png")
            except:
                pass
            
            # Debug: Print current URL and page title
            print(f"[*] Current URL: {self.driver.current_url}")
            print(f"[*] Page title: {self.driver.title}")
            
            # Debug: Print some page content to see what we got
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                print(f"[*] Page body length: {len(body_text)} chars")
                # Look for grade-related keywords
                if 'ders kodu' in body_text.lower():
                    print("[*] Page contains 'Ders Kodu' - likely grades page!")
                elif 'oturum' in body_text.lower():
                    print("[!] Page contains 'oturum' - might be session warning!")
                elif len(body_text) < 100:
                    print(f"[!] Page body very short! Content: {body_text}")
                # Preview first 300 chars
                print(f"[*] Page preview: {body_text[:300]}")
            except:
                pass
            
            grades = []
            
            # First, let's debug what tables exist on the page
            all_tables_debug = self.driver.find_elements(By.TAG_NAME, "table")
            print(f"[*] Total tables on page: {len(all_tables_debug)}")
            
            for idx, table in enumerate(all_tables_debug):
                try:
                    table_id = table.get_attribute("id") or "no-id"
                    table_class = table.get_attribute("class") or "no-class"
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    # Get first row text preview
                    first_row_text = ""
                    if rows:
                        cells = rows[0].find_elements(By.TAG_NAME, "td") or rows[0].find_elements(By.TAG_NAME, "th")
                        first_row_text = " | ".join([c.text.strip()[:20] for c in cells[:5]])
                    print(f"[*] Table {idx+1}: id='{table_id}' class='{table_class}' rows={len(rows)} preview='{first_row_text[:60]}'")
                except:
                    pass
            
            # Strategy: Look for the main grades table
            # The table should have columns like "Ders Kodu", "Ders Adı", "Not"
            table_xpaths = [
                "//table[contains(@id, 'grd')]",
                "//table[contains(@id, 'Grid')]",
                "//table[.//th[contains(text(), 'Ders') or contains(text(), 'Not')]]",
                "//table[.//td[contains(text(), 'Sonuç')]]",
                "//table[contains(@class, 'grid')]",
                "//table[contains(@class, 'DataGrid')]",
                "//div[contains(@class, 'content')]//table",
                "//table[@border]",
                "//table"
            ]
            
            main_table = None
            for xpath in table_xpaths:
                tables = self.driver.find_elements(By.XPATH, xpath)
                for table in tables:
                    # Check if this table looks like a grades table
                    table_text = table.text.lower()
                    if 'ders' in table_text or 'not' in table_text or 'vize' in table_text:
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        if len(rows) >= 2:  # At least header + 1 row
                            main_table = table
                            print(f"[*] Found grades table with xpath: {xpath}")
                            break
                if main_table:
                    break
            
            if not main_table:
                # Fallback: find any table with multiple rows that contains course-like content
                all_tables = self.driver.find_elements(By.TAG_NAME, "table")
                for table in all_tables:
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    if len(rows) >= 2:  # At least header + 1 data row
                        # Check if any cell looks like a course code (e.g., "BLM207", "AIT0101")
                        table_text = table.text
                        # Look for patterns like 3 letters + numbers
                        import re
                        if re.search(r'[A-Z]{2,4}\d{3,4}', table_text):
                            main_table = table
                            print(f"[*] Found table with course codes pattern, rows={len(rows)}")
                            break
                        elif len(rows) >= 5:  # Large table might be grades
                            main_table = table
                            print(f"[*] Using large fallback table with {len(rows)} rows")
                            break
            
            if not main_table:
                print("[!] No suitable grades table found!")
                return []
            
            # Parse the grades table
            table_id = main_table.get_attribute("id") or ""
            print(f"[*] Parsing table with ID: '{table_id}'")
            is_curriculum = "grd_ders" in table_id

            rows = main_table.find_elements(By.TAG_NAME, "tr")
            print(f"[*] Processing table with {len(rows)} rows")
            
            # Analyze header to find column indices
            header_row = rows[0] if rows else None
            header_cells = header_row.find_elements(By.TAG_NAME, "th") if header_row else []
            if not header_cells:
                header_cells = header_row.find_elements(By.TAG_NAME, "td") if header_row else []
            
            header_texts = [cell.text.strip().lower() for cell in header_cells]
            print(f"[*] Header columns: {header_texts}")
            
            # Find column indices (for generic table)
            code_idx = None
            name_idx = None
            grade_idx = None
            exam_grades_idx = None
            
            for i, header in enumerate(header_texts):
                if 'ders kodu' in header or header == 'ders kodu':
                    code_idx = i
                elif 'ders adı' in header or header == 'ders adı':
                    name_idx = i
                elif header == 'not' or header == 'harf notu':
                    grade_idx = i
                elif 'sınav' in header or 'vize' in header or 'final' in header:
                    exam_grades_idx = i
            
            if not is_curriculum:
                print(f"[*] Column indices - Code: {code_idx}, Name: {name_idx}, Grade: {grade_idx}")
            
            # Grade patterns to look for
            letter_grades = ["AA", "BA", "BB", "CB", "CC", "DC", "DD", "FF", "FD", "NA", "VZ", "MU"]
            
            # Process data rows
            for row_idx, row in enumerate(rows[1:], start=1):  # Skip header
                cols = row.find_elements(By.TAG_NAME, "td")
                
                # Special handling for Curriculum Table (grd_ders)
                if is_curriculum:
                    if len(cols) < 7:
                        continue
                    
                    course_code = cols[0].text.strip()
                    course_name = cols[1].text.strip()
                    
                    # The details are in the LAST column usually
                    details_text = cols[-1].text.strip()
                    
                    # Regex to find grade at the end (e.g. "BA", "CC")
                    # Pattern typically: [Term] Code Name ... Z Credit ECTS Grade Icon
                    import re
                    grade_match = re.search(r'\s([A-Z]{2})\s*$', details_text)
                    final_grade = grade_match.group(1) if grade_match else ""
                    
                    # If not found via regex, try simple split
                    if not final_grade and details_text:
                        parts = details_text.split()
                        if parts:
                            last_token = parts[-1]
                            if last_token in letter_grades:
                                final_grade = last_token
                    
                    # Create grade info directly
                    grade_info = {
                        "course_code": course_code,
                        "course_name": course_name,
                        "grade": final_grade,
                        "exam_grades": {},
                        "status": "Final" if final_grade else ""
                    }
                    
                    grades.append(grade_info)
                    if final_grade:
                        print(f"[*] Row {row_idx}: {course_code} - {course_name[:30]} = {final_grade}")
                    continue

                # Generic Table Parsing (Fallback)
                if len(cols) < 3:
                    continue
                
                col_texts = [col.text.strip() for col in cols]
                
                # Extract course code
                course_code = ""
                if code_idx is not None and code_idx < len(col_texts):
                    course_code = col_texts[code_idx]
                else:
                    for i, text in enumerate(col_texts[:4]):
                        if text and len(text) >= 5 and len(text) <= 10:
                            if any(c.isalpha() for c in text) and any(c.isdigit() for c in text):
                                course_code = text
                                code_idx = i
                                break
                
                # Extract course name
                course_name = ""
                if name_idx is not None and name_idx < len(col_texts):
                    course_name = col_texts[name_idx]
                elif code_idx is not None and code_idx + 1 < len(col_texts):
                    course_name = col_texts[code_idx + 1]
                
                # Extract final grade
                final_grade = ""
                if grade_idx is not None and grade_idx < len(col_texts):
                    final_grade = col_texts[grade_idx]
                
                if not final_grade:
                    # Search from right
                    for i in range(len(col_texts) - 1, 2, -1):
                        text = col_texts[i].strip()
                        if text.upper() in letter_grades:
                            final_grade = text.upper()
                            break
                        try:
                            num = float(text.replace(',', '.'))
                            if 0 <= num <= 100:
                                final_grade = text
                                break
                        except ValueError:
                            pass
                
                # Extract exam grades
                exam_grades = {}
                for i, text in enumerate(col_texts):
                    text_lower = text.lower()
                    if 'vize' in text_lower or ':' in text:
                        parts = text.split(':')
                        if len(parts) == 2:
                            try:
                                exam_grades[parts[0].strip()] = float(parts[1].strip().replace(',', '.'))
                            except:
                                pass
                
                if not course_code:
                    continue
                
                grade_info = {
                    "course_code": course_code,
                    "course_name": course_name,
                    "grade": final_grade,
                    "exam_grades": exam_grades,
                    "status": ""
                }
                
                grades.append(grade_info)
                print(f"[*] Row {row_idx}: {course_code} - {course_name[:30]} = {final_grade or 'No grade yet'}")
            
            print(f"[*] Found {len(grades)} course(s) total")
            
            # Filter to only courses with grades
            graded_courses = [g for g in grades if g.get("grade")]
            print(f"[*] Courses with grades: {len(graded_courses)}")
            
            return grades
            
        except Exception as e:
            print(f"[!] Error fetching grades: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def close(self):
        """Close the browser session."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None


def get_new_grades(cached_grades: list[dict], current_grades: list[dict]) -> list[dict]:
    """
    Compare cached and current grades to find new ones.
    Returns list of newly added or changed grades.
    
    Only considers courses that have a grade (not empty).
    """
    new_grades = []
    
    # Build lookup from cached grades (only courses with grades)
    cached_lookup = {}
    for g in cached_grades:
        grade = g.get('grade', '')
        if grade:  # Only add if has a grade
            key = g['course_code']
            cached_lookup[key] = grade
    
    # Check current grades for new or changed ones
    for grade in current_grades:
        current_grade = grade.get('grade', '')
        
        # Skip courses without grades
        if not current_grade:
            continue
        
        key = grade['course_code']
        cached_grade = cached_lookup.get(key)
        
        # New grade if:
        # 1. Course wasn't in cache with a grade (new grade entry)
        # 2. Grade value changed (updated grade)
        if cached_grade is None or cached_grade != current_grade:
            new_grades.append(grade)
            print(f"[+] New/changed grade: {key} = {current_grade} (was: {cached_grade})")
    
    return new_grades
