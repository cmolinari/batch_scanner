import streamlit as st
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import base64
import time
import json
import pandas as pd
import os

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
        # 1. Fetch existing codes (Column A)
        existing_codes = sheet.col_values(1)  # Codes are in the first column
        existing_codes_set = set(existing_codes)
        
        rows_to_add = []
        skipped_count = 0
        
        for car in car_list:
            # 2. Skip if code already exists
            if car['code'] in existing_codes_set:
                skipped_count += 1
                continue
                
            link_formula = f'=HYPERLINK("{car["link"]}", "View")'
            # Updated row structure: Toy Code, Year, Model Name, Collector #, Series, Series #, Link, Status
            row = [
                car['code'], 
                car.get('year', 'N/A'),
                car.get('name', 'Unknown'), 
                car.get('collector_num', 'N/A'),
                car.get('series', 'Unknown'), 
                car.get('series_num', 'N/A'),
                link_formula, 
                "Scanned"
            ] 
            rows_to_add.append(row)
        
        if not rows_to_add:
            return True, f"ℹ️ All {len(car_list)} cars were already in the sheet. No new rows added."

        # 3. Batch Append
        sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        
        msg = f"✅ Added {len(rows_to_add)} cars to the sheet!"
        if skipped_count > 0:
            msg += f" (Skipped {skipped_count} duplicates)"
        return True, msg
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- CORE LOGIC ---
def get_car_details(search_code):
    """Fetches details from local hw_master_db.csv"""
    # Load DB into session state if not already there
    if 'hw_db' not in st.session_state:
        try:
            db_path = 'hw_master_db.csv'
            if os.path.exists(db_path):
                st.session_state['hw_db'] = pd.read_csv(db_path)
            else:
                st.error(f"❌ Database file {db_path} not found!")
                return "DB Not Found", "N/A", "N/A", "N/A"
        except Exception as e:
            st.error(f"❌ Error loading database: {e}")
            return "Load Error", "N/A", "N/A", "N/A"

    df = st.session_state['hw_db']
    
    # Search for the code. Toy Code in CSV might be shorter or longer.
    search_code = search_code.strip()
    
    # Try exact match first
    match = df[df['Toy Code'] == search_code]
    
    # If no exact match, try if the CSV code starts with our search code, 
    # OR if our search code starts with the CSV code (e.g., CSV has 'HTC79' and we have 'HTC79-N7C6')
    if match.empty:
        match = df[df['Toy Code'].apply(lambda x: str(x).startswith(search_code) or search_code.startswith(str(x)))]
    
    if not match.empty:
        row = match.iloc[0]
        name = str(row.get('Model Name', 'Unknown Name'))
        series = str(row.get('Series', 'Unknown Series'))
        col_num = str(row.get('Collector #', 'N/A'))
        series_num = str(row.get('Series #', 'N/A'))
        year = str(row.get('Year', 'N/A'))
        return name, series, col_num, series_num, year
    
    return "No Data Found", "N/A", "N/A", "N/A", "N/A"

def generate_collecthw_url(code):
    try:
        encoded_str = base64.b64encode(code.strip().encode("utf-8")).decode("utf-8")
        return f"https://collecthw.com/hw/search/{encoded_str}"
    except:
        return None

def normalize_code(text):
    """Common OCR corrections for HW codes"""
    return text.replace('O', '0').replace('S', '5').replace('I', '1').replace('Q', '0')

def extract_all_codes(image):
    """Multi-pass OCR strategy for maximum detection rate"""
    image = ImageOps.exif_transpose(image)
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    
    # Focus areas: Full image and Top half (where lighting/perspective often varies)
    top_half = gray.crop((0, 0, width, height // 2))
    
    all_found = set()
    
    # Configs: (source_img, resize, contrast, psm, sharp, bright)
    configs = [
        (gray, 2, 2.0, 11, 1.0, 1.0),   # Standard Full
        (gray, 2, 1.2, 12, 1.0, 1.0),   # Low Contrast/Sparse
        (top_half, 3, 2.0, 11, 1.5, 1.0) # High-Res Top Focus
    ]
    
    pattern = r'[A-Z0-9]{5}-[A-Z0-9]{4,5}'
    
    for src, resize, contrast, psm, sharp, bright in configs:
        w, h = src.size
        img = src.resize((int(w * resize), int(h * resize)), Image.Resampling.LANCZOS)
        
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if sharp != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(sharp)
        if bright != 1.0:
            img = ImageEnhance.Brightness(img).enhance(bright)
            
        text = pytesseract.image_to_string(img, config=f'--psm {psm}')
        normalized_text = normalize_code(text)
        
        matches = re.findall(pattern, normalized_text)
        for m in matches:
            # Truncate the suffix to 4 characters as the 5th is a box code not used for search
            prefix, suffix = m.split('-')
            clean_code = f"{prefix}-{suffix[:4]}"
            all_found.add(clean_code)
            
    return sorted(list(all_found))

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
                        name, series, col_num, series_num, year = get_car_details(code)
                        results.append({
                            "code": code, 
                            "link": generate_collecthw_url(code), 
                            "name": name, 
                            "series": series,
                            "collector_num": col_num,
                            "series_num": series_num,
                            "year": year
                        })
                        progress_bar.progress((i + 1) / len(codes))
                        # No need for time.sleep(1.0) anymore as we are doing local lookups
                    st.session_state['found_cars'] = results
                else:
                    st.warning("No codes found.")

if st.session_state['found_cars']:
    st.divider()
    df = pd.DataFrame(st.session_state['found_cars'])
    # Reorder/rename columns for display
    display_df = df[['code', 'year', 'name', 'collector_num', 'series', 'series_num']]
    display_df.columns = ['Toy Code', 'Year', 'Model Name', 'Collector #', 'Series', 'Series #']
    st.table(display_df)
    
    if st.button("💾 Save All to Google Sheet"):
        success, msg = save_batch_to_sheet(st.session_state['found_cars'])
        if success:
            st.balloons()
            st.success(msg)
            st.session_state['found_cars'] = []
        else:
            st.error(msg)
