import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import json
import re

def main():
    db_file = 'hw_master_db.csv'
    start_year = 1968
    end_year = 2026
    
    # Target fields mapping (CSV Header : API Key)
    field_mapping = {
        "Toy Code": "Toy",
        "Model Name": "ModelName",
        "Collector #": "Col",
        "Series #": "SeriesNum",
        "Series": "Series",
        "Color": "Color",
        "Tampos": "Tampo",
        "Wheel Type": "WheelType",
        "Base Type": "BaseType",
        "Window Color": "WindowColor",
        "Interior Color": "InteriorColor"
    }

    # Requirement 5: Resume feature
    if os.path.exists(db_file):
        try:
            temp_df = pd.read_csv(db_file)
            if not temp_df.empty and 'Year' in temp_df.columns:
                last_year = temp_df['Year'].max()
                start_year = int(last_year) + 1
                print(f"Resuming from year {start_year} (found data up to {last_year})")
        except Exception as e:
            print(f"Error reading existing database, starting from scratch: {e}")

    if start_year > end_year:
        print(f"Database already complete up to {end_year}. Nothing to do.")
        return

    # Requirement 2: cloudscraper with standard Windows desktop configuration
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

    for year in range(start_year, end_year + 1):
        print(f"\n--- Scraping Year: {year} ---")
        
        try:
            # Requirement 6: Respect rate limits
            time.sleep(2)
            
            # Step 1: Request the page to get the API configuration
            page_url = f"https://collecthw.com/hw/year/{year}"
            r = scraper.get(page_url)
            
            if r.status_code != 200:
                print(f"Failed to load page for {year}, status: {r.status_code}")
                continue
                
            # Requirement 3: Use BeautifulSoup to extract data
            # Note: The site uses DataTables/AJAX. We use BS4 to find the API endpoint from the page source.
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Extract API URL from script tags
            api_url = None
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'apiUrl' in script.string:
                    match = re.search(r'const apiUrl = "(.*?)";', script.string)
                    if match:
                        api_url = match.group(1).replace(r'\/', '/')
                        break
            
            if not api_url:
                # Fallback to standard pattern if not found in script
                api_url = f"https://collecthw.com/find/years?query={year}"
            
            # Add length parameter to get all records for the year
            api_url += "&length=5000"
            
            print(f"Fetching data from API...")
            api_response = scraper.get(api_url)
            if api_response.status_code != 200:
                print(f"Failed to fetch API data for {year}, status: {api_response.status_code}")
                continue
                
            data_json = api_response.json()
            cars = data_json.get('data', [])
            print(f"Found {len(cars)} cars for year {year}")
            
            if not cars:
                print(f"No cars found for {year}, skipping.")
                continue
                
            year_data = []
            for car in cars:
                car_row = {"Year": year}
                
                # Requirement 7: Robust try/except and field extraction
                for csv_field, api_key in field_mapping.items():
                    try:
                        val = car.get(api_key, "N/A")
                        car_row[csv_field] = val if val and str(val).strip() != "" else "N/A"
                    except:
                        car_row[csv_field] = "N/A"
                
                year_data.append(car_row)
            
            # Requirement 4: Checkpointing - Append to CSV after each year
            df_year = pd.DataFrame(year_data)
            
            # Reorder columns to ensure Year is first
            cols = ["Year"] + list(field_mapping.keys())
            df_year = df_year[cols]
            
            if not os.path.exists(db_file):
                df_year.to_csv(db_file, index=False)
            else:
                df_year.to_csv(db_file, mode='a', header=False, index=False)
                
            # Requirement 8: Confirmation print
            print(f"Successfully appended {len(year_data)} records for {year} to {db_file}.")
            
        except Exception as e:
            print(f"Critical error scraping year {year}: {e}")
            continue

    print("\nScraping complete!")

if __name__ == "__main__":
    main()
