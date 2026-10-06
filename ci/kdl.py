"""Download every file of a Kaggle dataset into one flat folder, a few at a time, in one process: the CLI pays seconds of start-up per file (1,600 files took
over 40 minutes), and the whole-dataset download is unreliable. Files already present are skipped, so a retry resumes. Kaggle answers HTTP 429 when asked
too fast, so that is backed off hard instead of counted as a failure.
usage: kdl.py <owner/slug> <dir> [file name to skip ... | +file name to fetch (then only the +names are fetched)]"""
import concurrent.futures as cf, contextlib, io, os, sys, time
from kaggle.api.kaggle_api_extended import KaggleApi

THREADS = int(os.getenv("KDL_THREADS", 5))

def main(ds, out, *skip):
    api = KaggleApi(); api.authenticate()
    os.makedirs(out, exist_ok=True)
    names, tok = [], None
    while True:
        r = api.dataset_list_files(ds, page_token=tok, page_size=200)
        if r.error_message: sys.exit(r.error_message)
        names += [f.name for f in r.files]
        tok = r.next_page_token
        if not tok: break
    only = {a[1:] for a in skip if a.startswith("+")}
    names = [n for n in names if (os.path.basename(n) in only if only else os.path.basename(n) not in skip)]
    print(f"downloading {len(names)} files from {ds} with {THREADS} threads", flush=True)
    def get(n):
        err, tries, waits = None, 0, 0
        while tries < 4 and waits < 20:
            try: api.dataset_download_file(ds, n, out); return None  # saved as <dir>/<basename>
            except Exception as e:
                err = e
                if "429" in str(e): waits += 1; time.sleep(60)  # rate limited: wait it out (up to 20 min), this is not the file's fault
                else: tries += 1; time.sleep(5 * tries)
        return f"{n}: {type(err).__name__} {err}"
    with contextlib.redirect_stdout(io.StringIO()), cf.ThreadPoolExecutor(THREADS) as ex: bad = [b for b in ex.map(get, names) if b]  # the client prints a URL line per file
    if bad: sys.exit(f"{len(bad)} of {len(names)} files failed, e.g. {bad[0]}")
    print("done", flush=True)

if __name__ == "__main__": main(*sys.argv[1:])
