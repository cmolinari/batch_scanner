import streamlit as st
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import base64

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
        return None

def save_batch_to_sheet(car_list):
    sheet = get_sheet_connection()
    if not sheet:
        return False, "❌ Error: Could not connect to Google Sheet."
    try:
        # We prepare a list of rows to add all at once
        rows_to_add = []
        for car in car_list:
            # Row Structure: [Code, Link, Notes]
            # We use the HYPERLINK formula so you can click it in the sheet
            link_formula = f'=HYPERLINK("{car["link"]}", "ID This Car")'
            row = [car['code'], link_formula, "Unverified"] 
            rows_to_add.append(row)
        
        sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        return True, f"✅ Added {len(rows_to_add)} cars to the sheet!"
    except Exception as e:
        return False, f"❌ Cloud Error: {e}"

# --- CORE LOGIC ---
def generate_collecthw_url(code):
    """JBC19 -> SkJDMTk= -> URL"""
    try:
        clean_code = code.split("-")[0].strip()
        encoded_bytes = base64.b64encode(clean_code.encode("utf-8"))
        encoded_str = encoded_bytes.decode("utf-8")
        return f"https://collecthw.com/hw/search/{encoded_str}"
    except:
        return "Error generating link"

def extract_all_codes(image):
    """Finds ALL patterns like JBC19-N7C5 in one image"""
    # 1. Image Prep (High Contrast is key for stacks)
    gray = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(gray)
    clean_img = enhancer.enhance(2.0)
    
    # 2. OCR Reading
    # psm 6 = Assume a single uniform block of text (good for lists/stacks)
    custom_config = r'--psm 6' 
    text = pytesseract.image_to_string(clean_img, config=custom_config)
    
    # 3. Regex Hunt
    # Finds every occurrence of the pattern
    pattern = r'[A-Z0-9]{5}-[A-Z0-9]{4}'
    matches = re.findall(pattern, text)
    
    # Remove duplicates (in case it read the same line twice)
    unique_matches = sorted(list(set(matches)))
    
    return unique_matches

# --- APP INTERFACE ---
st.title("📚 HW Stack Scanner")
st.write("Take a photo of the **top edges** of a stack of cards.")

if 'found_cars' not in st.session_state:
    st.session_state['found_cars'] = []

uploaded_file = st.file_uploader("Upload Stack Photo", key="stack_uploader")

if uploaded_file:
    image = Image.open(uploaded_file)
    # Fix rotation if needed
    image = ImageOps.exif_transpose(image)
    
    st.image(image, caption="Your Stack", width=300)
    
    if st.button("🔍 Scan Stack"):
        with st.spinner("Reading all codes..."):
            codes = extract_all_codes(image)
            
            if codes:
                st.success(f"Found {len(codes)} Codes!")
                
                # Convert to a list of dictionaries
                results = []
                for code in codes:
                    link = generate_collecthw_url(code)
                    results.append({"code": code, "link": link})
                
                st.session_state['found_cars'] = results
            else:
                st.warning("No codes found. Ensure text is horizontal and lit well.")

# --- PREVIEW & SAVE ---
if st.session_state['found_cars']:
    st.divider()
    st.subheader("Preview Batch")
    
    # Display the list nicely
    for i, car in enumerate(st.session_state['found_cars']):
        cols = st.columns([1, 3])
        cols[0].write(f"**{car['code']}**")
        cols[1].markdown(f"[Test Link]({car['link']})")
    
    st.divider()
    if st.button("💾 Save All to Google Sheet"):
        success, msg = save_batch_to_sheet(st.session_state['found_cars'])
        if success:
            st.balloons()
            st.success(msg)
            # Clear the list
            st.session_state['found_cars'] = []
        else:
            st.error(msg)
