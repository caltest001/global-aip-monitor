import requests
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime, timezone
from urllib.parse import urljoin


# ============================================================
# Basic settings
# ============================================================

URL = "https://ais.caa.gov.tw/eaip/"

headers = {
    "User-Agent": "Mozilla/5.0"
}


# ============================================================
# Taiwan AIP AMDT Monitor
# ============================================================

response = requests.get(
    URL,
    headers=headers,
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


# ------------------------------------------------------------
# Current issue
# ------------------------------------------------------------

current_section = extract_section(
    text,
    "Currently Effective Issue",
    "Next Issues"
)

current_issue = parse_issue(
    current_section
)


# ------------------------------------------------------------
# Next issue
# ------------------------------------------------------------

next_section = extract_section(
    text,
    "Next Issues",
    "Expired Issues"
)

next_issue = parse_issue(
    next_section
)


# ------------------------------------------------------------
# Save AIP AMDT data
# ------------------------------------------------------------

data = {
    "state": "Taiwan",
    "icao": "RC",
    "source": URL,

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
        data,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )
)


# ============================================================
# Detect new AIP amendment
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
# Taiwan SUP + AIC Monitor
# ============================================================

#
# IMPORTANT:
# This package is temporarily fixed to the
# currently verified Taiwan eAIP package.
#
# We will automate package detection separately
# after the stable version is confirmed.
#

PACKAGE_URL = (
    "https://ais.caa.gov.tw/eaip/"
    "AIRAC%20AIP%20AMDT%2004-26_2026_10_01/"
)


SUP_MENU_URL = urljoin(
    PACKAGE_URL,
    "eSUP/menu.html"
)


AIC_MENU_URL = urljoin(
    PACKAGE_URL,
    "eAIC/menu.html"
)


print(
    "Current eAIP package:",
    PACKAGE_URL
)


# ============================================================
# Get document links from SUP / AIC menu
# ============================================================

def get_document_links(
    menu_url,
    doc_type
):

    documents = {}

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


        for link in menu_soup.find_all(
            "a",
            href=True
        ):

            label = link.get_text(
                " ",
                strip=True
            )

            href = link["href"]


            # Find document number
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


            # SUP English document
            if doc_type == "SUP":

                if (
                    "SUP-en-GB.html"
                    not in href
                ):
                    continue


            # AIC English document
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


    except Exception as e:

        print(
            f"{doc_type} menu error:",
            e
        )


    return documents


# ============================================================
# Parse SUP / AIC document
# ============================================================

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


        # ----------------------------------------------------
        # Publication Date
        # ----------------------------------------------------

        pub_match = re.search(
            r"Published\s+on\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )


        # ----------------------------------------------------
        # Effective From / Until
        # ----------------------------------------------------

        effective_match = re.search(
            r"Effective\s+from\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})"
            r"(?:\s+to\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4}))?",
            doc_text,
            re.IGNORECASE
        )


        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # AIC checklist fallback
        # ----------------------------------------------------

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
# Collect SUP documents
# ============================================================

sup_links = get_document_links(
    SUP_MENU_URL,
    "SUP"
)


sup_documents = []


for number, url in (
    sup_links.items()
):

    document = parse_document(
        number,
        url,
        "SUP"
    )

    if document:
        sup_documents.append(
            document
        )


# ============================================================
# Collect AIC documents
# ============================================================

aic_links = get_document_links(
    AIC_MENU_URL,
    "AIC"
)


aic_documents = []


for number, url in (
    aic_links.items()
):

    document = parse_document(
        number,
        url,
        "AIC"
    )

    if document:
        aic_documents.append(
            document
        )


# ============================================================
# Sort documents
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
# SAFETY CHECK
#
# Do NOT overwrite good existing data when
# the CAA website cannot be read correctly.
# ============================================================

total_documents = (
    len(sup_documents)
    +
    len(aic_documents)
)


if total_documents == 0:

    print(
        "⚠️ WARNING: No SUP/AIC "
        "documents were found."
    )

    print(
        "Existing document files "
        "will NOT be overwritten."
    )


else:

    # --------------------------------------------------------
    # Combined SUP + AIC file
    # --------------------------------------------------------

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

        "source":
            PACKAGE_URL,

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


    # --------------------------------------------------------
    # Keep taiwan_sup.json for compatibility
    # --------------------------------------------------------

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
# Print document summary
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
