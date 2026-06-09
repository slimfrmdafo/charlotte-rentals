#!/usr/bin/env python3
"""Fresh scrape (2026-06-09 refresh) of curl-friendly Charlotte rental sources.
Targets budget overlap with $1,400-$1,900/mo. Emits per-source JSON in unified schema.
"""
import re, json, subprocess, time, html as htmllib

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
LO, HI = 1400, 1900

def curl(url, extra=None):
    cmd = ["curl", "-sL", "--compressed", "-A", UA, "--max-time", "40"]
    if extra: cmd += extra
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def in_budget(plo, phi):
    if not plo and not phi: return False
    lo = plo or phi; hi = phi or plo
    return lo <= HI and hi >= LO

def blank(**kw):
    base = dict(name="", address="", city="Charlotte", state="NC", zip="", neighborhood="",
                price_low=0, price_high=0, beds_low=0, beds_high=0, baths_low=0, baths_high=0,
                sqft_low=0, sqft_high=0, available_date="", property_type="apartment",
                url="", source="", special="", amenities=[])
    base.update(kw); return base

# ---------------- rent.com ----------------
def scrape_rentcom():
    out = {}
    bases = [
        "https://www.rent.com/north-carolina/charlotte-apartments/min-price-1400_max-price-1900",
        "https://www.rent.com/north-carolina/charlotte-houses/min-price-1400_max-price-1900",
        "https://www.rent.com/north-carolina/charlotte-townhomes/min-price-1400_max-price-1900",
    ]
    for base in bases:
        for page in range(1, 7):
            url = base if page == 1 else f"{base}?page={page}"
            doc = curl(url)
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', doc, re.S)
            if not m: break
            try:
                d = json.loads(m.group(1))
                L = d['props']['pageProps']['pageData']['location']['listingSearch']['listings']
            except Exception:
                break
            if not L: break
            for x in L:
                loc = x.get('location') or {}
                fps = x.get('floorPlans') or []
                prices = [p for fp in fps for p in (fp.get('priceRange') or {}).values() if p]
                if not prices:
                    prices = [p for b in (x.get('bedCountData') or []) for p in (b.get('prices') or {}).values() if p]
                if not prices: continue
                plo, phi = min(prices), max(prices)
                if not in_budget(plo, phi): continue
                beds = [fp.get('bedCount') for fp in fps if fp.get('bedCount') is not None] or \
                       [b.get('beds') for b in (x.get('bedCountData') or [])]
                baths = [fp.get('bathCount') for fp in fps if fp.get('bathCount') is not None]
                sqft = [s for fp in fps for s in (fp.get('sqFtRange') or {}).values() if s]
                avail = next((fp.get('availableDate') for fp in fps if fp.get('availableDate')), "")
                # move-in specials: dealTypes[].text are short badges, dealsText is the full blurb
                deal_types = [d.get('text', '').strip() for d in (x.get('dealTypes') or []) if d.get('text')]
                seen_dt, ordered = set(), []
                for t in deal_types:                       # dedup, keep order, concession badges first
                    if t.lower() not in seen_dt:
                        seen_dt.add(t.lower()); ordered.append(t)
                ordered.sort(key=lambda t: (t.lower() == 'lowered fees',))  # push generic "Lowered Fees" last
                special = " · ".join(ordered)[:80]
                if not special and (x.get('deals') or x.get('dealsText')):
                    special = "Specials"
                key = x.get('urlPathname') or x.get('name')
                out[key] = blank(
                    name=x.get('name', ''), zip=str(loc.get('zip') or ''),
                    price_low=plo, price_high=phi,
                    beds_low=min(beds) if beds else 0, beds_high=max(beds) if beds else 0,
                    baths_low=min(baths) if baths else 0, baths_high=max(baths) if baths else 0,
                    sqft_low=min(sqft) if sqft else 0, sqft_high=max(sqft) if sqft else 0,
                    available_date=avail or "", property_type="apartment",
                    url="https://www.rent.com" + (x.get('urlPathname') or ''),
                    source="rent.com", special=special)
            time.sleep(1.0)
    return list(out.values())

# ---------------- craigslist ----------------
def scrape_craigslist():
    out = {}
    for off in range(0, 300, 120):
        url = (f"https://charlotte.craigslist.org/search/apa?max_price={HI}&min_price={LO}"
               f"&availabilityMode=0#search=1~gallery~{off//120}~0")
        doc = curl(url)
        # craigslist embeds results in a JSON blob in newer markup
        for m in re.finditer(r'<a[^>]+class="[^"]*cl-app-anchor[^"]*"[^>]+href="(https://[^"]+\.html)"[^>]*>.*?<span class="label">(.*?)</span>', doc, re.S):
            pass
        # fallback: parse the data-id anchors + titles + prices via the gallery card markup
        cards = re.findall(r'<li class="cl-static-search-result"[^>]*title="([^"]*)"[^>]*>(.*?)</li>', doc, re.S)
        for title, body in cards:
            href = re.search(r'href="(https://[^"]+\.html)"', body)
            price = re.search(r'\$([\d,]+)', body)
            if not href or not price: continue
            p = int(price.group(1).replace(',', ''))
            if not (LO <= p <= HI): continue
            beds = re.search(r'(\d+)br', body)
            out[href.group(1)] = blank(
                name=htmllib.unescape(title)[:90], price_low=p, price_high=p,
                beds_low=int(beds.group(1)) if beds else 0, beds_high=int(beds.group(1)) if beds else 0,
                property_type="Various", url=href.group(1), source="craigslist")
        time.sleep(1.0)
    return list(out.values())

# ---------------- redfin ----------------
def scrape_redfin():
    out = {}
    url = ("https://www.redfin.com/city/35915/NC/Charlotte/apartments-for-rent"
           "/filter/property-type=house+townhouse+condo+apartment,min-price=1.4k,max-price=1.9k")
    doc = curl(url)
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        items = j if isinstance(j, list) else [j]
        for it in items:
            if it.get('@type') not in ('Apartment', 'SingleFamilyResidence', 'House', 'Residence'):
                continue
            offers = it.get('offers') or {}
            p = offers.get('price') or offers.get('lowPrice')
            try: p = int(float(p))
            except Exception: continue
            if not in_budget(p, p): continue
            addr = it.get('address') or {}
            out[it.get('url', it.get('name'))] = blank(
                name=it.get('name', ''), address=addr.get('streetAddress', ''),
                zip=str(addr.get('postalCode') or ''), price_low=p, price_high=p,
                property_type="house", url=it.get('url', ''), source="redfin")
    return list(out.values())

if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    fns = {"rentcom": scrape_rentcom, "craigslist": scrape_craigslist, "redfin": scrape_redfin}
    targets = fns if which == "all" else {which: fns[which]}
    for name, fn in targets.items():
        rows = fn()
        json.dump(rows, open(f"fresh_{name}.json", "w"), indent=1)
        print(f"{name}: {len(rows)} listings -> fresh_{name}.json")
