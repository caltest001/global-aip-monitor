import requests
from bs4 import BeautifulSoup
import json
import re
import os
import base64
import mimetypes
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
# Permanent Taiwan Document Archive
#
# AMDT:
#   Save the official PDF.
#
# SUP / AIC:
#   Save only the publication content in a clean, self-contained
#   HTML page. No dependency on the authority's CSS, scripts,
#   navigation, or image assets.
#
# REBUILD_HTML_ARCHIVE = True is intentional for the next run:
# it rebuilds old SUP/AIC snapshots in the simplified format.
# After one successful run, change it back to False.
# ============================================================

ARCHIVE_ROOT = os.path.join("archive", "taiwan")
REBUILD_HTML_ARCHIVE = False


def archive_year(number):
    match = re.search(r"/(\d{2})$", str(number or "").strip())
    return "20" + match.group(1) if match else "unknown"


def archive_safe_number(number):
    return str(number or "unknown").strip().replace("/", "-")


def github_pages_archive_url(relative_path):
    return "../" + relative_path.replace(os.sep, "/")


def save_binary_archive(source_url, relative_path):
    if os.path.exists(relative_path):
        print("Archive already exists:", relative_path)
        return True

    try:
        r = requests.get(source_url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        os.makedirs(os.path.dirname(relative_path), exist_ok=True)

        with open(relative_path, "wb") as f:
            f.write(r.content)

        print("Archived binary:", relative_path)
        return True
    except Exception as e:
        print("Archive binary error:", source_url, e)
        return False


def clean_publication_content(doc_soup):
    # Remove elements that are not part of the publication body.
    for tag in doc_soup.find_all([
        "script", "style", "noscript", "nav", "header", "footer",
        "iframe", "object", "embed", "form", "button"
    ]):
        tag.decompose()

    # Remove images: user only needs the textual/table content.
    for tag in doc_soup.find_all(["img", "svg", "picture", "video", "audio"]):
        tag.decompose()

    # Remove external styling and event attributes while preserving
    # semantic HTML such as headings, paragraphs, lists and tables.
    for tag in doc_soup.find_all(True):
        for attr in list(tag.attrs):
            if (
                attr.lower() == "style" or
                attr.lower() == "class" or
                attr.lower() == "id" or
                attr.lower().startswith("on")
            ):
                del tag.attrs[attr]

        if tag.name == "a" and tag.get("href"):
            href = tag.get("href")
            if href.startswith(("javascript:", "#")):
                tag.unwrap()

    body = doc_soup.body or doc_soup

    # Copy body children into a new fragment so the archive does not
    # inherit the authority website's page shell.
    fragment = BeautifulSoup("<div></div>", "html.parser")
    holder = fragment.div

    for child in list(body.contents):
        holder.append(child.extract())

    return holder


def save_html_snapshot(source_url, relative_path, label):
    if os.path.exists(relative_path) and not REBUILD_HTML_ARCHIVE:
        print("Archive already exists:", relative_path)
        return True

    try:
        r = requests.get(source_url, headers=HEADERS, timeout=60)
        r.raise_for_status()

        original = BeautifulSoup(r.content, "html.parser")
        content = clean_publication_content(original)

        archived_at = datetime.now(timezone.utc).isoformat()

        page = BeautifulSoup(
            """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title></title>
<style>
body{
  margin:0;
  background:#f4f6f9;
  color:#172033;
  font-family:Arial,Helvetica,sans-serif;
  line-height:1.55;
}
main{
  max-width:1100px;
  margin:32px auto;
  background:#fff;
  border:1px solid #dfe5ec;
  border-radius:10px;
  padding:28px 34px 40px;
}
.archive-head{
  border-bottom:2px solid #17365d;
  padding-bottom:18px;
  margin-bottom:24px;
}
.archive-head h1{
  margin:0 0 8px;
  color:#17365d;
  font-size:25px;
}
.meta{
  color:#64748b;
  font-size:13px;
  margin-top:5px;
}
.content{
  overflow-x:auto;
}
.content table{
  border-collapse:collapse;
  max-width:100%;
}
.content th,.content td{
  border:1px solid #aeb8c4;
  padding:6px 8px;
  vertical-align:top;
}
.content h1,.content h2,.content h3,.content h4{
  color:#17365d;
}
.content pre{
  white-space:pre-wrap;
}
.content a{
  color:#1769aa;
}
@media(max-width:700px){
  main{margin:0;border:0;border-radius:0;padding:20px 16px}
}
</style>
</head>
<body>
<main>
  <div class="archive-head">
    <h1></h1>
    <div class="meta archived-at"></div>
    <div class="meta official"></div>
  </div>
  <div class="content"></div>
</main>
</body>
</html>""",
            "html.parser"
        )

        page.title.string = f"{label} | Global AIP Monitor Archive"
        page.select_one(".archive-head h1").string = label
        page.select_one(".archived-at").string = f"Archived: {archived_at}"

        official = page.select_one(".official")
        official.append("Official source: ")
        a = page.new_tag("a", href=source_url)
        a["target"] = "_blank"
        a["rel"] = "noopener noreferrer"
        a.string = source_url
        official.append(a)

        target = page.select_one(".content")
        for child in list(content.contents):
            target.append(child.extract())

        os.makedirs(os.path.dirname(relative_path), exist_ok=True)
        with open(relative_path, "w", encoding="utf-8") as f:
            f.write(str(page))

        print(
            "Rebuilt content archive:" if REBUILD_HTML_ARCHIVE
            else "Archived content:",
            relative_path
        )
        return True

    except Exception as e:
        print("Archive HTML error:", source_url, e)
        return False


def archive_amendment(issue):
    number = amendment_number(issue)
    if not number:
        return None

    package_url = build_package_url(issue)
    if not package_url:
        return None

    source_url = urljoin(package_url, "documents/PDF/AMDT.pdf")
    relative_path = os.path.join(
        ARCHIVE_ROOT, "amdt", archive_year(number),
        archive_safe_number(number) + ".pdf"
    )

    if save_binary_archive(source_url, relative_path):
        return github_pages_archive_url(relative_path)
    return None


def archive_html_publication(item, doc_type):
    number = item.get("number")
    source_url = item.get("url")

    if not number or not source_url:
        return None

    relative_path = os.path.join(
        ARCHIVE_ROOT, doc_type.lower(), archive_year(number),
        archive_safe_number(number) + ".html"
    )

    if save_html_snapshot(source_url, relative_path, f"{doc_type} {number}"):
        return github_pages_archive_url(relative_path)
    return None


# ============================================================
# Permanent Taiwan History
#
# This archive is append-only in practice:
# - New items are added.
# - Existing items are updated with last_seen/source_status.
# - Items missing from the current official source are retained.
# - Absence alone never marks an item removed.
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
    A missing item is retained unchanged and is never deleted.
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

    # Never delete history.
    # Absence from the current snapshot is NOT sufficient evidence
    # that an official document has been withdrawn or removed.
    # Retain historical items unchanged unless they are seen again.
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
                urljoin(
                    build_package_url(issue),
                    "documents/PDF/AMDT.pdf"
                )
                if build_package_url(issue)
                else BASE_URL
            ),
            "archive_url": archive_amendment(issue)
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
            "source_url": item.get("url"),
            "archive_url": archive_html_publication(
                item,
                "SUP"
            )
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
            "source_url": item.get("url"),
            "archive_url": archive_html_publication(
                item,
                "AIC"
            )
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


