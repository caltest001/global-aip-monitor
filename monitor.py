import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timezone

URL = "https://ais.caa.gov.tw/eaip/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=headers, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

# 先取得首頁所有文字
page_text = soup.get_text(" ", strip=True)

data = {
    "state": "Taiwan",
    "icao": "RC",
    "source": URL,
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "page_title": soup.title.string.strip() if soup.title else "",
    "status": "OK",
    "raw_text": page_text[:3000]
}

with open("taiwan_aip.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Taiwan AIP check completed.")
print(data)
