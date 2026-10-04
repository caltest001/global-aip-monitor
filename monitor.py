import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin


# ============================================================
# Basic Settings
# ============================================================

URL = "https://ais.caa.gov.tw/eaip/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ============================================================
# Helper Functions
# ============================================================

def extract_section(text, start, end):
    try:
        return (
            text
            .split(start, 1)[1]
            .split(end, 1)[0]
            .strip()
        )
    except IndexError:
        return ""


def parse_issue(section):

    date_pattern = r"(\d{2} [A-Z][a-z]{2} \d{4})"

    issue_pattern = (
        r"(AIRAC AIP AMDT|AIP AMDT)"
        r"\s+(\d{2}/\d{2})"
    )

    dates = re.findall(
        date_pattern,
        section
    )

    issue = re.search(
        issue_pattern,
        section
    )

    if not issue:
        return None

    return {
        "amendment":
            f"{issue.group(1)} {issue.group(2)}",

        "effective_date":
            dates[0]
            if len(dates) >= 1
            else None,

        "publication_date":
            dates[1]
            if len(dates) >= 2
            else None
    }


# ============================================================
# Load Taiwan CAA eAIP Homepage
# ============================================================

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

text = soup.get_text(
    " ",
    strip=True
)


# ============================================================
# AIP AMDT Monitor
# ============================================================

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

current_issue = parse_issue(
    current_section
)

next_issue = parse_issue(
    next_section
)


aip_data = {
    "state": "Taiwan",
    "icao": "RC",
    "source": URL,
    "checked_at":
        datetime.now(
            timezone.utc
        ).isoformat(),
    "status": "OK",
    "current": current_issue,
    "next": next_issue
}


with open(
    "taiwan_aip.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        aip_data,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    json.dumps(
        aip_data,
        ensure_ascii=False,
        indent=2
    )
)


# ============================================================
# AIP AMDT History
# ============================================================

HISTORY_FILE = "aip_history.json"


