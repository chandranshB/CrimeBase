"""Refuse to publish a build that lost data: each table must keep at least GUARD (default 0.9) of the rows the previous build had.
A parser change that drops a table family, a restore that came back short, a half-finished parse: all show up as a shrink, and a bad run must never overwrite good data.
usage: guard.py <previous dir> <new dir>   (exit 1 on a shrink; GUARD=0 turns it off for a deliberate cut)"""
import os, sys

TABLES = ("crime_state_year.csv", "crime_india_year.csv", "facts.parquet", "documents.csv")

def rows(path):
    if not os.path.exists(path): return 0
    if path.endswith(".parquet"):
        import pyarrow.parquet as pq
        return pq.ParquetFile(path).metadata.num_rows
    with open(path, "rb") as f: return max(sum(1 for _ in f) - 1, 0)

def main(prev, new, keep=float(os.getenv("GUARD", 0.9))):
    bad = []
    for t in TABLES:
        a, b = rows(f"{prev}/{t}"), rows(f"{new}/{t}")
        print(f"{t}: {a:,} -> {b:,}")
        if a and b < keep * a: bad.append(t)
    if bad: sys.exit(f"refusing to publish: {', '.join(bad)} shrank by more than {1 - keep:.0%} (GUARD=0 to override)")

if __name__ == "__main__": main(*sys.argv[1:3])
