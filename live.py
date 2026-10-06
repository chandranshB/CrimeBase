"""Crawl today's government sites for crime-data files, so everything currently published is captured, not just what the Wayback Machine holds.
Polite: honours robots.txt, one request per DELAY seconds, identifies itself, stays on registered hosts (sources.ARCHIVE), conditional GETs
(ETag / Last-Modified) for files seen before, per-host page cap. Files go through the same content-addressed store and manifest as scrape.py."""
import hashlib, heapq, json, os, re, time, requests
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser
from scrape import S, Manifest, SKIP, MAX_BYTES, OUT
from sources import ARCHIVE, wanted, site

BUDGET, PAGES, DEPTH, DELAY = int(os.getenv("LIVE_BUDGET", 2400)), int(os.getenv("LIVE_PAGES", 150)), 5, 2
FILE = re.compile(r"\.(pdf|xlsx?|csv|zip|docx?)$", re.I)
JUNK = re.compile(r"\.(jpe?g|png|gif|svg|ico|css|js|mp[34]|avi|mov|woff2?|ttf|xml|json|rss|ppt|pptx)$", re.I)
LINK = re.compile(r"""(?:href|src)\s*=\s*["']([^"'#\s][^"']*)""", re.I)
ROBOTS, STATE = {}, f"{OUT}/live_state.json"

def robots_ok(url):
    host = urlparse(url).netloc
    if host not in ROBOTS:
        rp = RobotFileParser()
        try:
            r = S.get(f"https://{host}/robots.txt", timeout=20)
            if r.status_code == 200: rp.parse(r.text.splitlines())
            elif r.status_code >= 500: rp.disallow_all = True  # RFC 9309: server error -> assume off limits for now
            else: rp.allow_all = True                         # RFC 9309: robots.txt absent/4xx -> no rules
        except requests.RequestException: rp.disallow_all = True
        ROBOTS[host] = rp
        if not rp.can_fetch(S.headers["User-Agent"], f"https://{host}/"): print(f"{host}: robots.txt forbids crawling; skipped (Wayback still covers it)", flush=True)
    return ROBOTS[host].can_fetch(S.headers["User-Agent"], url)

def fetch(url, **kw):
    if not robots_ok(url): return None
    for i in range(2):
        time.sleep(DELAY)
        try:
            r = S.get(url, timeout=(15, 120), stream=True, **kw)
            if r.status_code in (200, 304) or r.status_code < 500 and r.status_code != 429: return r
        except requests.RequestException as e: print("skip", url, type(e).__name__)
        time.sleep(30)

def take(url, m, st):
    """Download one file if it changed since last run; returns True on a clean fetch."""
    old = st.get(url, {})
    h = {k: old[v] for k, v in (("If-None-Match", "etag"), ("If-Modified-Since", "lm")) if old.get(v)}
    r = fetch(url, headers=h)
    if r is None: return False
    if r.status_code != 200 or int(r.headers.get("content-length", 0)) > MAX_BYTES or "text/html" in r.headers.get("content-type", ""): r.close(); return r.status_code == 304
    body = r.content
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    st[url] = {"etag": r.headers.get("etag"), "lm": r.headers.get("last-modified")}
    if (url, digest) not in m.seen and not m.link(url, digest, ""): m.put(url, digest, "", body)
    return True

def crawl(host, m, st, deadline):
    pub, restrict = ARCHIVE[host]
    q, queued, pages, fails = [(-1, 0, u) for u in st if site(u) == ARCHIVE[host]] + [(0, 0, f"https://{host}/")], set(st), 0, 0
    heapq.heapify(q)
    while q and time.time() < deadline and pages < PAGES and fails < 3:
        _, d, url = heapq.heappop(q)
        if FILE.search(urlparse(url).path):
            fails = 0 if take(url, m, st) else fails + 1; continue
        r = fetch(url)
        if r is None or r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            if r is not None: r.close()
            fails += r is None; continue
        fails, pages = 0, pages + 1
        try: html = r.text
        except requests.RequestException: continue
        for l in LINK.findall(html):
            u = urldefrag(urljoin(r.url, l.strip()))[0]
            s = site(u) if u.startswith("http") else None
            if not s or u in queued or JUNK.search(urlparse(u).path): continue
            if FILE.search(urlparse(u).path):
                if SKIP.search(u) or (s[1] and not wanted(u)): continue
                heapq.heappush(q, (-1, 0, u))
            elif d < DEPTH: heapq.heappush(q, (1 if wanted(u) else 2, d + 1, u))
            queued.add(u)
    print(f"{host}: {pages} pages, queue left {len(q)}", flush=True)

def main():
    m = Manifest()
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    t0, hosts = time.time(), list(ARCHIVE)
    for i, host in enumerate(hosts):
        if host.startswith("xn--"): continue  # redirect target of mha.gov.in: registered so its links are accepted, already crawled via the alias
        try: crawl(host, m, st, time.time() + (BUDGET - (time.time() - t0)) / (len(hosts) - i))  # unused time rolls over to later hosts
        except Exception as e: print("crawl failed for", host, type(e).__name__, e)  # one bad site never stops the others
        json.dump(st, open(STATE + ".tmp", "w")); os.replace(STATE + ".tmp", STATE)

if __name__ == "__main__": main()
