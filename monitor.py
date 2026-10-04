import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone

URL = "https://ais.caa.gov.tw/eaip/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=headers, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")
text = soup.get_text(" ", strip=True)


def extract_section(text, start, end):
    try:
        return text.split(start, 1)[1].split(end, 1)[0].strip()
    except IndexError:
        return ""


def parse_issue(section):
    date_pattern = r"(\d{2} [A-Z][a-z]{2} \d{4})"
    issue_pattern = r"(AIRAC AIP AMDT|AIP AMDT)\s+(\d{2}/\d{2})"

    dates = re.findall(date_pattern, section)
    issue = re.search(issue_pattern, section)

    if not issue:
        return None

    return {
        "amendment": f"{issue.group(1)} {issue.group(2)}",
        "effective_date": dates[0] if len(dates) >= 1 else None,
        "publication_date": dates[1] if len(dates) >= 2 else None
    }


current_section = extract_section(
    text,
    "Currently Effective Issue",
    "Next Issues"
)

next_section = extract_section(
    text,
    "Next Issues",
    "Expired Issues"
)

current_issue = parse_issue(current_section)
next_issue = parse_issue(next_section)

data = {
    "state": "Taiwan",
    "icao": "RC",
    "source": URL,
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "status": "OK",
    "current": current_issue,
    "next": next_issue
}

with open("taiwan_aip.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(json.dumps(data, ensure_ascii=False, indent=2))
