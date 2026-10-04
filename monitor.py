import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urljoin


# ============================================================
# Basic Settings
# ============================================================

BASE_URL = "https://ais.caa.gov.tw/eaip/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
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

    date_pattern = (
        r"(\d{2} [A-Z][a-z]{2} \d{4})"
    )

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
    BASE_URL,
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
# AIP AMDT
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


if not current_issue:

    raise RuntimeError(
        "Could not parse current Taiwan AIP issue."
    )


# ============================================================
# Save Taiwan AIP Status
# ============================================================

aip_data = {
    "state": "Taiwan",
    "icao": "RC",
    "source": BASE_URL,

    "checked_at":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "status": "OK",

    "current":
        current_issue,

    "next":
        next_issue
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
# AIP History
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
    else current_issue["amendment"]
)


is_new = False


if (
    latest_issue
    and
    previous_issue
    and
    latest_issue != previous_issue
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

    print(
        "🔴 NEW AIP UPDATE"
    )

    print(
        "Previous:",
        previous_issue
    )

    print(
        "New:",
        latest_issue
    )

else:

    print(
        "🟢 No new AIP update"
    )


# ============================================================
# Build Package URL from AIP Issue
#
# Example:
#
# AIRAC AIP AMDT 04/26
# Effective: 01 Oct 2026
#
# becomes:
#
# AIRAC AIP AMDT 04-26_2026_10_01/
#
# IMPORTANT:
#
# These package folders are only technical storage locations.
#
# SUP and AIC remain independent publications.
# ============================================================

def build_package_url(issue):

    if not issue:
        return None


    amendment = issue.get(
        "amendment"
    )

    effective_date = issue.get(
        "effective_date"
    )


    if (
        not amendment
        or
        not effective_date
    ):

        return None


    number_match = re.search(
        r"(\d{2})/(\d{2})",
        amendment
    )


    if not number_match:
        return None


    issue_number = (
        number_match.group(1)
    )

    issue_year = (
        number_match.group(2)
    )


    try:

        effective = datetime.strptime(
            effective_date,
            "%d %b %Y"
        )

    except ValueError:

        return None


    # Determine whether this is AIRAC or non-AIRAC
    if amendment.startswith(
        "AIRAC AIP AMDT"
    ):

        prefix = (
            "AIRAC AIP AMDT"
        )

    else:

        prefix = (
            "AIP AMDT"
        )


    folder_name = (
        f"{prefix} "
        f"{issue_number}-{issue_year}"
        f"_{effective:%Y_%m_%d}"
    )


    encoded_folder = quote(
        folder_name,
        safe="-_"
    )


    return (
        BASE_URL
        + encoded_folder
        + "/"
    )


# ============================================================
# Package Candidates
# ============================================================

PACKAGE_CANDIDATES = []


# ------------------------------------------------------------
# Current AIP package
# ------------------------------------------------------------

current_package = (
    build_package_url(
        current_issue
    )
)


if current_package:

    PACKAGE_CANDIDATES.append(
        current_package
    )


# ------------------------------------------------------------
# Next AIP package
# ------------------------------------------------------------

next_package = (
    build_package_url(
        next_issue
    )
)


if (
    next_package
    and
    next_package
    not in PACKAGE_CANDIDATES
):

    PACKAGE_CANDIDATES.append(
        next_package
    )


# ------------------------------------------------------------
# Known recent fallback packages
#
# These are NOT used to determine SUP/AIC publication dates.
#
# They are only additional technical locations to check.
# ------------------------------------------------------------

FALLBACK_PACKAGES = [
    (
        "https://ais.caa.gov.tw/eaip/"
        "AIRAC%20AIP%20AMDT%2003-26_2026_08_06/"
    )
]


for package_url in FALLBACK_PACKAGES:

    if (
        package_url
        not in PACKAGE_CANDIDATES
    ):

        PACKAGE_CANDIDATES.append(
            package_url
        )


print(
    f"Generated "
    f"{len(PACKAGE_CANDIDATES)} "
    f"package candidates."
)


for package_url in PACKAGE_CANDIDATES:

    print(
        "Package candidate:",
        package_url
    )


# ============================================================
# Read Menu "Published as of"
# ============================================================

def get_menu_date(menu_url):

    try:

        r = requests.get(
            menu_url,
            headers=HEADERS,
            timeout=30
        )

        if r.status_code == 404:

            print(
                "Menu not found:",
                menu_url
            )

            return None


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

            print(
                "No Published as of date:",
                menu_url
            )

            return None


        published_date = (
            datetime.strptime(
                match.group(1).upper(),
                "%d %b %Y"
            )
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
# Find Latest SUP / AIC Menu
#
# IMPORTANT:
#
# SUP and AIC are compared independently.
#
# We DO NOT select based on AIRAC issue number.
#
# We select based only on each menu's own:
#
# Published as of DD MMM YYYY
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


        published_date = (
            get_menu_date(
                menu_url
            )
        )


        if not published_date:
            continue


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
        key=lambda x: x[0],
        reverse=True
    )


    latest_date = (
        candidates[0][0]
    )

    latest_url = (
        candidates[0][1]
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
# Select SUP and AIC Sources Independently
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
        "Existing SUP/AIC data will not be overwritten."
    )


if not AIC_MENU_URL:

    raise RuntimeError(
        "Could not find a valid AIC menu. "
        "Existing SUP/AIC data will not be overwritten."
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

            href = link.get(
                "href",
                ""
            )


            if not href:
                continue


            number_match = re.search(
                r"\b(\d{1,2}/\d{2})\b",
                label
            )


            if not number_match:
                continue


            number = (
                number_match.group(1)
            )


            # =================================================
            # SUP English page
            # =================================================

            if doc_type == "SUP":

                if (
                    "sup-en-gb.html"
                    not in href.lower()
                ):

                    continue


            # =================================================
            # AIC English page
            # =================================================

            elif doc_type == "AIC":

                if (
                    "en-gb.html"
                    not in href.lower()
                ):

                    continue


            else:

                continue


            full_url = urljoin(
                menu_url,
                href
            )


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
# Parse Individual SUP / AIC
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
            [
                "h1",
                "h2",
                "h3"
            ]
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
            and
            title == "—"
            and
            "CHECKLIST"
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
# Load SUP Links
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
# Load AIC Links
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
# Parse SUP Documents
# ============================================================

sup_documents = []


for (
    number,
    document_url
) in sup_links.items():

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
# Parse AIC Documents
# ============================================================

aic_documents = []


for (
    number,
    document_url
) in aic_links.items():

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
# Results
# ============================================================

print(
    f"Found "
    f"{len(sup_documents)} "
    f"SUP documents."
)

print(
    f"Found "
    f"{len(aic_documents)} "
    f"AIC documents."
)


# ============================================================
# Safety Check
#
# Never overwrite valid data with an empty scrape.
# ============================================================

if not sup_documents:

    raise RuntimeError(
        "SUP scrape returned 0 documents. "
        "Existing JSON files will not be overwritten."
    )


if not aic_documents:

    raise RuntimeError(
        "AIC scrape returned 0 documents. "
        "Existing JSON files will not be overwritten."
    )


# ============================================================
# Combined SUP + AIC JSON
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
# SUP JSON
#
# Keep this file for frontend compatibility.
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


# ============================================================
# Final Summary
# ============================================================

print(
    f"Saved "
    f"{len(all_documents)} "
    f"documents to "
    f"taiwan_documents.json"
)


print(
    "----------------------------------------"
)

print(
    "SUP SUMMARY"
)

print(
    "----------------------------------------"
)


for item in sup_documents:

    print(
        "SUP",
        item["number"],
        "| Published:",
        item["publication_date"],
        "| Effective:",
        item["effective_from"],
        "|",
        item["title"]
    )


print(
    "----------------------------------------"
)

print(
    "AIC SUMMARY"
)

print(
    "----------------------------------------"
)


for item in aic_documents:

    print(
        "AIC",
        item["number"],
        "| Published:",
        item["publication_date"],
        "| Effective:",
        item["effective_from"],
        "|",
        item["title"]
    )