try:

    with open(
        HISTORY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        history = json.load(f)

except (
    FileNotFoundError,
    json.JSONDecodeError
):

    history = {}


previous_issue = (
    history
    .get("Taiwan", {})
    .get("last_seen")
)


latest_issue = (
    next_issue["amendment"]
    if next_issue
    else None
)


is_new = False


if (
    latest_issue
    and previous_issue
    and latest_issue != previous_issue
):

    is_new = True


if latest_issue:

    history["Taiwan"] = {
        "last_seen":
            latest_issue,

        "last_checked":
            datetime.now(
                timezone.utc
            ).isoformat()
    }


with open(
    HISTORY_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        history,
        f,
        ensure_ascii=False,
        indent=2
    )


if is_new:

    print("🔴 NEW AIP UPDATE")

    print(
        f"Previous: {previous_issue}"
    )

    print(
        f"New: {latest_issue}"
    )

else:

    print(
        "🟢 No new AIP update"
    )


# ============================================================
# SUP / AIC Source Discovery
#
# IMPORTANT:
#
# SUP and AIC are independent publications.
#
# AIRAC package folders below are only technical locations
# used by the Taiwan CAA website.
#
# SUP and AIC each independently select the menu with the
# newest "Published as of" date.
# ============================================================

PACKAGE_CANDIDATES = [

    (
        "https://ais.caa.gov.tw/eaip/"
        "AIRAC%20AIP%20AMDT%2004-26_2026_10_01/"
    ),

    (
        "https://ais.caa.gov.tw/eaip/"
        "AIRAC%20AIP%20AMDT%2003-26_2026_08_06/"
    )

]


# ============================================================
# Read "Published as of" from menu
# ============================================================

def get_menu_date(menu_url):

    try:

        r = requests.get(
            menu_url,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        menu_soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        menu_text = menu_soup.get_text(
            " ",
            strip=True
        )


        match = re.search(
            r"Published\s+as\s+of\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})",
            menu_text,
            re.IGNORECASE
        )


        if not match:
            return None


        published_date = datetime.strptime(
            match.group(1).upper(),
            "%d %b %Y"
        )


        return published_date


    except Exception as e:

        print(
            "Menu check error:",
            menu_url,
            e
        )

        return None


# ============================================================
# Select latest SUP or AIC menu independently
# ============================================================

def find_latest_menu(
    packages,
    menu_path,
    doc_type
):

    candidates = []


    for package_url in packages:

        menu_url = urljoin(
            package_url,
            menu_path
        )


        published_date = get_menu_date(
            menu_url
        )


        if published_date:

            candidates.append(
                (
                    published_date,
                    menu_url
                )
            )


            print(
                f"{doc_type} candidate:",
                published_date.strftime(
                    "%d %b %Y"
                ).upper(),
                menu_url
            )


    if not candidates:

        return None


    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )


    latest_date, latest_url = (
        candidates[0]
    )


    print(
        f"Selected {doc_type} menu:",
        latest_date.strftime(
            "%d %b %Y"
        ).upper(),
        latest_url
    )


    return latest_url


# ============================================================
# SUP and AIC source selection
# ============================================================

SUP_MENU_URL = find_latest_menu(
    PACKAGE_CANDIDATES,
    "eSUP/menu.html",
    "SUP"
)


AIC_MENU_URL = find_latest_menu(
    PACKAGE_CANDIDATES,
    "eAIC/menu.html",
    "AIC"
)


if not SUP_MENU_URL:

    raise RuntimeError(
        "Could not find a valid SUP menu. "
        "Existing data will not be overwritten."
    )


if not AIC_MENU_URL:

    raise RuntimeError(
        "Could not find a valid AIC menu. "
        "Existing data will not be overwritten."
    )


print(
    "SUP source:",
    SUP_MENU_URL
)

print(
    "AIC source:",
    AIC_MENU_URL
)


# ============================================================
# Get SUP / AIC Document Links
# ============================================================

def get_document_links(
    menu_url,
    doc_type
):

    documents = {}


    try:

        r = requests.get(
            menu_url,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()


        menu_soup = BeautifulSoup(
            r.text,
            "html.parser"
        )


        for link in menu_soup.find_all(
            "a",
            href=True
        ):

            label = link.get_text(
                " ",
                strip=True
            )

            href = link["href"]


            number_match = re.search(
                r"\b(\d{1,2}/\d{2})\b",
                label
            )


            if not number_match:
                continue


            number = (
                number_match
                .group(1)
                .zfill(5)
            )


            # --------------------------------------------
            # SUP English document
            # --------------------------------------------

            if doc_type == "SUP":

                if (
                    "SUP-en-GB.html"
                    not in href
                ):
                    continue


            # --------------------------------------------
            # AIC English document
            # --------------------------------------------

            elif doc_type == "AIC":

                if (
                    "en-GB.html"
                    not in href
                ):
                    continue


            full_url = urljoin(
                menu_url,
                href
            )


            # Deduplicate by document number
            documents[number] = (
                full_url
            )


        return documents


    except Exception as e:

        print(
            f"{doc_type} menu error:",
            e
        )

        return None


# ============================================================
# Parse Individual SUP / AIC Document
# ============================================================

def parse_document(
    number,
    url,
    doc_type
):

    try:

        r = requests.get(
            url,
            headers=HEADERS,
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


        # ====================================================
        # Publication Date
        # ====================================================

        pub_match = re.search(
            r"Published\s+on\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )


        # ====================================================
        # Effective From / Until
        # ====================================================

        effective_match = re.search(
            r"Effective\s+from\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})"
            r"(?:\s+to\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4}))?",
            doc_text,
            re.IGNORECASE
        )


        # ====================================================
        # Title
        # ====================================================

        title = "—"


        headings = doc_soup.find_all(
            ["h1", "h2", "h3"]
        )


        for heading in headings:

            candidate = heading.get_text(
                " ",
                strip=True
            )


            if not candidate:
                continue


            candidate_upper = (
                candidate.upper()
            )


            if (
                "AIP SUP"
                in candidate_upper
            ):
                continue


            if (
                candidate_upper
                == "AIC"
            ):
                continue


            if len(candidate) <= 5:
                continue


            title = candidate

            break


        # ====================================================
        # AIC Checklist Fallback
        # ====================================================

        if (
            doc_type == "AIC"
            and title == "—"
            and "CHECKLIST"
            in doc_text.upper()
        ):

            title = (
                "CHECKLIST OF "
                "AERONAUTICAL "
                "INFORMATION CIRCULARS"
            )


        return {

            "type":
                doc_type,

            "number":
                number,

            "title":
                title,

            "publication_date":
                (
                    pub_match.group(1)
                    if pub_match
                    else None
                ),

            "effective_from":
                (
                    effective_match.group(1)
                    if effective_match
                    else None
                ),

            "effective_until":
                (
                    effective_match.group(2)
                    if (
                        effective_match
                        and
                        effective_match.group(2)
                    )
                    else None
                ),

            "url":
                url
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
# Get SUP Links
# ============================================================

sup_links = get_document_links(
    SUP_MENU_URL,
    "SUP"
)


if sup_links is None:

    raise RuntimeError(
        "Failed to load SUP menu. "
        "Existing data will not be overwritten."
    )


# ============================================================
# Get AIC Links
# ============================================================

aic_links = get_document_links(
    AIC_MENU_URL,
    "AIC"
)


if aic_links is None:

    raise RuntimeError(
        "Failed to load AIC menu. "
        "Existing data will not be overwritten."
    )


# ============================================================
# Collect SUP Documents
# ============================================================

sup_documents = []


for number, document_url in (
    sup_links.items()
):

    document = parse_document(
        number,
        document_url,
        "SUP"
    )

    if document:

        sup_documents.append(
            document
        )


# ============================================================
# Collect AIC Documents
# ============================================================

aic_documents = []


for number, document_url in (
    aic_links.items()
):

    document = parse_document(
        number,
        document_url,
        "AIC"
    )

    if document:

        aic_documents.append(
            document
        )


# ============================================================
# Sort Documents
# ============================================================

def document_sort(item):

    try:

        number, year = (
            item["number"]
            .split("/")
        )

        return (
            int(year),
            int(number)
        )

    except Exception:

        return (
            0,
            0
        )


sup_documents.sort(
    key=document_sort,
    reverse=True
)


aic_documents.sort(
    key=document_sort,
    reverse=True
)


# ============================================================
# Result
# ============================================================

print(
    f"Found {len(sup_documents)} "
    "SUP documents."
)

print(
    f"Found {len(aic_documents)} "
    "AIC documents."
)


# ============================================================
# Safety Check
#
# Never overwrite valid existing files when scraping fails.
# ============================================================

total_documents = (
    len(sup_documents)
    +
    len(aic_documents)
)


if total_documents == 0:

    raise RuntimeError(
        "SUP/AIC scrape returned 0 documents. "
        "Existing JSON files will not be overwritten."
    )


# ============================================================
# Save Combined SUP + AIC File
# ============================================================

all_documents = (
    sup_documents
    +
    aic_documents
)


documents_data = {

    "state":
        "Taiwan",

    "icao":
        "RC",

    "source": {
        "sup":
            SUP_MENU_URL,

        "aic":
            AIC_MENU_URL
    },

    "checked_at":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "documents":
        all_documents
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


# ============================================================
# Keep taiwan_sup.json for Compatibility
# ============================================================

sup_data = {

    "state":
        "Taiwan",

    "icao":
        "RC",

    "source":
        SUP_MENU_URL,

    "checked_at":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "documents":
        sup_documents
}


with open(
    "taiwan_sup.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        sup_data,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    f"Saved {total_documents} "
    "documents to "
    "taiwan_documents.json"
)


# ============================================================
# Print SUP Summary
# ============================================================

for item in sup_documents:

    print(
        "SUP",
        item["number"],
        "|",
        item["publication_date"],
        "|",
        item["effective_from"],
        "|",
        item["title"]
    )


# ============================================================
# Print AIC Summary
# ============================================================

for item in aic_documents:

    print(
        "AIC",
        item["number"],
        "|",
        item["publication_date"],
        "|",
        item["effective_from"],
        "|",
        item["title"]
    )
