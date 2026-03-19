import cloudscraper
from bs4 import BeautifulSoup
import json
import base64

def test():
    code = "HRY66-N7C5"
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    # 1. Test API
    api_url = f"https://collecthw.com/find?query={code}"
    print(f"Testing API: {api_url}")
    r = scraper.get(api_url)
    print(f"API Status: {r.status_code}")
    try:
        print(f"API JSON Sample: {json.dumps(r.json(), indent=2)[:500]}")
    except:
        print(f"API Response is not JSON. Text sample: {r.text[:200]}")

    # 2. Test HTML Search
    encoded = base64.b64encode(code.encode()).decode()
    html_url = f"https://collecthw.com/hw/search/{encoded}"
    print(f"\nTesting HTML: {html_url}")
    r = scraper.get(html_url)
    print(f"HTML Status: {r.status_code}")
    
    soup = BeautifulSoup(r.text, 'html.parser')
    tables = soup.find_all('table')
    print(f"Found {len(tables)} tables")
    for i, t in enumerate(tables):
        rows = t.find_all('tr')
        print(f"Table {i} has {len(rows)} rows")
        if len(rows) > 1:
            print(f"First data row sample: {rows[1].get_text(strip=True)[:100]}")

if __name__ == "__main__":
    test()
