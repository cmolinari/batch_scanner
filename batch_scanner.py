import streamlit as st
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import base64
import cloudscraper
from bs4 import BeautifulSoup
import time
import json
import pandas as pd

# --- CONFIGURATION ---
SHEET_NAME = "My Collection"

# --- GOOGLE SHEETS SETUP ---
def get_sheet_connection():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"Sheet Connection Error: {e}")
        return None

def save_batch_to_sheet(car_list):
    sheet = get_sheet_connection()
    if not sheet:
        return False, "❌ Error: Could not connect to Google Sheet."
    try:
        rows_to_add = []
        for car in car_list:
            link_formula = f'=HYPERLINK("{car["link"]}", "View")'
            row = [car['code'], car.get('name', 'Unknown'), car.get('series', 'Unknown'), link_formula, "Scanned"] 
            rows_to_add.append(row)
        sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        return True, f"✅ Added {len(rows_to_add)} cars to the sheet!"
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- CORE LOGIC ---
def get_car_details(search_code):
    """Fetches details via the internal API"""
    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        api_url = f"https://collecthw.com/find?query={search_code}"
        response = scraper.get(api_url, timeout=10)
        
        if response.status_code == 200:
            try:
                raw_data = response.json()
                results = raw_data.get('data', [])
                if results and len(results) > 0:
                    item = results[0]
                    name = item.get('ModelName') or item.get('Model Name') or "Unknown Name"
                    series = item.get('Series') or "Unknown Series"
                    return name, series
            except:
                pass 
        return "No Data Found", "Verify on Site"
    except Exception as e:
        return f"Scraper Error", "N/A"

def generate_collecthw_url(code):
    try:
        encoded_str = base64.b64encode(code.strip().encode("utf-8")).decode("utf-8")
        return f"https://collecthw.com/hw/search/{encoded_str}"
    except:
        return None

def extract_all_codes(image):
    """Reverted to simpler OCR logic with O->0 correction"""
    # 1. Basic Preprocessing
    gray = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(gray)
    clean_img = enhancer.enhance(2.0)
    
    # 2. OCR Reading
    custom_config = r'--psm 6' 
    text = pytesseract.image_to_string(clean_img, config=custom_config)
    
    # 3. Normalization (Handle common misread: Letter 'O' -> Number '0')
    normalized_text = text.replace('O', '0')
    
    # 4. Regex Hunt
    pattern = r'[A-Z0-9]{5}-[A-Z0-9]{4}'
    matches = re.findall(pattern, normalized_text)
    
    return sorted(list(set(matches)))

# --- APP INTERFACE ---
st.set_page_config(page_title="HW Stack Scanner", layout="wide")
st.title("📚 HW Stack Scanner (Local Run)")

if 'found_cars' not in st.session_state:
    st.session_state['found_cars'] = []

uploaded_file = st.file_uploader("Upload Stack Photo", type=['jpg', 'jpeg', 'png'], key="stack_uploader")

if uploaded_file:
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(image, caption="Your Stack", use_container_width=True)
    
    with col2:
        if st.button("🔍 Scan & Fetch Details"):
            with st.spinner("Scanning..."):
                codes = extract_all_codes(image)
                if codes:
                    st.success(f"Found {len(codes)} Codes!")
                    results = []
                    progress_bar = st.progress(0)
                    for i, code in enumerate(codes):
                        name, series = get_car_details(code)
                        results.append({
                            "code": code, 
                            "link": generate_collecthw_url(code), 
                            "name": name, 
                            "series": series
                        })
                        progress_bar.progress((i + 1) / len(codes))
                        time.sleep(1.0)
                    st.session_state['found_cars'] = results
                else:
                    st.warning("No codes found.")

if st.session_state['found_cars']:
    st.divider()
    df = pd.DataFrame(st.session_state['found_cars'])
    st.table(df[['code', 'name', 'series']])
    
    if st.button("💾 Save All to Google Sheet"):
        success, msg = save_batch_to_sheet(st.session_state['found_cars'])
        if success:
            st.balloons()
            st.success(msg)
            st.session_state['found_cars'] = []
        else:
            st.error(msg)
