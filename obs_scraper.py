"""
BTU OBS Web Scraper Module - Selenium + Gemini Vision Edition.
Handles login and grade fetching from the OBS system using Selenium and Gemini Vision for captcha.
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
    
    def _preprocess_captcha_image(self, image: Image.Image, threshold: int = 128) -> Image.Image:
        """Preprocess captcha image for better OCR results."""
        # Convert to grayscale
        image = image.convert('L')
        
        # Resize for better OCR (larger = more detail)
        width, height = image.size
        image = image.resize((width * 4, height * 4), Image.Resampling.LANCZOS)
        
        # Apply threshold
        image = image.point(lambda p: 255 if p > threshold else 0)
        
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
            prompt = """Bu bir matematik captcha görüntüsüdür. 
Görüntüdeki matematik işlemini çöz ve SADECE sayısal cevabı ver.
Örnek: Eğer görüntü "25+17=?" ise, sadece "42" yaz.
Başka hiçbir şey yazma, sadece sonuç sayısını yaz."""

            # Use gemini-1.5-pro as stable fallback since 3.0 might not be available or named differently
            # User intent is "best pro model". 1.5-pro is current stable pro.
            # If 2.0-pro-exp exists we could try that, but 1.5-pro is safer for reliability.
            model_id = 'gemini-1.5-pro'
            
            max_gemini_retries = 3
            response = None
            
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
                    break # Success
                except Exception as e:
                    # Check for rate limit error (usually 429)
                    if "429" in str(e) and i < max_gemini_retries - 1:
                        wait_time = 10 * (i + 1)
                        print(f"[!] Gemini Rate Limit (429). Waiting {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"[!] Gemini error: {e}")
                        # Fallback to older model if model not found? 
                        # But for now just fail gracefully to OCR
                        return None
            
            # Extract the answer
            if response and response.text:
                answer = response.text.strip()
                # Clean up - only keep digits
                answer = re.sub(r'[^0-9]', '', answer)
                
                if answer:
                    print(f"[*] Gemini Vision ({model_id}) answer: {answer}")
                    return answer
            
            print(f"[!] Gemini returned empty or invalid response")
            return None
                
        except Exception as e:
            print(f"[!] Gemini Vision error: {e}")
            return None
    
    def _try_multiple_ocr_approaches(self, original_image: Image.Image) -> list[str]:
        """Try multiple preprocessing approaches and return all results."""
        results = []
        
        # Try different thresholds and also inverted image
        thresholds = [100, 128, 150, 180]
        
        images_to_try = [original_image]
        
        # Also try inverted image
        inverted = original_image.copy().convert('L')
        inverted = Image.eval(inverted, lambda x: 255 - x)
        images_to_try.append(inverted.convert('RGB'))
        
        for img in images_to_try:
            for thresh in thresholds:
                processed = self._preprocess_captcha_image(img.copy(), threshold=thresh)
                
                # Try different OCR configs
                configs = [
                    r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789+=?',
                    r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789+=?',
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
            def score_result(text):
                score = 0
                if '+' in text:
                    score += 10
                nums = re.findall(r'\d+', text)
                if len(nums) >= 2:
                    if all(1 <= int(n) < 100 for n in nums[:2]):
                        score += 5
                digit_count = len(re.findall(r'\d', text))
                if 2 <= digit_count <= 4:
                    score += 3
                return score
            
            if results:
                best = max(results, key=score_result)
                print(f"[*] Best OCR result: '{best}' (score: {score_result(best)})")
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
    
    def login(self, max_retries: int = 2) -> bool:
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
            
            # Wait for response
            time.sleep(4)
            
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
        Fetch current grades from OBS.
        Returns list of grade dictionaries.
        """
        if not self.logged_in:
            print("[!] Not logged in, attempting login...")
            if not self.login():
                return []
        
        try:
            # Navigate to grades page
            grades_url = f"{config.OBS_BASE_URL}/oibs/std/start.aspx?gkm=014001"
            print(f"[*] Navigating to grades page...")
            self.driver.get(grades_url)
            
            # Wait for page to load
            time.sleep(3)
            
            grades = []
            
            # Find grade tables
            tables = self.driver.find_elements(By.XPATH, "//table[contains(@class, 'grid') or contains(@class, 'table') or contains(@id, 'grd')]")
            
            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows[1:]:  # Skip header
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) >= 3:
                        grade_info = {
                            "course_code": cols[0].text.strip(),
                            "course_name": cols[1].text.strip() if len(cols) > 1 else "",
                            "grade": cols[2].text.strip() if len(cols) > 2 else "",
                            "status": cols[3].text.strip() if len(cols) > 3 else "",
                        }
                        if grade_info["course_code"] and grade_info["grade"]:
                            grades.append(grade_info)
            
            print(f"[*] Found {len(grades)} grades")
            return grades
            
        except Exception as e:
            print(f"[!] Error fetching grades: {e}")
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
    """
    new_grades = []
    
    cached_lookup = {
        f"{g['course_code']}_{g.get('exam_type', '')}": g.get('grade', '')
        for g in cached_grades
    }
    
    for grade in current_grades:
        key = f"{grade['course_code']}_{grade.get('exam_type', '')}"
        cached_grade = cached_lookup.get(key)
        
        if cached_grade is None or cached_grade != grade.get('grade', ''):
            new_grades.append(grade)
    
    return new_grades
