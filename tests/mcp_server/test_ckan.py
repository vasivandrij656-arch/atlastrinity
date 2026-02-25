import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://data.gov.ua/api/3/action/package_search"
params = {"q": "адреса", "rows": 1}
headers = {"User-Agent": "AtlasTrinity-GoldenFund/1.0", "Accept": "application/json"}

try:
    print(f"Testing CKAN search at {url}")
    response = requests.get(url, params=params, headers=headers, timeout=15, verify=False)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("Response Success!")
        print(f"Result count: {len(response.json().get('result', {}).get('results', []))}")
    else:
        print(f"Error Body: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
