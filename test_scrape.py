"""Offline check of repair(): a store rebuilt from its manifest gets its files back from the recorded sources, hash-verified; changed or gone sources are remembered."""
import csv, hashlib, json, os, tempfile
import scrape

d = tempfile.mkdtemp(); scrape.OUT, scrape.LOST = d, d + "/lost.json"; scrape.time.sleep = lambda s: None
good = b"hello"; sha = hashlib.sha256(good).hexdigest()
with open(d + "/manifest.csv", "w", newline="") as f:
    w = csv.DictWriter(f, scrape.HEAD); w.writeheader()
    for url, file, h, ts in (("http://a/x.xls", "g1.xls", sha, "2020"), ("http://a/y.xls", "g2.xls", sha, "2020"), ("http://a/z.xls", "g3.xls", sha, ""), ("http://a/w.xls", "g4.xls", sha, "2021")):
        w.writerow(dict(url=url, file=file, sha256=h, wayback_timestamp=ts, digest="", publisher="", retrieved=""))
calls = []
class R:
    def __init__(s, code, content=b""): s.status_code, s.content = code, content
def get(url, **kw):
    calls.append(url)
    return R(200, good) if "x.xls" in url else R(200, b"changed") if "y.xls" in url else R(404) if "z.xls" in url else R(200, good)
scrape.S.get = get
scrape.repair(float("inf"))
assert open(d + "/g1.xls", "rb").read() == good and os.path.exists(d + "/g4.xls")  # fetched from the Wayback capture and hash-checked
assert not os.path.exists(d + "/g2.xls") and not os.path.exists(d + "/g3.xls") and set(json.load(open(scrape.LOST))) == {"g2.xls", "g3.xls"}  # changed bytes / gone: kept out, remembered
assert any("web.archive.org/web/2020id_/http://a/x.xls" in c for c in calls)
n = len(calls); scrape.repair(float("inf")); assert len(calls) == n  # nothing missing, nothing remembered-as-lost is retried
print("OK")
