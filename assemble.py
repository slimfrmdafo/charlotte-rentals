#!/usr/bin/env python3
"""Assemble refreshed master_listings.json and rebuild index.html.
Fresh (2026-06-09): rent.com, craigslist, apartments.com, zillow.
Carried forward (2026-04-10): all other sources (tricon, redfin, PM companies).
"""
import json, re, html as htmllib

LO, HI = 1400, 1900
IDEAL = {"28207","28203","28216","28209","28204","28202","28206","28208","28205",
         "28210","28215","28262","28217","28277","28273"}
REFRESHED = {"rent.com","craigslist","apartments.com","zillow"}

def blank(**kw):
    b = dict(name="",address="",city="Charlotte",state="NC",zip="",neighborhood="",
             price_low=0,price_high=0,beds_low=0,beds_high=0,baths_low=0,baths_high=0,
             sqft_low=0,sqft_high=0,available_date="",property_type="apartment",
             url="",source="",special="",amenities=[])
    b.update(kw); return b

def overlap(plo,phi):
    if not plo and not phi: return False
    lo=min(p for p in (plo,phi) if p); hi=max(plo,phi)
    return lo<=HI and hi>=LO

rows=[]

# ---- fresh rent.com & craigslist (already unified schema) ----
for f in ("fresh_rentcom.json","fresh_craigslist.json"):
    rows += json.load(open(f))

# ---- fresh apartments.com (3 pages) ----
seen=set()
for f in ("apt_p1.json","apt_p2.json","apt_p3.json"):
    for x in json.load(open(f)):
        if not overlap(x["price_low"],x["price_high"]): continue
        if x["url"] in seen: continue
        seen.add(x["url"])
        rows.append(blank(name=x["name"],address=x.get("addr",""),zip=x.get("zip",""),
            price_low=x["price_low"],price_high=x["price_high"],
            beds_low=x["beds_low"],beds_high=x["beds_high"],
            property_type="apartment",url=x["url"],source="apartments.com",
            special=x.get("special","")))

# ---- fresh zillow (page 1) ----
for x in json.load(open("zillow_p1.json")):
    if not overlap(x["price_low"],x["price_high"]): continue
    t=(x.get("type") or "").lower()
    pt="house" if "single" in t or "townhouse" in t else "apartment"
    rows.append(blank(name=x.get("name","") or x.get("address",""),address=x.get("address",""),
        zip=str(x.get("zip","")),price_low=x["price_low"],price_high=x["price_high"],
        beds_low=x["beds_low"],beds_high=x["beds_high"],
        baths_low=int(x.get("baths") or 0),baths_high=int(x.get("baths") or 0),
        sqft_low=int(x.get("sqft") or 0),sqft_high=int(x.get("sqft") or 0),
        property_type=pt,url=x["url"],source="zillow"))

# ---- carry forward all non-refreshed sources from the original embedded data ----
html=open("index.html").read()
m=re.search(r'const listings = (\[.*?\]);', html, re.S)
orig=json.loads(m.group(1))
carried=0
for x in orig:
    if x.get("source") in REFRESHED: continue
    rows.append(x); carried+=1

# ---- stats ----
total=len(rows)
ideal=sum(1 for r in rows if str(r.get("zip","")) in IDEAL)
sources=len({r.get("source") for r in rows})
zips=len({str(r.get("zip")) for r in rows if r.get("zip")})
fresh_n=total-carried
print(f"total={total} fresh={fresh_n} carried={carried} ideal={ideal} sources={sources} zips={zips}")
from collections import Counter
for s,c in Counter(r.get("source") for r in rows).most_common():
    tag="FRESH" if s in REFRESHED else "Apr"
    print(f"  {c:4d}  {s}  [{tag}]")

json.dump(rows, open("master_listings.json","w"), indent=1)

# ---- rewrite index.html ----
data_js=json.dumps(rows, separators=(", ",": "))
repl="const listings = "+data_js+";"
html=re.sub(r'const listings = \[.*?\];', lambda _: repl, html, count=1, flags=re.S)
# header date
html=html.replace("Generated: April 10, 2026",
                  "Generated: April 10, 2026 · Refreshed: June 9, 2026 (rent.com, Craigslist, Apartments.com, Zillow live)")
# stat numbers (first four .num divs, in order)
def repl_stats(h):
    nums=[str(total),str(ideal),str(sources),str(zips)]
    i=[0]
    def f(mm):
        v=nums[i[0]] if i[0]<len(nums) else mm.group(1)
        i[0]+=1
        return f'<div class="num">{v}</div>'
    return re.sub(r'<div class="num">(\d+)</div>', f, h, count=4)
html=repl_stats(html)
open("index.html","w").write(html)
print("index.html rebuilt")
