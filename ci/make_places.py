"""Build places.csv (place name -> state, with population) from GeoNames' India dump (CC BY 4.0, geonames.org). Run by hand when you want a refresh; the result is committed.
usage: make_places.py [IN.txt admin1CodesASCII.txt]   (downloaded from download.geonames.org/export/dump/ if not given)
Keeps towns and cities of 5,000+ people, every district and sub-district seat, and, for places of 50,000+, their alternative Latin spellings (Bombay, Madras, Gurgaon ...)."""
import csv, io, re, sys, urllib.request, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from taxonomy import norm, state_code

U = "https://download.geonames.org/export/dump/"
def fetch(name):
    return urllib.request.urlopen(U + name, timeout=300).read()

def main(places=None, admin1=None):
    if places: rows, a1 = open(places, encoding="utf-8"), open(admin1, encoding="utf-8").read()
    else: rows, a1 = io.TextIOWrapper(zipfile.ZipFile(io.BytesIO(fetch("IN.zip"))).open("IN.txt"), encoding="utf-8"), fetch("admin1CodesASCII.txt").decode("utf-8")
    st = {}
    for l in a1.splitlines():
        code, name = l.split("\t")[:2]
        if code.startswith("IN."): st[code[3:]] = state_code(name)
    out = {}  # (name, state) -> [population, kind]
    for r in csv.reader(rows, delimiter="\t", quoting=csv.QUOTE_NONE):
        _, name, ascii_, alts, _, _, fclass, fcode, _, _, a1c, *_rest = r[:11] + [""] * 8
        pop = int(r[14] or 0); s = st.get(a1c)
        if not s: continue
        district = fcode == "ADM2"
        seat = fcode in ("PPLA", "PPLA2", "PPLA3", "PPLC")
        if not (district or (fclass == "P" and (pop >= 5000 or seat))): continue
        names = {ascii_}
        if pop >= 50000 or district or seat: names |= {a for a in alts.split(",") if a.isascii() and re.fullmatch(r"[A-Za-z .'-]{4,}", a)}
        for n in names:
            t = n.split()
            if len(t) >= 3 and sum(map(len, t)) / len(t) < 3.2: continue  # pinyin-style transliterations ('A Bo He Er')
            k = norm(n)
            if len(k) < 4 and not seat and not district: continue  # 'Man', 'Bar': too many English words
            cur = out.setdefault((k, s), [0, 0, False])  # town population, district population, is a district
            cur[1 if district else 0] = max(cur[1 if district else 0], pop)
            cur[2] |= district
    with open(Path(__file__).resolve().parent.parent / "places.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["name", "state_code", "population", "kind"])
        for (k, s), (town, dist, is_dist) in sorted(out.items()): w.writerow([k, s, town or dist, "district" if is_dist else "city"])  # size of the town itself when known: a district's population says little about which Aurangabad is meant
    print(len(out), "place names")

if __name__ == "__main__": main(*sys.argv[1:])
