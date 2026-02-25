import json

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def test_query(q):
    url = "https://data.gov.ua/api/3/action/package_search"
    params = {"q": q, "rows": 3}
    headers = {"User-Agent": "AtlasTrinity-GoldenFund/1.0", "Accept": "application/json"}
    try:
        print(f"Testing CKAN search: '{q}'")
        response = requests.get(url, params=params, headers=headers, timeout=10, verify=False)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            count = response.json().get("result", {}).get("count", 0)
            print(f"Total results: {count}")
            results = response.json().get("result", {}).get("results", [])
            for r in results:
                print(f" - {r.get('title')}")
        else:
            print(f"Error: {response.text[:200]}")
    except Exception as e:
        print(f"Exception: {e}")


test_query("адреса")
test_query("забудовник")
