import os,re,json,requests,time,sys
from bs4 import BeautifulSoup
from datetime import datetime,timezone
from urllib.parse import urljoin

HISTORY_URL="https://aim.koca.go.kr/eaipPub/Package/history-en-GB.html"
HISTORY_FILE="korea_history.json"
STATUS_FILE="korea_aip.json"
ARCHIVE_ROOT=os.path.join("archive","korea")
HEADERS={"User-Agent":"Mozilla/5.0 Chrome/120.0"}
NOW=datetime.now(timezone.utc).isoformat()

def get(url, timeout=15, attempts=3):
    last_error=None
    for attempt in range(1, attempts+1):
        try:
            r=requests.get(url,headers=HEADERS,timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_error=e
            print(f"Korea request attempt {attempt}/{attempts} failed: {url} -> {e}",flush=True)
            if attempt < attempts:
                time.sleep(5*attempt)
    raise last_error
def clean(s): return re.sub(r"\s+"," ",str(s or "")).strip()
def dt(s):
    for f in ("%d %b %Y","%d %b %y"):
        try:return datetime.strptime(clean(s).upper(),f)
        except ValueError:pass
    return None
def safe(n): return re.sub(r"[^A-Za-z0-9_-]+","-",str(n).replace("/","-")).strip("-")
def year(n):
    m=re.search(r"/(\d{2})$",str(n or "")); return "20"+m.group(1) if m else "unknown"
def aurl(p): return "../"+p.replace(os.sep,"/")
def save_pdf(url,path):
    if os.path.exists(path): return True
    try:
        r=get(url,60)
        if not (r.content.startswith(b"%PDF") or "pdf" in (r.headers.get("content-type") or "").lower()): return False
        os.makedirs(os.path.dirname(path),exist_ok=True)
        open(path,"wb").write(r.content); print("Archived:",path); return True
    except Exception as e: print("Archive error:",url,e); return False
def load():
    try:return json.load(open(HISTORY_FILE,encoding="utf-8"))
    except Exception:return {"country":"Republic of Korea","fir":"Incheon FIR","amendments":[],"sup":[],"aic":[]}
def merge(old,new,key):
    d={key(x):dict(x) for x in old if key(x)}
    for x in new:
        k=key(x)
        if not k:continue
        if k in d:
            first=d[k].get("first_seen") or NOW
            d[k].update({a:b for a,b in x.items() if b is not None}); d[k]["first_seen"]=first; d[k]["last_seen"]=NOW
        else:
            d[k]=dict(x); d[k]["first_seen"]=NOW; d[k]["last_seen"]=NOW
    return list(d.values())

# AMDT: official Korea history page
# Korea renders each issue as a link whose label is the EFFECTIVE DATE,
# while the publication date and AMDT name are adjacent text. Therefore
# parse the page's visible text for issue metadata and match package links
# by their effective-date label instead of assuming a <tr> structure.
def run_monitor():
    s=BeautifulSoup(get(HISTORY_URL).text,"html.parser"); amdt=[]

    page_text=clean(s.get_text(" ",strip=True))
    issue_pattern=re.compile(
        r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})\s+"
        r"(\d{1,2}\s+[A-Z]{3}\s+\d{4})\s+"
        r"(AIRAC AIP AMDT|AIP AMDT)\s+(\d{1,2}/\d{2})",
        re.I
    )

    package_links={}
    for a in s.find_all("a",href=True):
        label=clean(a.get_text(" ",strip=True)).upper()
        if re.fullmatch(r"\d{1,2}\s+[A-Z]{3}\s+\d{4}",label):
            package_links.setdefault(label,[]).append(urljoin(HISTORY_URL,a["href"]))

    for m in issue_pattern.finditer(page_text):
        eff,pub,typ,num=m.group(1).upper(),m.group(2).upper(),m.group(3).upper(),m.group(4)
        links=package_links.get(eff,[])
        if not links:
            print("No package link for:",typ,num,eff)
            continue

        # If multiple issues share an effective date, AIRAC package URLs normally
        # contain '-AIRAC'; prefer the matching package type.
        if typ.startswith("AIRAC"):
            idx=next((u for u in links if "AIRAC" in u.upper()),links[0])
        else:
            idx=next((u for u in links if "AIRAC" not in u.upper()),links[0])

        root=idx.split("/html/",1)[0]+"/"
        src=idx; arc=None
        amdt.append({"number":num,"amendment_type":typ,"title":f"{typ} {num}","publication_date":pub,
                     "effective_date":eff,"effective_from":eff,"source_url":src,"package_url":idx,"archive_url":arc})
    if not amdt: raise RuntimeError("Could not parse Korea AMDT history.")

    # Deduplicate and resolve current/next by effective date
    amdt=list({(x["amendment_type"],x["number"]):x for x in amdt}.values())
    today=datetime.now().date()
    dated=[x for x in amdt if dt(x.get("effective_date"))]
    past=[x for x in dated if dt(x["effective_date"]).date()<=today]
    future=[x for x in dated if dt(x["effective_date"]).date()>today]
    current=max(past,key=lambda x:dt(x["effective_date"]),default=None)
    next_issue=min(future,key=lambda x:dt(x["effective_date"]),default=None)
    print("Korea current:",current); print("Korea next:",next_issue)

    # SUP: GEN 0.3 explicitly lists Current AIP SUP + Current AIRAC AIP SUP.
    def rootof(x):
        u=(x or {}).get("package_url",""); return u.split("/html/",1)[0]+"/" if "/html/" in u else None
    def sup_from_gen03(root):
        if not root:return []
        try:ss=BeautifulSoup(get(urljoin(root,"html/eAIP/KR-GEN-0.3-en-GB.html")).text,"html.parser")
        except Exception as e: print("GEN 0.3 error:",e); return []
        out=[]
        for table in ss.find_all("table"):
            # GEN 0.3 has separate "Current AIP Supplement" and
            # "Current AIRAC AIP Supplement" sections. Walk backwards to the
            # nearest visible section label instead of sampling arbitrary nodes.
            typ="AIP SUP"
            node=table
            for _ in range(30):
                node=node.find_previous()
                if node is None:
                    break
                txt=clean(node.get_text(" ",strip=True)) if hasattr(node,"get_text") else ""
                if "Current AIRAC AIP Supplement" in txt:
                    typ="AIRAC AIP SUP"
                    break
                if "Current AIP Supplement" in txt:
                    typ="AIP SUP"
                    break
            for tr in table.find_all("tr"):
                c=[clean(x.get_text(" ",strip=True)) for x in tr.find_all(["td","th"])]
                if len(c)<2 or not re.fullmatch(r"\d{1,3}/\d{2}",c[0]):continue
                num,title=c[0],c[1]; period=c[3] if len(c)>3 else ""
                em=re.search(r"Effective\s*:\s*(?:\d{4}UTC\s*)?(\d{1,2}\s+[A-Z]{3}\s+\d{4})",title,re.I)
                eff=em.group(1).upper() if em else None
                dates=re.findall(r"\d{1,2}\s+[A-Z]{3}\s+\d{2}",period.upper())
                until=(dt(dates[-1]).strftime("%d %b %Y").upper() if len(dates)>=2 and dt(dates[-1]) else ("PERM" if "PERM" in period.upper() else None))
                yy="20"+num.split("/")[1]; nr=str(int(num.split("/")[0]))
                pdf=urljoin(root,f"html/eSUP/KR-eSUP-{yy}-{nr}-en-GB.pdf")
                # Fast monitor: do not download/archive PDFs during routine checks.
                arc=None
                out.append({"number":num,"sup_type":typ,"title":re.sub(r"\s*\\(Effective\s*:.*?\\)\s*"," ",title,flags=re.I).strip(),
                            "publication_date":None,"effective_from":eff,"effective_until":until,"source_url":pdf,"archive_url":arc,"source_status":"CURRENT"})
        return list({x["number"]:x for x in out}.values())

    sup=sup_from_gen03(rootof(current))
    if not sup:
        for x in sorted(amdt,key=lambda z:dt(z.get("effective_date")) or datetime.min,reverse=True):
            sup=sup_from_gen03(rootof(x))
            if sup:break
    from collections import Counter
    print("Current Korea SUP:",len(sup))
    print("Korea SUP types:",dict(Counter(x.get("sup_type","UNKNOWN") for x in sup)))
    print("Korea SUP sample:")
    for x in sup[:5]:
        print("  ",x.get("number"),"|",x.get("sup_type"),"|",x.get("title"))

    # AIC: authoritative current checklist
    # Korea publishes an annual AIC checklist. For 2026, AIC 1/26 states that
    # the listed AICs are still current and that omitted AICs are cancelled,
    # expired, or incorporated into the AIP.
    AIC_CHECKLIST_URL="https://aim.koca.go.kr/eaipPub/Package/2026-01-08/html/eAIC/AIC%201-en-GB.pdf"

    # Current list from official AIC 1/26. Keep this explicit and safe: if a newer
    # checklist is published later, we will update discovery rather than silently
    # dropping current historical records.
    CURRENT_AIC_2026=[
        ("5/21","Imposition of a New Air Navigation Services Charge"),
        ("7/21","Imposition of a New Aeronautical Meteorological Services Charge"),
        ("2/25","The Korean AIP Abroad Will Be Distributed by the Website and CD Only"),
        ("3/25","Provision of Aviation Information from Upper-air Instrument(Rawinsonde) of the Korea Meteorological Administration(KMA)"),
        ("6/25","Notice of Extension for Installation Deadline of Autonomous Distress Tracking device"),
        ("8/25","Snow Plan 2025/2026"),
        ("9/25","Subscription to Aeronautical Information Publication and Order Form 2026"),
    ]

    def aic_source_url(number):
        nr,yy=number.split("/")
        year=2000+int(yy)
        # AIC files are carried forward inside later packages; the checklist is the
        # authoritative evidence of current status. Individual historical package
        # locations are not guessed here.
        return AIC_CHECKLIST_URL

    aic=[]
    for num,title in CURRENT_AIC_2026:
        aic.append({
            "number":num,
            "title":title,
            "publication_date":None,
            "effective_from":None,
            "effective_until":None,
            "source_url":aic_source_url(num),
            "archive_url":None,
            "source_status":"CURRENT",
            "current_checklist":"1/26",
            "checklist_url":AIC_CHECKLIST_URL
        })
    print("Korea AIC current from checklist:",len(aic))
    for x in aic:
        print("  ",x["number"],"|",x["title"])

    h=load(); h.update({"country":"Republic of Korea","fir":"Incheon FIR","source":HISTORY_URL})
    h["amendments"]=merge(h.get("amendments",[]),amdt,lambda x:(x.get("amendment_type"),x.get("number")))
    h["sup"]=merge(h.get("sup",[]),sup,lambda x:x.get("number"))
    # AIC documents in the same annual checklist share the checklist URL.
    # Their document number is the stable identity; using source_url here
    # collapses all 7 current AICs into one record.
    if aic:
        h["aic"]=merge(h.get("aic",[]),aic,lambda x:x.get("number"))
    else:
        h.setdefault("aic",[])
    h["last_checked"]=NOW
    json.dump(h,open(HISTORY_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    status={"country":"Republic of Korea","icao":"RK","fir":"Incheon FIR","source":HISTORY_URL,"checked_at":NOW,"status":"OK",
            "current":current,"next":next_issue,"counts":{"amendments":len(h["amendments"]),"current_sup":len(sup),"aic_history":len(h["aic"])}}
    json.dump(status,open(STATUS_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("Saved Korea:",len(h["amendments"]),"AMDT,",len(h["sup"]),"SUP,",len(h["aic"]),"AIC")

try:
    run_monitor()
except requests.RequestException as e:
    print("",flush=True)
    print("WARNING: Korea official source is temporarily unavailable.",flush=True)
    print("Existing korea_history.json and korea_aip.json are preserved unchanged.",flush=True)
    print(f"Reason: {e}",flush=True)
    print("Korea monitor skipped safely; the next scheduled run will retry.",flush=True)
    sys.exit(0)
