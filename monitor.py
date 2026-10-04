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

# ----------------------------
# Detect new AIP amendment
# ----------------------------

HISTORY_FILE = "aip_history.json"

try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
except FileNotFoundError:
    history = {}

previous_issue = history.get("Taiwan", {}).get("last_seen")
latest_issue = next_issue["amendment"] if next_issue else None

is_new = False

if latest_issue and previous_issue and latest_issue != previous_issue:
    is_new = True

if latest_issue:
    history["Taiwan"] = {
        "last_seen": latest_issue,
        "last_checked": datetime.now(timezone.utc).isoformat()
    }

with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

if is_new:
    print("🔴 NEW AIP UPDATE")
    print(f"Previous: {previous_issue}")
    print(f"New: {latest_issue}")
else:
    print("🟢 No new AIP update")


# ============================================================
# Taiwan SUP Monitor
# ============================================================

from urllib.parse import urljoin

# Current eAIP package
PACKAGE_URL = (
    "https://ais.caa.gov.tw/eaip/"
    "AIRAC%20AIP%20AMDT%2004-26_2026_10_01/"
)

# Possible SUP index locations
SUP_INDEX_URLS = [
    urljoin(PACKAGE_URL, "eSUP/"),
    urljoin(PACKAGE_URL, "eSUP/index.html"),
    urljoin(PACKAGE_URL, "eSUP/index-en-GB.html"),
]

sup_links = set()

for index_url in SUP_INDEX_URLS:

    try:
        r = requests.get(
            index_url,
            headers=headers,
            timeout=30
        )

        if r.status_code != 200:
            continue

        sup_soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        for link in sup_soup.find_all("a", href=True):

            href = link["href"]

            if "SUP-en-GB.html" in href:

                full_url = urljoin(
                    index_url,
                    href
                )

                sup_links.add(full_url)

    except Exception as e:

        print(
            "SUP index error:",
            index_url,
            e
        )


# ------------------------------------------------------------
# Parse each SUP
# ------------------------------------------------------------

sup_documents = []

for sup_url in sorted(sup_links):

    try:

        r = requests.get(
            sup_url,
            headers=headers,
            timeout=30
        )

        r.raise_for_status()

        doc_soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        doc_text = doc_soup.get_text(
            " ",
            strip=True
        )

        # SUP number
        number_match = re.search(
            r"AIP\s+SUP\s+(\d{1,2}/\d{2})",
            doc_text,
            re.IGNORECASE
        )

        # Publication date
        pub_match = re.search(
            r"Published\s+on\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )

        # Effective dates
        effective_match = re.search(
            r"Effective\s+from\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})"
            r"(?:\s+to\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4}))?",
            doc_text,
            re.IGNORECASE
        )

        # Title
        title = "—"

        headings = doc_soup.find_all(
            ["h1", "h2", "h3"]
        )

        for heading in headings:

            candidate = heading.get_text(
                " ",
                strip=True
            )

            if (
                candidate
                and "AIP SUP" not in candidate.upper()
                and len(candidate) > 5
            ):
                title = candidate
                break

        if number_match:

            sup_documents.append({
                "type": "SUP",
                "number": number_match.group(1),

                "title": title,

                "publication_date":
                    pub_match.group(1)
                    if pub_match
                    else None,

                "effective_from":
                    effective_match.group(1)
                    if effective_match
                    else None,

                "effective_until":
                    effective_match.group(2)
                    if (
                        effective_match
                        and effective_match.group(2)
                    )
                    else None,

                "url": sup_url
            })

    except Exception as e:

        print(
            "SUP document error:",
            sup_url,
            e
        )


# Sort newest first
def sup_sort(item):

    try:
        n, y = item["number"].split("/")
        return int(y), int(n)

    except:
        return 0, 0


sup_documents.sort(
    key=sup_sort,
    reverse=True
)


# Save
with open(
    "taiwan_sup.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        {
            "state": "Taiwan",
            "icao": "RC",

            "checked_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "documents":
                sup_documents
        },

        f,
        ensure_ascii=False,
        indent=2
    )


print(
    f"Found {len(sup_documents)} SUP documents."
)

for item in sup_documents:

    print(
        item["number"],
        "|",
        item["publication_date"],
        "|",
        item["effective_from"],
        "|",
        item["effective_until"],
        "|",
        item["title"]
    )
