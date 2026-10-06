import os,re,json,requests
from bs4 import BeautifulSoup
from datetime import datetime,timezone
from urllib.parse import urljoin

HISTORY_URL="https://aim.koca.go.kr/eaipPub/Package/history-en-GB.html"
HISTORY_FILE="korea_history.json"
STATUS_FILE="korea_aip.json"
ARCHIVE_ROOT=os.path.join("archive","korea")
HEADERS={"User-Agent":"Mozilla/5.0 Chrome/120.0"}
NOW=datetime.now(timezone.utc).isoformat()

def get(url,timeout=45):
    r=requests.get(url,headers=HEADERS,timeout=timeout); r.raise_for_status(); return r
def clean(s): return re.sub(r"\\s+"," ",str(s or "")).strip()
def dt(s):
    for f in ("%d %b %Y","%d %b %y"):
        try:return datetime.strptime(clean(s).upper(),f)
        except ValueError:pass
    return None
def safe(n): return re.sub(r"[^A-Za-z0-9_-]+","-",str(n).replace("/","-")).strip("-")
def year(n):
    m=re.search(r"/(\\d{2})$",str(n or "")); return "20"+m.group(1) if m else "unknown"
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
s=BeautifulSoup(get(HISTORY_URL).text,"html.parser"); amdt=[]
for tr in s.find_all("tr"):
    t=clean(tr.get_text(" ",strip=True))
    m=re.search(r"(AIRAC AIP AMDT|AIP AMDT)\\s+(\\d{1,2}/\\d{2})",t,re.I)
    a=tr.find("a",href=True)
    if not m or not a: continue
    typ,num=m.group(1).upper(),m.group(2)
    dates=re.findall(r"\\b\\d{1,2}\\s+[A-Z]{3}\\s+\\d{4}\\b",t.upper())
    eff=dates[0] if dates else None; pub=dates[1] if len(dates)>1 else None
    idx=urljoin(HISTORY_URL,a["href"]); root=idx.split("/html/",1)[0]+"/"
    n,y=num.split("/")
    names=([f"AIRAC AIP AMDT {n}_{y}.pdf"] if typ.startswith("AIRAC") else [f"AIP AMDT {n}_{y}.pdf"])
    src=idx; arc=None
    rel=os.path.join(ARCHIVE_ROOT,"amdt",year(num),("AIRAC-" if typ.startswith("AIRAC") else "AIP-")+safe(num)+".pdf")
    for name in names:
        u=urljoin(root,"pdf/"+name)
        if save_pdf(u,rel): src=u; arc=aurl(rel); break
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
        prev=" ".join(clean(x.get_text(" ",strip=True)) for x in table.find_all_previous(["h1","h2","h3","h4","p"],limit=5))
        typ="AIRAC AIP SUP" if "Current AIRAC AIP Supplement" in prev else "AIP SUP"
        for tr in table.find_all("tr"):
            c=[clean(x.get_text(" ",strip=True)) for x in tr.find_all(["td","th"])]
            if len(c)<2 or not re.fullmatch(r"\\d{1,3}/\\d{2}",c[0]):continue
            num,title=c[0],c[1]; period=c[3] if len(c)>3 else ""
            em=re.search(r"Effective\\s*:\\s*(?:\\d{4}UTC\\s*)?(\\d{1,2}\\s+[A-Z]{3}\\s+\\d{4})",title,re.I)
            eff=em.group(1).upper() if em else None
            dates=re.findall(r"\\d{1,2}\\s+[A-Z]{3}\\s+\\d{2}",period.upper())
            until=(dt(dates[-1]).strftime("%d %b %Y").upper() if len(dates)>=2 and dt(dates[-1]) else ("PERM" if "PERM" in period.upper() else None))
            yy="20"+num.split("/")[1]; nr=str(int(num.split("/")[0]))
            pdf=urljoin(root,f"html/eSUP/KR-eSUP-{yy}-{nr}-en-GB.pdf")
            rel=os.path.join(ARCHIVE_ROOT,"sup",year(num),safe(num)+".pdf")
            arc=aurl(rel) if save_pdf(pdf,rel) else None
            out.append({"number":num,"sup_type":typ,"title":re.sub(r"\\s*\\(Effective\\s*:.*?\\)\\s*"," ",title,flags=re.I).strip(),
                        "publication_date":None,"effective_from":eff,"effective_until":until,"source_url":pdf,"archive_url":arc,"source_status":"CURRENT"})
    return list({x["number"]:x for x in out}.values())

sup=sup_from_gen03(rootof(current))
if not sup:
    for x in sorted(amdt,key=lambda z:dt(z.get("effective_date")) or datetime.min,reverse=True):
        sup=sup_from_gen03(rootof(x))
        if sup:break
print("Current Korea SUP:",len(sup))

# AIC discovery: keep old history even if no links are found on a run.
def aics(root):
    if not root:return []
    found={}
    for p in ("html/index-en-GB.html","html/eAIC/menu-en-GB.html","html/eAIC/menu.html"):
        try:ss=BeautifulSoup(get(urljoin(root,p)).text,"html.parser")
        except Exception:continue
        for a in ss.find_all("a",href=True):
            u=urljoin(urljoin(root,p),a["href"])
            m=re.search(r"/eAIC/AIC(?:%20|\\s)(\\d{1,2})-en-GB\\.pdf",u,re.I)
            if not m:continue
            nr=int(m.group(1)); py=re.search(r"/Package/(\\d{4})-",root); yy=(py.group(1)[2:] if py else str(today.year)[2:])
            num=f"{nr}/{yy}"; rel=os.path.join(ARCHIVE_ROOT,"aic",year(num),safe(num)+".pdf")
            found[u]={"number":num,"title":f"AIC {num}","publication_date":None,"effective_from":None,
                      "effective_until":None,"source_url":u,"archive_url":aurl(rel) if save_pdf(u,rel) else None,"source_status":"DISCOVERED"}
    return list(found.values())
aic=[]
for x in sorted(amdt,key=lambda z:dt(z.get("effective_date")) or datetime.min,reverse=True)[:6]:
    aic+=aics(rootof(x))
aic=list({x["source_url"]:x for x in aic}.values())
print("Korea AIC discovered:",len(aic))

h=load(); h.update({"country":"Republic of Korea","fir":"Incheon FIR","source":HISTORY_URL})
h["amendments"]=merge(h.get("amendments",[]),amdt,lambda x:(x.get("amendment_type"),x.get("number")))
h["sup"]=merge(h.get("sup",[]),sup,lambda x:x.get("number"))
if aic:h["aic"]=merge(h.get("aic",[]),aic,lambda x:x.get("source_url") or x.get("number"))
else:h.setdefault("aic",[])
h["last_checked"]=NOW
json.dump(h,open(HISTORY_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
status={"country":"Republic of Korea","icao":"RK","fir":"Incheon FIR","source":HISTORY_URL,"checked_at":NOW,"status":"OK",
        "current":current,"next":next_issue,"counts":{"amendments":len(h["amendments"]),"current_sup":len(sup),"aic_history":len(h["aic"])}}
json.dump(status,open(STATUS_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("Saved Korea:",len(h["amendments"]),"AMDT,",len(h["sup"]),"SUP,",len(h["aic"]),"AIC")
