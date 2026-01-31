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

            # Try multiple models in order of preference/availability
            models_to_try = [
                'gemini-3.0-pro',        # User requested specific model
                'gemini-3.0-pro-exp', 
                'gemini-3.0-flash',      # Experimental variant
                'gemini-2.0-flash',      # Latest flash model (fast & capable)
                'gemini-2.0-pro-exp',    # Next gen pro
                'gemini-1.5-pro',        # Stable pro model
                'gemini-1.5-flash',      # Stable flash model
                'gemini-pro-vision',     # Legacy vision model
            ]
            
            response = None
            used_model = None
            
            for model_id in models_to_try:
                try:
                    # print(f"[*] Trying Gemini model: {model_id}") # Optional debug
                    
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
                            # Rate limit handling
                            if "429" in str(e) and i < max_gemini_retries - 1:
                                wait_time = 5 * (i + 1)
                                time.sleep(wait_time)
                                img_byte_arr.seek(0)
                            else:
                                raise e # Re-raise to try next model
                    
                    if response:
                        break # Found a working model and got response
                        
                except Exception as e:
                    # If 404 (model not found) or other error, try next model
                    if "404" in str(e):
                        continue
                    # print(f"[!] Error with model {model_id}: {e}")
                    continue
            
            if not response:
                print("[!] All Gemini models failed or not found")
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
            # Navigate to the grades page ("Not Listesi")
            # User confirmed the URL is index.aspx?curOp=0
            grades_url = f"{config.OBS_BASE_URL}/oibs/std/index.aspx?curOp=0"
            print(f"[*] Navigating to grades page: {grades_url}")
            self.driver.get(grades_url)
            
            # Wait for page to load
            time.sleep(4)
            
            # Save page source for debugging
            try:
                with open("obs_grades_page.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                print("[*] Saved page source to obs_grades_page.html")
            except:
                pass
            
            # Take screenshot for debugging
            try:
                self.driver.save_screenshot("obs_grades_page.png")
                print("[*] Saved screenshot to obs_grades_page.png")
            except:
                pass
            
            grades = []
            
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
                # Fallback: find any table with multiple rows
                all_tables = self.driver.find_elements(By.TAG_NAME, "table")
                for table in all_tables:
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    if len(rows) >= 3:  # Header + at least 2 data rows
                        main_table = table
                        print(f"[*] Using fallback table with {len(rows)} rows")
                        break
            
            if not main_table:
                print("[!] No suitable grades table found!")
                return []
            
            # Parse the grades table
            rows = main_table.find_elements(By.TAG_NAME, "tr")
            print(f"[*] Processing table with {len(rows)} rows")
            
            # Analyze header to find column indices
            header_row = rows[0] if rows else None
            header_cells = header_row.find_elements(By.TAG_NAME, "th") if header_row else []
            if not header_cells:
                header_cells = header_row.find_elements(By.TAG_NAME, "td") if header_row else []
            
            header_texts = [cell.text.strip().lower() for cell in header_cells]
            print(f"[*] Header columns: {header_texts}")
            
            # Find column indices
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
            
            print(f"[*] Column indices - Code: {code_idx}, Name: {name_idx}, Grade: {grade_idx}")
            
            # Grade patterns to look for
            letter_grades = ["AA", "BA", "BB", "CB", "CC", "DC", "DD", "FF", "FD", "NA", "VZ", "MU"]
            
            # Process data rows
            for row_idx, row in enumerate(rows[1:], start=1):  # Skip header
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 3:
                    continue
                
                col_texts = [col.text.strip() for col in cols]
                
                # Extract course code - usually column 1 or 2 (after # column)
                course_code = ""
                if code_idx is not None and code_idx < len(col_texts):
                    course_code = col_texts[code_idx]
                else:
                    # Heuristic: course code looks like "AIT0101", "BLM207", etc.
                    for i, text in enumerate(col_texts[:4]):
                        if text and len(text) >= 5 and len(text) <= 10:
                            if any(c.isalpha() for c in text) and any(c.isdigit() for c in text):
                                course_code = text
                                code_idx = i
                                break
                
                # Extract course name - usually next column after code
                course_name = ""
                if name_idx is not None and name_idx < len(col_texts):
                    course_name = col_texts[name_idx]
                elif code_idx is not None and code_idx + 1 < len(col_texts):
                    course_name = col_texts[code_idx + 1]
                
                # Extract final grade from "Not" column
                # Based on screenshot, "Not" column is around index 9-10
                # It can contain numeric (89) or letter grade (AA)
                final_grade = ""
                
                # First, try the grade_idx if we found it
                if grade_idx is not None and grade_idx < len(col_texts):
                    potential_grade = col_texts[grade_idx]
                    if potential_grade:
                        final_grade = potential_grade
                
                # If not found, search all columns for grade-like values
                if not final_grade:
                    # Search from the right side of the table (where "Not" column typically is)
                    for i in range(len(col_texts) - 1, 2, -1):
                        text = col_texts[i].strip()
                        if not text:
                            continue
                        
                        # Check for letter grade
                        if text.upper() in letter_grades:
                            final_grade = text.upper()
                            break
                        
                        # Check for numeric grade (0-100)
                        try:
                            num = float(text.replace(',', '.'))
                            if 0 <= num <= 100:
                                final_grade = text
                                break
                        except ValueError:
                            pass
                
                # Also look for exam grades (Vize, Kısa Sınav, Final)
                exam_grades = {}
                for i, text in enumerate(col_texts):
                    text_lower = text.lower()
                    # Try to parse exam grades like "Vize: 85" or just numbers in specific columns
                    if 'vize' in text_lower or ':' in text:
                        parts = text.split(':')
                        if len(parts) == 2:
                            try:
                                exam_grades[parts[0].strip()] = float(parts[1].strip().replace(',', '.'))
                            except:
                                pass
                
                # Skip invalid rows
                if not course_code:
                    continue
                
                # Only add if we have valid data
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
