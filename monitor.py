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
# Taiwan SUP + AIC Monitor
# ============================================================

from urllib.parse import urljoin

# ------------------------------------------------------------
# Automatically detect current eAIP package URL
# ------------------------------------------------------------

PACKAGE_URL = None

if current_issue and current_issue.get("effective_date"):

    current_effective_date = current_issue["effective_date"]

    for link in soup.find_all("a", href=True):

        label = link.get_text(
            " ",
            strip=True
        )

        # The CAA homepage puts the package link
        # on the Effective Date
        if label.lower() == current_effective_date.lower():

            package_index_url = urljoin(
                URL,
                link["href"]
            )

            PACKAGE_URL = urljoin(
                package_index_url,
                "./"
            )

            break


if not PACKAGE_URL:
    raise RuntimeError(
        "Could not automatically detect "
        "the current Taiwan eAIP package URL."
    )


print(
    "Current eAIP package:",
    PACKAGE_URL
)


SUP_MENU_URL = urljoin(
    PACKAGE_URL,
    "eSUP/menu.html"
)

AIC_MENU_URL = urljoin(
    PACKAGE_URL,
    "eAIC/menu.html"
)


def get_document_links(menu_url, doc_type):
    links = {}

    try:
        r = requests.get(
            menu_url,
            headers=headers,
            timeout=30
        )
        r.raise_for_status()

        menu_soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        for link in menu_soup.find_all("a", href=True):

            label = link.get_text(
                " ",
                strip=True
            )

            if not re.fullmatch(
                r"\d{1,2}/\d{2}",
                label
            ):
                continue

            href = link["href"]

            # English document only
            if doc_type == "SUP":
                if "SUP-en-GB.html" not in href:
                    continue

            elif doc_type == "AIC":
                if "en-GB.html" not in href:
                    continue

            full_url = urljoin(
                menu_url,
                href
            )

            # Avoid Chinese/English duplicate entries
            links[label] = full_url

    except Exception as e:
        print(
            f"{doc_type} menu error:",
            e
        )

    return links


def parse_document(
    number,
    url,
    doc_type
):

    try:
        r = requests.get(
            url,
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

        # -------------------------
        # Publication Date
        # -------------------------

        pub_match = re.search(
            r"Published\s+on\s+"
            r"(\d{1,2}\s+[A-Z]{3,4}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )

        publication_date = (
            pub_match.group(1).upper()
            if pub_match
            else None
        )

        # -------------------------
        # Effective From
        # -------------------------

        effective_match = re.search(
            r"Effective\s+from\s+"
            r"(\d{1,2}\s+[A-Z]{3,4}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )

        effective_from = (
            effective_match.group(1).upper()
            if effective_match
            else None
        )

        # -------------------------
        # Effective Until
        # -------------------------

        until_match = re.search(
            r"Effective\s+from\s+"
            r"\d{1,2}\s+[A-Z]{3,4}\s+\d{4}"
            r"\s+to\s+"
            r"(\d{1,2}\s+[A-Z]{3,4}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )

        effective_until = (
            until_match.group(1).upper()
            if until_match
            else None
        )

        # -------------------------
        # Title
        # -------------------------

        title = None

        headings = doc_soup.find_all(
            ["h1", "h2", "h3"]
        )

        for heading in headings:

            candidate = heading.get_text(
                " ",
                strip=True
            )

            upper = candidate.upper()

            if (
                candidate
                and "AIP SUP" not in upper
                and upper != "AIC"
                and len(candidate) > 5
            ):
                title = candidate
                break

        # AIC checklist sometimes has no heading
        if not title and doc_type == "AIC":

            if "CHECKLIST OF AERONAUTICAL INFORMATION CIRCULARS" in doc_text.upper():
                title = (
                    "CHECKLIST OF AERONAUTICAL "
                    "INFORMATION CIRCULARS"
                )

        if not title:
            title = "—"

        return {
            "type": doc_type,
            "number": number,
            "title": title,
            "publication_date": publication_date,
            "effective_from": effective_from,
            "effective_until": effective_until,
            "url": url
        }

    except Exception as e:

        print(
            f"{doc_type} document error:",
            number,
            url,
            e
        )

        return None


# ============================================================
# Get SUP
# ============================================================

sup_links = get_document_links(
    SUP_MENU_URL,
    "SUP"
)

sup_documents = []

for number, url in sup_links.items():

    document = parse_document(
        number,
        url,
        "SUP"
    )

    if document:
        sup_documents.append(document)


# ============================================================
# Get AIC
# ============================================================

aic_links = get_document_links(
    AIC_MENU_URL,
    "AIC"
)

aic_documents = []

for number, url in aic_links.items():

    document = parse_document(
        number,
        url,
        "AIC"
    )

    if document:
        aic_documents.append(document)


# ============================================================
# Sort newest number first
# ============================================================

def document_sort(item):

    try:
        number, year = item["number"].split("/")

        return (
            int(year),
            int(number)
        )

    except Exception:
        return (0, 0)


sup_documents.sort(
    key=document_sort,
    reverse=True
)

aic_documents.sort(
    key=document_sort,
    reverse=True
)


# ============================================================
# Save combined documents
# ============================================================

all_documents = (
    sup_documents +
    aic_documents
)

documents_data = {
    "state": "Taiwan",
    "icao": "RC",
    "source": URL,
    "checked_at":
        datetime.now(
            timezone.utc
        ).isoformat(),
    "documents": all_documents
}

with open(
    "taiwan_documents.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        documents_data,
        f,
        ensure_ascii=False,
        indent=2
    )


# Keep SUP-only file if needed
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
            "documents": sup_documents
        },
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    f"Found {len(sup_documents)} SUP documents."
)

print(
    f"Found {len(aic_documents)} AIC documents."
)

print(
    f"Saved {len(all_documents)} documents "
    "to taiwan_documents.json"
)

for item in all_documents:

    print(
        item["type"],
        item["number"],
        "|",
        item["publication_date"],
        "|",
        item["effective_from"],
        "|",
        item["title"]
    )
