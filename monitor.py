import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urljoin


# ============================================================
# Settings
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
# Basic Helpers
# ============================================================

def extract_section(text, start, end=None):
    try:
        section = text.split(start, 1)[1]

        if end and end in section:
            section = section.split(end, 1)[0]

        return section.strip()

    except IndexError:
        return ""


def parse_issue(section):
    """
    Parse the first AIP AMDT issue found in a section.

    Example:
    AIRAC AIP AMDT 04/26
    01 Oct 2026
    20 Aug 2026
    """

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
            dates[0] if len(dates) >= 1 else None,

        "publication_date":
            dates[1] if len(dates) >= 2 else None
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
# Parse Current / Next / Previous
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

expired_section = extract_section(
    text,
    "Expired Issues"
)


current_issue = parse_issue(
    current_section
)

next_issue = parse_issue(
    next_section
)

previous_issue_data = parse_issue(
    expired_section
)


if not current_issue:
    raise RuntimeError(
        "Could not parse current Taiwan AIP issue."
    )


# ============================================================
# Debug Information
# ============================================================

print("Current issue:", current_issue)
print("Next issue:", next_issue)
print("Previous issue:", previous_issue_data)


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


previous_seen = (
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
    previous_seen
    and
    latest_issue != previous_seen
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
    print("Previous:", previous_seen)
    print("New:", latest_issue)

else:

    print("🟢 No new AIP update")


# ============================================================
# Build Package URL
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


    issue_number = number_match.group(1)
    issue_year = number_match.group(2)


    try:
        effective = datetime.strptime(
            effective_date,
            "%d %b %Y"
        )

    except ValueError:
        return None


    if amendment.startswith(
        "AIRAC AIP AMDT"
    ):
        prefix = "AIRAC AIP AMDT"

    else:
        prefix = "AIP AMDT"


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
# Generate Package Candidates Automatically
#
# Previous + Current + Next
#
# Package folders are only technical storage locations.
# They do NOT determine whether a SUP or AIC is current/new.
# ============================================================

PACKAGE_CANDIDATES = []


issues_to_check = [
    previous_issue_data,
    current_issue,
    next_issue
]


for issue in issues_to_check:

    package_url = build_package_url(
        issue
    )

    if (
        package_url
        and
        package_url not in PACKAGE_CANDIDATES
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


if not PACKAGE_CANDIDATES:
    raise RuntimeError(
        "No eAIP package candidates could be generated."
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


        return datetime.strptime(
            match.group(1).upper(),
            "%d %b %Y"
        )


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
# SUP and AIC are completely independent.
#
# The newest source is selected by the menu's own
# "Published as of" date.
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
# Select SUP and AIC Independently
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
# Get SUP / AIC Links
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


            number = number_match.group(1)


            if doc_type == "SUP":

                if (
                    "sup-en-gb.html"
                    not in href.lower()
                ):
                    continue


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


        # Publication date

        pub_match = re.search(
            r"Published\s+on\s+"
            r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})",
            doc_text,
            re.IGNORECASE
        )


        # Effective period

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


            if candidate_upper == "AIC":
                continue


            if len(candidate) <= 5:
                continue


            title = candidate
            break


        # AIC checklist fallback

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
                "AERONAUTICAL INFORMATION CIRCULARS"
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
# Load SUP / AIC Links
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


for number, document_url in sup_links.items():

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


for number, document_url in aic_links.items():

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
# Sort
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
# Safety Checks
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
# Summary
# ============================================================

print(
    f"Saved "
    f"{len(all_documents)} "
    f"documents to taiwan_documents.json"
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

# ============================================================
# Permanent Taiwan History
#
# This archive is append-only in practice:
# - New items are added.
# - Existing items are updated with last_seen/source_status.
# - Items missing from the current official source are retained
#   and marked REMOVED, never deleted.
# ============================================================

TAIWAN_HISTORY_FILE = "taiwan_history.json"
history_now = datetime.now(timezone.utc).isoformat()


def load_taiwan_history():
    try:
        with open(
            TAIWAN_HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("History root must be an object.")

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError
    ):
        data = {
            "country": "Taiwan",
            "fir": "Taipei FIR",
            "amendments": [],
            "sup": [],
            "aic": []
        }

    data.setdefault("country", "Taiwan")
    data.setdefault("fir", "Taipei FIR")
    data.setdefault("amendments", [])
    data.setdefault("sup", [])
    data.setdefault("aic", [])

    return data


def amendment_number(issue):
    if not issue:
        return None

    amendment = issue.get("amendment")

    if not amendment:
        return None

    match = re.search(
        r"(\d{1,2}/\d{2})",
        amendment
    )

    return match.group(1) if match else amendment


def update_history_collection(
    existing_items,
    current_items,
    key_field
):
    """
    Merge the latest official-source snapshot into permanent history.

    IMPORTANT:
    A missing item is marked REMOVED but is never deleted.
    """
    by_key = {}

    for item in existing_items:
        key = item.get(key_field)

        if key:
            by_key[key] = dict(item)

    active_keys = set()

    for current_item in current_items:
        key = current_item.get(key_field)

        if not key:
            continue

        active_keys.add(key)

        if key in by_key:
            saved = by_key[key]

            # Preserve first_seen, but refresh official metadata.
            first_seen = saved.get(
                "first_seen",
                history_now
            )

            saved.update(current_item)
            saved["first_seen"] = first_seen
            saved["last_seen"] = history_now
            saved["source_status"] = "ACTIVE"

        else:
            saved = dict(current_item)
            saved["first_seen"] = history_now
            saved["last_seen"] = history_now
            saved["source_status"] = "ACTIVE"
            by_key[key] = saved

            print(
                "🔴 NEW HISTORY ITEM:",
                key
            )

    # Never delete history. If it is no longer visible in the
    # official source snapshot, retain it and mark it REMOVED.
    for key, saved in by_key.items():
        if key not in active_keys:
            saved["source_status"] = "REMOVED"

    return list(by_key.values())


taiwan_history = load_taiwan_history()


# ------------------------------------------------------------
# AIRAC / AIP AMDT history
#
# Current + Next + Previous are all useful historical evidence.
# ------------------------------------------------------------

current_amendments = []

for issue in [
    previous_issue_data,
    current_issue,
    next_issue
]:
    if not issue:
        continue

    number = amendment_number(issue)

    if not number:
        continue

    current_amendments.append(
        {
            "number": number,
            "amendment": issue.get("amendment"),
            "title": issue.get("amendment"),
            "publication_date": issue.get(
                "publication_date"
            ),
            "effective_date": issue.get(
                "effective_date"
            ),
            "source_url": (
                build_package_url(issue)
                or BASE_URL
            )
        }
    )


taiwan_history["amendments"] = (
    update_history_collection(
        taiwan_history.get(
            "amendments",
            []
        ),
        current_amendments,
        "number"
    )
)


# ------------------------------------------------------------
# SUP history
# ------------------------------------------------------------

current_sup_history = []

for item in sup_documents:
    current_sup_history.append(
        {
            "number": item.get("number"),
            "title": item.get("title"),
            "publication_date": item.get(
                "publication_date"
            ),
            "effective_from": item.get(
                "effective_from"
            ),
            "effective_until": item.get(
                "effective_until"
            ),
            "source_url": item.get("url")
        }
    )


taiwan_history["sup"] = (
    update_history_collection(
        taiwan_history.get("sup", []),
        current_sup_history,
        "number"
    )
)


# ------------------------------------------------------------
# AIC history
# ------------------------------------------------------------

current_aic_history = []

for item in aic_documents:
    current_aic_history.append(
        {
            "number": item.get("number"),
            "title": item.get("title"),
            "publication_date": item.get(
                "publication_date"
            ),
            "effective_from": item.get(
                "effective_from"
            ),
            "effective_until": item.get(
                "effective_until"
            ),
            "source_url": item.get("url")
        }
    )


taiwan_history["aic"] = (
    update_history_collection(
        taiwan_history.get("aic", []),
        current_aic_history,
        "number"
    )
)


def history_sort(item):
    value = (
        item.get("number")
        or ""
    )

    match = re.search(
        r"(\d{1,2})/(\d{2})",
        value
    )

    if not match:
        return (0, 0)

    return (
        int(match.group(2)),
        int(match.group(1))
    )


taiwan_history["amendments"].sort(
    key=history_sort,
    reverse=True
)

taiwan_history["sup"].sort(
    key=history_sort,
    reverse=True
)

taiwan_history["aic"].sort(
    key=history_sort,
    reverse=True
)

taiwan_history["last_checked"] = history_now


with open(
    TAIWAN_HISTORY_FILE,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        taiwan_history,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    "Saved permanent Taiwan history:",
    len(taiwan_history["amendments"]),
    "AMDT,",
    len(taiwan_history["sup"]),
    "SUP,",
    len(taiwan_history["aic"]),
    "AIC"
)