# ============================================================
# Persistent Action Alerts
#
# Purpose:
# - taiwan_history.json = permanent archive
# - alerts.json = documents first discovered AFTER the baseline
# - Cloudflare D1 = processed/done state (handled by dashboard)
#
# IMPORTANT:
# Existing history is the baseline. It must never be turned into
# a backlog of alerts when this feature is first enabled.
# ============================================================

ALERTS_FILE = "alerts.json"
ALERTS_BASELINE_FILE = ".alerts_baseline_ready"


def load_alerts():
    try:
        with open(
            ALERTS_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Alerts root must be an object.")

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError
    ):
        data = {
            "country": "Taiwan",
            "alerts": []
        }

    data.setdefault("country", "Taiwan")
    data.setdefault("alerts", [])

    if not isinstance(data["alerts"], list):
        data["alerts"] = []

    return data


def alert_id(doc_type, number):
    safe_number = re.sub(
        r"[^A-Z0-9_-]+",
        "-",
        str(number or "").strip().upper().replace("/", "-")
    )
    safe_number = re.sub(r"-+", "-", safe_number).strip("-")

    return f"TW-{doc_type}-{safe_number}"


def make_alert(
    doc_type,
    number,
    title,
    publication_date=None,
    effective_from=None,
    effective_until=None,
    source_url=None
):
    return {
        "document_id": alert_id(doc_type, number),
        "country": "Taiwan",
        "fir": "Taipei FIR",
        "document_type": doc_type,
        "document_number": number,
        "title": title or "—",
        "publication_date": publication_date,
        "effective_from": effective_from,
        "effective_until": effective_until,
        "source_url": source_url,
        "first_seen": history_now
    }


