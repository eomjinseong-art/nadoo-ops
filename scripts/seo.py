"""Monthly SEO check; opens an issue only when a site got worse vs the stored previous result."""
import datetime as dt, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
sys.path.insert(0, os.path.dirname(__file__))
import issues

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = json.load(open(os.path.join(ROOT, "sites.json")))
LATEST = os.path.join(ROOT, "data", "seo-latest.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; nadoo-ops-seo/1.0)"}
CHECKS = ["title", "description", "og:title", "og:image", "canonical", "lang", "robots_allow", "sitemap", "jsonld", "not_noindex"]

def fetch(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return r.status, r.geturl(), r.read(2_000_000).decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, url, "", dict(e.headers or {})
        except Exception as e:
            err = str(e); time.sleep(2)
    return None, url, err, {}

class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.m = {}; s.lang = None; s.canon = None; s.title = ""; s._t = False; s.jsonld = False
    def handle_starttag(s, tag, a):
        a = dict(a)
        if tag == "html": s.lang = a.get("lang")
        elif tag == "title": s._t = True
        elif tag == "meta":
            k = (a.get("name") or a.get("property") or "").lower()
            if k: s.m.setdefault(k, a.get("content") or "")
        elif tag == "link" and "canonical" in (a.get("rel") or "").lower(): s.canon = a.get("href")
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json": s.jsonld = True
    def handle_endtag(s, tag):
        if tag == "title": s._t = False
    def handle_data(s, d):
        if s._t: s.title += d

def robots_allows(txt):
    agent, block = None, False
    for line in txt.splitlines():
        line = line.split("#")[0].strip()
        if ":" not in line: continue
        k, v = [x.strip() for x in line.split(":", 1)]
        k = k.lower()
        if k == "user-agent": agent = v
        elif k == "disallow" and agent == "*" and v == "/": block = True
    return not block

def check(site):
    url = site["url"]
    st, final, body, hdr = fetch(url + "/")
    r = {"url": url, "status": st}
    if st != 200:
        r["up"] = False; return r
    p = P(); p.feed(body)
    robots_meta = (p.m.get("robots", "") + " " + str(hdr.get("X-Robots-Tag", ""))).lower()
    rs, _, rtxt, _ = fetch(url + "/robots.txt")
    sm_url = url + "/sitemap.xml"
    if rs == 200:
        m = re.search(r"(?im)^sitemap:\s*(\S+)", rtxt)
        if m: sm_url = m.group(1)
    ss, _, stxt, _ = fetch(sm_url)
    r.update({"up": True, "final_url": final, "title": p.title.strip()[:200],
              "description": (p.m.get("description") or "")[:300], "og:title": p.m.get("og:title"),
              "og:image": p.m.get("og:image"), "canonical": p.canon, "lang": p.lang})
    r["checks"] = {"title": bool(p.title.strip()), "description": bool(p.m.get("description")),
                   "og:title": bool(p.m.get("og:title")), "og:image": bool(p.m.get("og:image")),
                   "canonical": bool(p.canon), "lang": bool(p.lang),
                   "robots_allow": rs != 200 or robots_allows(rtxt),
                   "sitemap": ss == 200 and ("<urlset" in stxt or "<sitemapindex" in stxt),
                   "jsonld": p.jsonld, "not_noindex": "noindex" not in robots_meta}
    r["score"] = sum(r["checks"].values())
    return r

with ThreadPoolExecutor(8) as ex:
    results = list(ex.map(check, SITES))
prev = {}
if os.path.exists(LATEST):
    prev = {s["url"]: s for s in json.load(open(LATEST))["sites"]}
problems = {}
for r in results:
    o = prev.get(r["url"])
    if not o: continue
    if o.get("up") and not r["up"]:
        problems[f"[seo] Site down: {r['url']}"] = f"Homepage returned {r['status']} (was 200 last month)."
    elif r["up"] and o.get("up"):
        lost = [c for c in CHECKS if o["checks"].get(c) and not r["checks"].get(c)]
        if lost:
            problems[f"[seo] Regression: {r['url']}"] = "Checks that passed last month but fail now: " + ", ".join(f"`{c}`" for c in lost)
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="minutes")
os.makedirs(os.path.dirname(LATEST), exist_ok=True)
out = {"checked_at": now, "sites": results}
json.dump(out, open(LATEST, "w"), indent=1, ensure_ascii=False)
json.dump(out, open(os.path.join(ROOT, "data", f"seo-{now[:7]}.json"), "w"), indent=1, ensure_ascii=False)
for r in results: print(r["url"], r["status"], r.get("score"))
print("problems:", list(problems))
# only open/comment for worse-than-before; close prior seo issues whose site is now fine
issues.sync("seo", problems)
