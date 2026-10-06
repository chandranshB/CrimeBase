"""Kaggle's create/version call times out when a dataset has ~1,600 files, so the raw store travels as 16 zips (by first hex char of the file name).
usage: bundle.py pack <raw_dir> <out_dir> | unpack <dir> | verify <dir>   (unpack extracts bundles into <dir> and removes them; verify fails if manifest.csv names a missing file)"""
import csv, json, sys, zipfile, shutil
from pathlib import Path

def pack(src, out):
    src, out = Path(src), Path(out); out.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.suffix == ".csv" or f.suffix == ".json": shutil.copy(f, out / f.name)  # manifest.csv, live_state.json stay plain
    for c in "0123456789abcdef":
        fs = sorted(f for f in src.iterdir() if f.is_file() and f.name[0] == c and f.suffix not in (".csv", ".json"))
        if fs:
            with zipfile.ZipFile(out / f"raw-{c}.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for f in fs: z.write(f, f.name)

def unpack(d):
    for z in sorted(Path(d).glob("raw-*.zip")):
        zipfile.ZipFile(z).extractall(d); z.unlink()

def verify(d):
    lost = set(json.load(open(Path(d) / "lost.json"))) if (Path(d) / "lost.json").exists() else set()  # sources that no longer serve those bytes
    names = {r["file"] for r in csv.DictReader(open(Path(d) / "manifest.csv", newline=""))} - lost
    missing = sorted(n for n in names if not (Path(d) / n).exists())
    print(f"{len(names) - len(missing)}/{len(names)} manifest files present")
    if missing: sys.exit(f"missing {len(missing)} files, e.g. {missing[:3]}")

if __name__ == "__main__":
    {"pack": lambda: pack(*sys.argv[2:4]), "unpack": lambda: unpack(sys.argv[2]), "verify": lambda: verify(sys.argv[2])}[sys.argv[1]]()