alerts_data = load_alerts()

existing_alert_ids = {
    item.get("document_id")
    for item in alerts_data.get("alerts", [])
    if item.get("document_id")
}


# First deployment is baseline-only.
#
# If alerts.json is empty and the baseline marker does not exist,
# the current official/history data is treated as already known.
# No alert is created. The marker is then written so later runs
# can create alerts only for genuinely new history records.
try:
    with open(
        ALERTS_BASELINE_FILE,
        "r",
        encoding="utf-8"
    ):
        baseline_ready = True

except FileNotFoundError:
    baseline_ready = False


if not baseline_ready:

    with open(
        ALERTS_BASELINE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(
            "Taiwan alerts baseline established at "
            + history_now
            + "\\n"
        )

    print(
        "Alerts baseline established. "
        "Existing Taiwan history was NOT added as pending alerts."
    )

else:

    # --------------------------------------------------------
    # AIRAC / AIP AMDT alerts
    # --------------------------------------------------------

    for item in current_amendments:

        number = item.get("number")
        if not number:
            continue

        document_id = alert_id("AMDT", number)

        # Alert only if this record was first discovered in THIS run.
        history_item = next(
            (
                x for x in taiwan_history["amendments"]
                if x.get("number") == number
            ),
            None
        )

        if (
            history_item
            and history_item.get("first_seen") == history_now
            and document_id not in existing_alert_ids
        ):
            alert = make_alert(
                "AMDT",
                number,
                item.get("title"),
                item.get("publication_date"),
                item.get("effective_date"),
                None,
                item.get("source_url")
            )

            alerts_data["alerts"].append(alert)
            existing_alert_ids.add(document_id)

            print(
                "🔴 NEW ACTION ALERT:",
                document_id
            )


    # --------------------------------------------------------
    # SUP alerts
    # --------------------------------------------------------

    for item in current_sup_history:

        number = item.get("number")
        if not number:
            continue

        document_id = alert_id("SUP", number)

        history_item = next(
            (
                x for x in taiwan_history["sup"]
                if x.get("number") == number
            ),
            None
        )

        if (
            history_item
            and history_item.get("first_seen") == history_now
            and document_id not in existing_alert_ids
        ):
            alert = make_alert(
                "SUP",
                number,
                item.get("title"),
                item.get("publication_date"),
                item.get("effective_from"),
                item.get("effective_until"),
                item.get("source_url")
            )

            alerts_data["alerts"].append(alert)
            existing_alert_ids.add(document_id)

            print(
                "🔴 NEW ACTION ALERT:",
                document_id
            )


    # --------------------------------------------------------
    # AIC alerts
    # --------------------------------------------------------

    for item in current_aic_history:

        number = item.get("number")
        if not number:
            continue

        document_id = alert_id("AIC", number)

        history_item = next(
            (
                x for x in taiwan_history["aic"]
                if x.get("number") == number
            ),
            None
        )

        if (
            history_item
            and history_item.get("first_seen") == history_now
            and document_id not in existing_alert_ids
        ):
            alert = make_alert(
                "AIC",
                number,
                item.get("title"),
                item.get("publication_date"),
                item.get("effective_from"),
                item.get("effective_until"),
                item.get("source_url")
            )

            alerts_data["alerts"].append(alert)
            existing_alert_ids.add(document_id)

            print(
                "🔴 NEW ACTION ALERT:",
                document_id
            )


alerts_data["last_checked"] = history_now


with open(
    ALERTS_FILE,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        alerts_data,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    "Saved action alerts:",
    len(alerts_data["alerts"])
)
