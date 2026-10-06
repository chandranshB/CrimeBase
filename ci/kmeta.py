"""Kaggle listing metadata, from the templates in kaggle/. usage:
  kmeta.py prep   <template.json> <dir> <user>             write <dir>/dataset-metadata.json: owner filled in, only files present listed, column docs attached from kaggle/columns.py, cover image copied beside it
  kmeta.py apply  <dir>/dataset-metadata.json <server.json> copy the privacy flag and collaborators Kaggle holds into our file (exit 1 if unreadable, so a listing update can never flip privacy)
  kmeta.py kernel <dir> <user> <server.json>               write <dir>/kernel-metadata.json for the quick-start notebook; it is public only once its dataset is"""
import csv, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kaggle"))
from columns import COLUMNS

def names(path):
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        return pq.read_schema(path).names
    if path.suffix == ".csv":
        with open(path, newline="", encoding="utf-8") as f: return next(csv.reader(f), [])

def prep(tpl, d, user):
    d = Path(d); m = json.loads(Path(tpl).read_text(encoding="utf-8")); m["id"] = m["id"].replace("USER", user)
    cover = m.pop("cover", None)
    # a news run has no raw files, an early run has no documents.csv ...; a path with * stands for every matching file (raw-*.zip)
    m["resources"] = [{**r, "path": f.name} for r in m["resources"] for f in (sorted(d.glob(r["path"])) if "*" in r["path"] else [d / r["path"]]) if f.is_file()]
    listed = {r["path"] for r in m["resources"]}
    for r in m["resources"]:
        docs = {n: (t, x) for n, t, x in COLUMNS.get(r["path"], [])}
        cols = names(d / r["path"]) or []
        if cols and docs:
            for c in cols:
                if c not in docs: print(f"::warning::{r['path']}: column '{c}' has no description in kaggle/columns.py")
            r["schema"] = {"fields": [{"name": c, "description": docs[c][1] if c in docs else "", "type": docs[c][0] if c in docs else "string"} for c in cols]}
    for f in sorted(p.name for p in d.iterdir() if p.is_file() and p.name not in listed | {"dataset-metadata.json", "dataset-cover-image.png"}):
        print(f"::warning::{f} is in the dataset folder but has no description in {Path(tpl).name}")
    if cover: shutil.copy(cover, d / "dataset-cover-image.png")  # the name Kaggle looks for
    (d / "dataset-metadata.json").write_text(json.dumps(m, indent=1), encoding="utf-8")

def server(path):
    s = json.loads(Path(path).read_text(encoding="utf-8")); s = s.get("info", s)
    priv = s.get("isPrivate", s.get("is_private"))
    if priv is None and ("datasetSlug" in s or "datasetId" in s): priv = False  # Kaggle's JSON leaves out false values: a dataset record without the flag is public
    if not isinstance(priv, bool): sys.exit("cannot read the dataset's privacy from Kaggle; leaving its listing alone")
    return s, priv

def held(ref):
    """Names of the files Kaggle holds for a dataset (all pages)."""
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi(); api.authenticate(); names, tok = set(), None
    while True:
        r = api.dataset_list_files(ref, page_token=tok, page_size=200)
        names |= {f.name for f in r.files}; tok = r.next_page_token
        if not tok: return names

def apply(ours, srv):
    s, priv = server(srv); p = Path(ours); m = json.loads(p.read_text(encoding="utf-8"))
    m["isPrivate"] = priv; m["collaborators"] = s.get("collaborators") or []
    have = held(m["id"])  # Kaggle rejects the whole update if a listed file isn't in the dataset (raw-*.zip is unpacked into folders there)
    m["resources"] = [r for r in m["resources"] if r["path"] in have]
    p.write_text(json.dumps(m, indent=1), encoding="utf-8")

def kernel(d, user, srv):
    _, priv = server(srv); d = Path(d)
    (d / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/crimebase-quickstart", "title": "CrimeBase quickstart: India crime by state and year", "code_file": "crimebase-quickstart.ipynb", "language": "python",
        "kernel_type": "notebook", "is_private": str(priv).lower(), "enable_gpu": "false", "enable_internet": "false", "dataset_sources": [f"{user}/crimebase"],
        "competition_sources": [], "kernel_sources": []}, indent=1), encoding="utf-8")

if __name__ == "__main__":
    {"prep": prep, "apply": apply, "kernel": kernel}[sys.argv[1]](*sys.argv[2:])
