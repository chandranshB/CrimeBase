"""Archive government crime-data documents (live or since removed) via the Wayback CDX index, growing a little every run.
Never redundant: a capture is downloaded only if its content digest is new. If the same bytes live under another URL we just
record that URL against the existing file; if a URL's content changed over time, each distinct version is kept.
manifest.csv is the provenance ledger: url, file, sha256, wayback_timestamp, digest, publisher, retrieved (live.py rows only)."""
import csv, glob, hashlib, json, os, re, time, requests
from datetime import date
from urllib.parse import urlparse
from sources import ARCHIVE, wanted, publisher

EXT = r".*\.(pdf|xlsx?|csv|zip|docx?)$"
SKIP = re.compile(r"RFP|CCTNS|TRAINING|AIPDM|tender|NIT_|Annexure|Quiz", re.I)  # procurement/training noise, not crime data
DELAY, BUDGET, MAX_BYTES = 4, int(os.getenv("BUDGET", 3 * 3600)), 200e6  # ~15 req/min is Wayback's published guideline
OUT = "data/raw"
HEAD = ["url", "file", "sha256", "wayback_timestamp", "digest", "publisher", "retrieved"]
S = requests.Session()
S.headers["User-Agent"] = "CrimeBase-archiver (public-data research; github.com/chandranshB/CrimeBase)"

class Manifest:
    """Provenance ledger shared by scrape.py (Wayback) and live.py (today's sites). Rows are flushed one by one, so a killed run loses nothing."""
    def __init__(self):
        os.makedirs(OUT, exist_ok=True)
        for t in glob.glob(f"{OUT}/*.tmp"): os.remove(t)  # half-written leftovers from a killed run
        mf = f"{OUT}/manifest.csv"
        old = list(csv.DictReader(open(mf, newline=""))) if os.path.exists(mf) else []
        with open(mf + ".tmp", "w", newline="") as f:  # rewritten so manifests from older versions gain new columns
            w = csv.DictWriter(f, HEAD, extrasaction="ignore", restval=""); w.writeheader(); w.writerows(old)
        os.replace(mf + ".tmp", mf)
        self.f = open(mf, "a", newline=""); self.w = csv.DictWriter(self.f, HEAD, extrasaction="ignore", restval="")
        self.seen = {(r["url"], r.get("digest", "")) for r in old}      # this exact capture is already recorded
        self.by_digest = {r["digest"]: r for r in old if r.get("digest")}  # same bytes already stored under some URL

    def _row(self, url, digest, ts, file, sha):
        row = dict(url=url, file=file, sha256=sha, wayback_timestamp=ts, digest=digest, publisher=publisher(url), retrieved="" if ts else date.today().isoformat())
        self.w.writerow(row); self.f.flush(); self.seen.add((url, digest)); self.by_digest.setdefault(digest, row)

    def link(self, url, digest, ts):
        """Record `url` against bytes we already hold (no download). False if those bytes are unknown."""
        r = self.by_digest.get(digest)
        if r: self._row(url, digest, ts, r["file"], r["sha256"])
        return bool(r)

    def put(self, url, digest, ts, content):
        sha = hashlib.sha256(content).hexdigest()
        name = sha[:16] + "." + urlparse(url).path.rsplit(".", 1)[-1].lower()
        if not os.path.exists(f"{OUT}/{name}"):
            open(f"{OUT}/{name}.tmp", "wb").write(content); os.replace(f"{OUT}/{name}.tmp", f"{OUT}/{name}")  # atomic: never a truncated file
        self._row(url, digest, ts, name, sha); print(name, flush=True)

def get(url, deadline=float("inf"), **kw):
    for i in range(4):
        if time.time() > deadline: return None
        time.sleep(DELAY)
        try:
            r = S.get(url, timeout=300, **kw)
            if r.status_code == 200: return r
            if r.status_code in (404, 403): return None
        except requests.RequestException: pass
        time.sleep(20 * 2 ** i)  # 429/5xx/network: back off
    return None

LOST = f"{OUT}/lost.json"  # {file: date}: sources that no longer serve those bytes; not retried every run

def repair(deadline):
    """Re-fetch stored files that are missing (a store rebuilt from its manifest alone, or a file lost): same URL, same capture, and the bytes must hash to the
    SHA-256 the manifest recorded, so a repaired file is identical to the original or not kept at all. Spreadsheets first: they become facts."""
    mf = f"{OUT}/manifest.csv"
    if not os.path.exists(mf): return
    lost = json.load(open(LOST)) if os.path.exists(LOST) else {}
    want = {}
    for r in csv.DictReader(open(mf, newline="")):
        f = r["file"]
        if f and f not in lost and not os.path.exists(f"{OUT}/{f}") and (f not in want or (r["wayback_timestamp"] and not want[f]["wayback_timestamp"])): want[f] = r  # prefer a Wayback capture
    todo = sorted(want.values(), key=lambda r: (not re.search(r"\.xlsx?$", r["file"]), r["file"]))
    print(f"{len(todo)} stored files are missing; re-fetching them from their recorded sources", flush=True)
    trouble = 0
    for r in todo:
        if time.time() > deadline or trouble >= 3: return print("repair paused (time budget or the source is struggling); next run resumes")
        url = f"https://web.archive.org/web/{r['wayback_timestamp']}id_/{r['url']}" if r["wayback_timestamp"] else r["url"]
        for i in range(3):
            time.sleep(DELAY)
            try: resp = S.get(url, timeout=300); code = resp.status_code
            except requests.RequestException: resp, code = None, 0
            if code in (200, 403, 404, 410): break
            time.sleep(20 * 2 ** i)  # 429 / 5xx / network: back off
        if code == 200 and hashlib.sha256(resp.content).hexdigest() == r["sha256"]:
            open(f"{OUT}/{r['file']}.tmp", "wb").write(resp.content); os.replace(f"{OUT}/{r['file']}.tmp", f"{OUT}/{r['file']}"); trouble = 0; print("repaired", r["file"], flush=True)
        elif code in (200, 403, 404, 410):  # gone, or different bytes now: remember, don't ask again every run
            lost[r["file"]] = date.today().isoformat(); json.dump(lost, open(LOST, "w")); trouble = 0
        else: trouble += 1

def main():
    m, deadline, down = Manifest(), time.time() + BUDGET, 0
    repair(deadline)
    for host, (_, restrict) in ARCHIVE.items():
        if down >= 2: return print("Wayback unreachable twice in a row; leaving the rest to the next run")
        r = get("https://web.archive.org/cdx/search/cdx", deadline, params={
            "url": host, "matchType": "domain", "output": "json", "collapse": "digest", "fl": "timestamp,original,digest,length",
            "filter": ["statuscode:200", "original:" + EXT]})
        try: rows = r.json()[1:]
        except (AttributeError, ValueError): rows = []; down += 1; print("no CDX answer for", host); continue
        down = 0
        caps = [c for c in rows if not SKIP.search(c[1]) and (not restrict or wanted(c[1]))]
        caps.sort(key=lambda c: (not re.search(r"\.(xlsx?|csv)$", c[1], re.I), c[0]))  # spreadsheets first: they become clean data
        for ts, url, dig, length in caps:
            if (url, dig) in m.seen or m.link(url, dig, ts): continue
            if time.time() > deadline: return print("time budget hit; next run resumes")
            if length.isdigit() and int(length) > MAX_BYTES: continue
            f = get(f"https://web.archive.org/web/{ts}id_/{url}", deadline)
            if f: m.put(url, dig, ts, f.content)

if __name__ == "__main__": main()
