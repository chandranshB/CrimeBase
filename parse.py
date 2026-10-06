"""Turn every NCRB xls/xlsx table in data/raw into one tidy long table: data/clean/facts.parquet (+ qc/conflict reports)."""
import csv, functools, os, re, sys, time, warnings
import numpy as np
import pandas as pd
from urllib.parse import unquote
from sources import publisher
from taxonomy import state_code, crime_category, metric, victim_group, write_reference, place_state, place_unique, states_in
from panel import build as build_panel

warnings.filterwarnings("ignore")
ENTITY = re.compile(r"^(state(s)?(\s*/\s*uts?)?|state or ut|district|city|cities|crime\s*heads?|crime/head|head of crime|crime)$", re.I)
COLYEAR = re.compile(r"^\s*((?:19|20)\d\d)(?:\.0)?\s*[$*#@]*\s*$")
SL = re.compile(r"^(sl|s\.?\s*no\.?|sno|sl\.?\s*no\.?|sr\.?\s*no\.?)$", re.I)
IDX = re.compile(r"^[\[(]\d+[\])]$")
SEP = " | "  # header-level joiner: one level per header row
PARSER_VERSION = 12  # bump when spreadsheet parsing changes so cached rows are rebuilt
PDF_VERSION = 12  # same for PDFs, which are slow to parse: bumping PARSER_VERSION alone keeps their cached rows
YEAR = re.compile(r"(?<!\d)(19[5-9]\d|20[0-3]\d)(?!\d)")

def clean(s): return re.sub(r"\s+", " ", str(s)).strip()
def num(x):
    try: return float(str(x).replace(",", "").strip())
    except ValueError: return None
def is_num(x): return not isinstance(x, bool) and num(x) is not None and str(x).strip() not in ("", "nan")

def is_ent(df, r, c):
    """True if cell (r, c) heads an entity column: a known header word, or any label right after an 'SL' cell."""
    v = df.iat[r, c]
    if not isinstance(v, str) or len(v) > 60 or IDX.match(v.strip()): return False
    return bool(ENTITY.search(v.strip())) or (c > 0 and isinstance(df.iat[r, c - 1], str) and bool(SL.match(df.iat[r, c - 1].strip())))

def blocks(df, merged=False):
    """Yield (title, entity_col, {col: label}, data_rows, sub_df) per header+data block; side-by-side blocks are split on repeated entity columns."""
    pos, n = 0, len(df)
    while pos < n:
        r0 = next((r for r in range(pos, n) if any(is_ent(df, r, c) for c in range(df.shape[1]))), None)
        if r0 is None: return
        ents = [c for c in range(df.shape[1]) if is_ent(df, r0, c)]
        end = pos
        for i, c0 in enumerate(ents):
            sub = df.iloc[:, c0:(ents[i + 1] if i + 1 < len(ents) else df.shape[1])]
            sub.columns = range(sub.shape[1])
            got = _block(sub, pos, r0, df.iloc[:, :c0] if i == 0 else None, [is_ent(df, r, c0) for r in range(n)], merged)
            if got: yield (*got, df.iat[r0, c0]); end = max(end, got[3][-1] + 1)
        pos = max(end, r0 + 1)

END = re.compile(r"total\b", re.I)
NOTE = re.compile(r"(source|note)\b|\*", re.I)  # footnote strips that sit between stacked tables
YEARCELL = re.compile(r"^(?:19|20)\d\d$")

def cell_text(v):
    """Header cell -> text; numbers survive only as years (other numbers are column-index rows)."""
    if isinstance(v, str): return clean(v) or None
    if isinstance(v, (int, float)) and not isinstance(v, bool) and not pd.isna(v) and float(v).is_integer() and 1950 <= v <= 2035: return str(int(v))
    return None

def col_year(lab):
    return next((int(m[1]) for seg in reversed(lab.split(" | ")) if (m := COLYEAR.match(seg))), None)

def _block(df, pos, r0, lead=None, hdrrow=None, merged=False):
    n, vals = len(df), list(range(1, df.shape[1]))
    cells = (clean(v) for r in range(max(pos, r0 - 4), r0) for v in (list(df.iloc[r]) + ([] if lead is None else list(lead.iloc[r]))) if isinstance(v, str))
    title = " ".join(dict.fromkeys(c for c in cells if len(c) > 4 and not NOTE.match(c)))[:400]  # merged title cells repeat across the row; keep each once
    def datarow(r):
        e = df.iat[r, 0]
        return isinstance(e, str) and not IDX.match(e.strip()) and not hdrrow[r] and sum(is_num(df.iat[r, c]) for c in vals) >= max(1, 0.3 * len(vals))
    first = next((r for r in range(r0 + 1, n) if datarow(r)), None)
    if first is None or not vals: return None
    def banner(r):  # a merged title strip repeating one text across the row, e.g. 'State: Kerala'
        t = [clean(v) for v in df.iloc[r] if isinstance(v, str) and clean(v)]
        return len(t) >= 3 and len(set(t)) == 1
    hdr = [r for r in range(r0, first) if sum(bool(IDX.match(str(v).strip())) for v in df.iloc[r]) < 2 and not banner(r)]
    # year strips sit *above* the 'SL | State' row in some sheets (2010 | 2011 | ...): pull in non-title rows just above it
    up = [r for r in range(max(pos, r0 - 3), r0) if not banner(r) and any(cell_text(df.iat[r, c]) for c in vals) and all(len(clean(v)) < 80 for v in df.iloc[r] if isinstance(v, str))]
    hdr = up + hdr
    grid = {}
    for r in hdr:
        t = {c: cell_text(df.iat[r, c]) for c in vals}
        if r != hdr[-1] and (not merged or all(YEARCELL.match(x) for x in t.values() if x)):  # spanning header cell: carry it rightwards
            last = None
            for c in vals:
                if t[c]: last = t[c]
                else: t[c] = last
        grid[r] = t
    labels = {}
    for c in vals:
        parts = []
        for r in hdr:
            v = grid[r][c]
            if v and (not parts or parts[-1] != v): parts.append(v)
        labels[c] = SEP.join(parts)
    rows, ctx, cur = [], {}, None
    for r in range(max(pos, r0 - 3), n):
        t = str(df.iat[r, 0]).strip()
        m = re.match(r"state\s*:\s*(.+)", t, re.I)
        cur = state_code(m[1]) if m else state_code(t, False) or cur  # 'State: X' banners and bare state-name rows head their districts
        if r < first: continue
        if datarow(r):
            rows.append(r); ctx[r] = cur
            if END.match(t): cur = None  # a 'Total' row closes its state's block: the next rows belong to a state this sheet has not named
        elif hdrrow[r]: break
    return title, 0, labels, rows, df, ctx

RANGE = re.compile(r"(?:19|20)\d\d\s*[-_]\s*(?:19|20)?\d\d(?!\d)")  # '2001-12', '2010-2015'

def file_year(url):
    """The one year a spreadsheet's file name carries ('1 Districtwise IPC Crimes_2021.xlsx'), else None. NCRB copies last year's sheet title into the new file
    ('...Crimes_2021.xlsx' is headed '2020', '...Crimes - 2018.xlsx' is headed '2017'; the all-India totals confirm the file name), so the file name outranks the title."""
    name = RANGE.sub(" ", unquote(url.rsplit("/", 1)[-1]))
    m = set(YEAR.findall(name))
    return int(m.pop()) if len(m) == 1 and url.lower().endswith((".xls", ".xlsx")) else None

def pub_year(path, title, sheet):
    """The file name's year, else the first of sheet / title / path naming exactly one year; ranges ('2001-2015') are ambiguous so they're skipped.
    The path is unquoted first: the '%20' + '11.6' of 'TABLE%2011.6.xlsx' is not 2011."""
    if fy := file_year(path): return fy, "path"
    for src, s in (("sheet", sheet), ("title", title), ("path", unquote(path))):
        m = set(YEAR.findall(s))
        if len(m) == 1: return int(m.pop()), src
    return None, None

def fix_years(df):
    """Rows parsed before that rule: a year taken from a title or sheet gives way to the file name's; a year taken from a mis-decoded path is recomputed."""
    cats = list(df.source_url.cat.categories)
    codes = df.source_url.cat.codes.to_numpy()
    fy = np.array([file_year(u) or np.nan for u in cats] + [np.nan])[codes]  # code -1 (no URL) lands on the trailing nan
    py = np.array([pub_year(u, "", "")[0] or np.nan for u in cats] + [np.nan])[codes]
    ys = df.year_source.astype(object)
    swap = ys.isin(["title", "sheet"]).to_numpy() & (df.format == "xls").to_numpy() & ~np.isnan(fy) & (fy != df.year.to_numpy())
    path = (ys == "path").to_numpy() & (py != df.year.to_numpy()) & ~swap
    df["year"] = np.where(swap, fy, np.where(path, py, df.year.to_numpy()))
    if swap.any():
        df["year_source"] = df.year_source.cat.add_categories([c for c in ["path"] if c not in df.year_source.cat.categories])
        df.loc[swap, "year_source"] = "path"
    df.loc[path & np.isnan(py), "year_source"] = None
    absurd = ((df.year < 1950) | (df.year > 2030)).to_numpy()  # a figure in a header cell read as a year ('2082')
    df.loc[absurd, "year"] = np.nan
    df.loc[absurd, "year_source"] = None
    print(f"years: {swap.sum():,} facts took the file name's year over the title's, {path.sum():,} path years recomputed", flush=True)
    return df

@functools.lru_cache(maxsize=1)
def _wb(path):
    if path.endswith("x"):
        import openpyxl
        return openpyxl.load_workbook(path, read_only=False)
    import xlrd
    return xlrd.open_workbook(path, formatting_info=True)

def merges(path, sheet):
    """Merged ranges (r0, r1, c0, c1), 0-based inclusive, or None if unavailable."""
    try:
        if path.endswith("x"):
            ws = _wb(path)[sheet]
            return [(m.min_row - 1, m.max_row - 1, m.min_col - 1, m.max_col - 1) for m in ws.merged_cells.ranges]
        import xlrd
        return [(a, b - 1, c, d - 1) for a, b, c, d in _wb(path).sheet_by_name(sheet).merged_cells]
    except Exception: return None

def fill_merges(df, mr):
    for r0, r1, c0, c1 in mr or []:
        if r0 < df.shape[0] and c0 < df.shape[1] and (r1 > r0 or c1 > c0):
            v = df.iat[r0, c0]
            if isinstance(v, str): df.iloc[r0:r1 + 1, c0:c1 + 1] = v
    return df

VAL = r"(?:-?\d[\d,]*(?:\.\d+)?|-{1,2}|\*+|NA|N\.A\.?|NIL)"  # a figure, or the dash / NA a table prints for 'none'
PDF_ROW = re.compile(rf"^(?:(\d{{1,3}})\s+)?([^\d\s][^\d]*?)\s+({VAL}(?:\s+{VAL})+)\s*$", re.I)  # 'serial  name  fig fig fig ...'
PDF_COLNO = re.compile(r"\(?\d{1,3}\)?")  # the strip of column numbers under the header: 1 2 3 4 ...

def pdf_page(pg, text=None):
    """(header rows, data rows) of one PDF page. NCRB's PDFs are text: the grid gives the header (one row per level), but it folds every data row into one cell, so the
    rows are read from the text lines instead ('12 Kerala 9767 10034 11057 ...') and kept only if their count of figures fits the header. None for any other page."""
    tabs = pg.extract_tables() or []
    if not tabs: return None
    hdr = []
    for r in tabs[0]:
        cells = [" ".join((c or "").split()) or None for c in r]
        full = [c for c in cells if c]
        if len(full) == 1 and len(full[0]) > 25: break  # the data rows, folded into one cell
        if sum(bool(PDF_COLNO.fullmatch(c)) for c in full) >= max(3, 0.6 * len(full)): continue
        if len(full) >= 4 and sum(bool(re.fullmatch(VAL, c)) and not YEARCELL.match(c) for c in full) > 0.5 * len(full): break  # figures: the grid did not fold this page's rows, so its header ends here
        hdr.append(cells)
    text = pg.extract_text() or "" if text is None else text
    data = [(m[1], m[2].strip(), re.findall(VAL, m[3], re.I)) for m in map(PDF_ROW.match, (l.strip() for l in text.splitlines())) if m]
    if not hdr or not data: return None
    k = pd.Series([len(d[2]) for d in data]).mode().iat[0]  # figures per row
    keep = [j for j in range(max(len(h) for h in hdr)) if any(j < len(h) and h[j] for h in hdr)]  # a grid with merged header cells is wider than its table: columns with no text are spans' leftovers
    hdr = [[h[j] if j < len(h) else None for j in keep] for h in hdr]
    w = len(keep)
    if w not in (k + 1, k + 2): return None  # serial + name + k figures, or name + k figures
    return hdr, [([sn] if w == k + 2 else []) + [name] + vals for sn, name, vals in data if len(vals) == k]

def pdf_frames(path, max_pages=40):
    """One frame per PDF: each table page's title row, header rows and data rows, the same shape as a spreadsheet. A page that is not such a table yields nothing."""
    import pdfplumber
    rows = []
    with pdfplumber.open(path) as p:
        if len(p.pages) > max_pages: return {}
        for pg in p.pages:
            text = pg.extract_text() or ""
            got = pdf_page(pg, text)
            if not got: continue
            head = []
            for l in text.splitlines()[:4]:  # the title ends at the first line that carries a year ('... - 2017'); what follows is column headings
                if len(l) > 4: head.append(l)
                if YEAR.search(l) and not re.fullmatch(r"TABLE [\w.() ]+", l.strip(), re.I): break
            rows.append([" ".join(head)]); rows += got[0]; rows += got[1]
    w = max((len(r) for r in rows), default=0)
    return {"pdf": pd.DataFrame([r + [None] * (w - len(r)) for r in rows], dtype=object)} if w else {}

def _parse_file(path, url, ts=""):
    name, out, pdf = os.path.basename(path), [], path.lower().endswith(".pdf")
    try: sheets = pdf_frames(path) if pdf else pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    except Exception as e: print("skip", name, type(e).__name__, file=sys.stderr); return out
    named = [k for k in sheets if not re.fullmatch(r"Sheet\d+", str(k))]  # 'SheetN' tabs are flat re-exports of the named sheets
    for sheet, df in sheets.items():
        if named and sheet not in named: continue
        mr = None if pdf else merges(path, sheet)
        df = fill_merges(df, mr).dropna(how="all").dropna(how="all", axis=1).reset_index(drop=True)
        df.attrs["merged"] = bool(mr)
        df.columns = range(df.shape[1])
        for title, c0, labels, rows, df, ctx, ent_hdr in blocks(df, bool(mr)):
            tid = (re.search(r"TABLE\s*[\w.]+", title, re.I) or [None])[0]
            ycols = [c for c, l in labels.items() if l.strip().upper() == "YEAR"]
            hdr_txt = ent_hdr.lower()
            etype = ("state_or_district" if "state" in hdr_txt and "district" in hdr_txt else "state" if "state" in hdr_txt else "district" if "district" in hdr_txt
                     else "city" if "city" in hdr_txt or "cities" in hdr_txt else "crime_head" if "crime" in hdr_txt else "other")
            default_year, ysrc0 = pub_year(url, title, str(sheet))
            for r in rows:
                raw = clean(df.iat[r, c0]); city_state = None
                m = re.match(r"(.+?)\s*\((.+)\)$", raw) if etype == "city" else None
                if m: raw, city_state = clean(m[1]), state_code(m[2])
                total = bool(re.match(r"total|all.?india|grand total", raw, re.I))
                sc = city_state or (state_code(raw, etype != "state_or_district") if etype in ("state", "district", "state_or_district") else None)
                etype_row = ("state" if sc else "district") if etype == "state_or_district" else etype
                parent = sc if etype_row == "state" else ctx.get(r) if etype_row == "district" else sc
                ent = raw
                row_year = next((int(num(df.iat[r, c])) for c in ycols if is_num(df.iat[r, c])), None)
                for c, lab in labels.items():
                    v = df.iat[r, c]
                    if c in ycols or not is_num(v): continue
                    y, ysrc = (row_year, "row") if row_year else (None, None)
                    if y is None:
                        y = col_year(lab)
                        y, ysrc = (y, "column") if y else (default_year, ysrc0)
                    cat = crime_category(raw if etype == "crime_head" and not total else lab) if etype == "crime_head" or crime_category(lab) not in (None, "other") else crime_category(title)
                    out.append((name, url, str(sheet), tid, title[:400], etype_row, ent, sc if etype_row != "crime_head" else None, parent, total, lab or "value", metric(lab, title), cat, victim_group(title + " | " + lab), y, ysrc, num(v), "pdf" if pdf else "xls", ts, f"https://web.archive.org/web/{ts}/{url}" if ts else None, publisher(url)))
    return out

def parse_file(path, url, ts=""):
    """All facts of one document. A document that trips the parser is skipped, never allowed to stop the run."""
    try: return _parse_file(path, url, ts)
    except Exception as e: print("skip", os.path.basename(path), type(e).__name__, file=sys.stderr); return []

COLS = ["file", "source_url", "sheet", "table_id", "table_title", "entity_type", "entity", "state_code", "parent_state_code", "is_total", "column_label", "metric", "crime_category", "victim_group", "year", "year_source", "value", "format", "wayback_timestamp", "wayback_url", "publisher"]

CATS = ["file", "source_url", "sheet", "table_id", "table_title", "entity_type", "entity", "state_code", "parent_state_code", "column_label", "metric",
        "crime_category", "victim_group", "year_source", "format", "wayback_timestamp", "wayback_url", "publisher"]  # repetitive strings: stored once, referenced by code

def pack(parts):
    """Concatenate frames with string columns as categoricals. Millions of facts as Python tuples/strings would not fit in a runner's RAM."""
    parts = [p for p in parts if p is not None and len(p)]
    df = pd.concat([p.drop(columns=CATS) for p in parts], ignore_index=True)
    for c in CATS: df[c] = pd.concat([p[c].astype(object) for p in parts], ignore_index=True).astype("category")
    return df[COLS]

def qc(df):
    """Flag state-level facts whose columns don't add up to the all-India total row of the same table."""
    df["qc"] = "unchecked"
    s = df[(df.entity_type == "state") & (df.metric != "rate")]
    key = ["file", "sheet", "table_title", "column_label", "year"]
    tot = s[s.is_total & s.entity.str.contains("india", case=False)].groupby(key, dropna=False).value.first()
    parts = s[s.state_code.notna() & ~s.is_total].groupby(key, dropna=False).value.sum()
    ok = pd.concat([tot, parts], axis=1, keys=["t", "p"]).dropna()
    ok["q"] = ((ok.t - ok.p).abs() <= 0.005 * ok.t.abs() + 1).map({True: "sum_ok", False: "sum_mismatch"})
    df["qc"] = df[key].merge(ok.q.reset_index(), on=key, how="left").q.fillna("unchecked").values  # left merge keeps row order
    # district sheets: a state's districts against the Total row that closes them. Passing (block_ok) means the block is complete and its state is the right one.
    isd = district_rows(df)
    d, k2 = df.iloc[isd], key + ["parent_state_code"]
    d = d[d.parent_state_code.notna() & (d.metric != "rate")]
    t = d[d.is_total].groupby(k2, dropna=False, observed=True).value.agg(["first", "size"])
    ok = pd.concat([t[t["size"] == 1]["first"], d[~d.is_total].groupby(k2, dropna=False, observed=True).value.sum()], axis=1, keys=["t", "p"]).dropna()
    ok["q"] = ((ok.t - ok.p).abs() <= 0.005 * ok.t.abs() + 1).map({True: "block_ok", False: "sum_mismatch"})
    res = df.qc.to_numpy(object).copy()
    res[isd] = df.iloc[isd][k2].merge(ok.q.reset_index(), on=k2, how="left").q.fillna("unchecked").to_numpy()
    df["qc"] = res
    return df

def district_rows(df):
    """Positions of the rows in district sheets: the districts, and the state-named rows (Chandigarh, Lakshadweep) that are a UT's one district there."""
    g = lambda c: df[c].cat.codes.to_numpy().astype(np.int64)
    sheet = (g("file") * 100003 + g("sheet")) * 100003 + g("table_title")
    dist = (df.entity_type == "district").to_numpy()
    return np.flatnonzero(np.isin(sheet, np.unique(sheet[dist])) & (dist | ((df.entity_type == "state") & ~df.is_total).to_numpy()))

def infer_states(df):
    """Cities and districts whose table printed no state (the metropolitan-city tables, whole tables without 'State:' banners) get one from the place table (GeoNames), so
    every such row can be grouped by state. Marked `state_inferred`. A name shared by several states (Aurangabad, Bilaspur) is settled by the other districts of the same
    sheet, then by size, else left empty rather than guessed. Run before de-duplication, so a district seen with and without its state in two files is one fact."""
    df["state_inferred"] = False
    place = df.entity_type.isin(["city", "district"]) & ~df.is_total
    need = place & df.parent_state_code.isna()
    if not need.any(): return df
    t = df.loc[need, ["file", "sheet", "entity", "entity_type", "year", "table_title"]].astype({"file": object, "sheet": object, "entity": object, "entity_type": object, "table_title": object})
    known = df.loc[place & df.parent_state_code.notna(), ["file", "sheet", "entity", "parent_state_code"]].astype(object).drop_duplicates()
    votes = {k: {s: n for s, n in g.parent_state_code.value_counts().items() if n} for k, g in known.groupby(["file", "sheet"])}  # state -> distinct places of the sheet already placed there
    for (f, sh), title in t[["file", "sheet", "table_title"]].drop_duplicates(["file", "sheet"]).set_index(["file", "sheet"]).table_title.items():  # a state named in the sheet or table title counts for more
        for c, n in states_in(f"{sh} {title}").items(): votes.setdefault((f, sh), {})[c] = votes.get((f, sh), {}).get(c, 0) + 3 * n
    uniq = set(zip(t.file, t.sheet, t.entity, t.entity_type))
    for f, sh, e, _ in uniq:  # neighbours in the same sheet that exist in one state only are evidence too
        c = state_code(e, False) or place_unique(e)
        if c: votes.setdefault((f, sh), {})[c] = votes.get((f, sh), {}).get(c, 0) + 1
    found = {k: state_code(k[2], False) or place_state(k[2], votes.get(k[:2]), metro=k[3] == "city") for k in uniq}  # an entity that is itself a state name is that state
    new = pd.Series([found[k] for k in zip(t.file, t.sheet, t.entity, t.entity_type)], index=t.index, dtype=object)
    new = new.mask((new == "TS") & (t.year < 2014), "AP").mask((new == "LA") & (t.year < 2019), "JK")  # a 2010 table agrees with its own state rows
    new = new[new.notna()]
    rows = {"parent_state_code": new.index, "state_code": new.index[(df.loc[new.index, "entity_type"] == "city").values & df.loc[new.index, "state_code"].isna().values]}
    for col, idx in rows.items():
        df[col] = df[col].cat.add_categories([c for c in new.unique() if c not in df[col].cat.categories])
        df.loc[idx, col] = new[idx].values
    df.loc[new.index, "state_inferred"] = True
    return df

ORDER = "AP AR AS BR CG GA GJ HR HP JK JH KA KL MP MH MN ML MZ NL OD PB RJ SK TN TS TR UP UK WB AN CH DH DL LD PY".split()  # NCRB's district sheets before Ladakh: states by name, then UTs by name

def block_states(df):
    """District sheets are stacked state after state, each state closed by a 'Total' row, so a block of rows is one state. The block's state is the one most of its rows
    already have (printed, or from the place table). Its unplaced rows (CID, GRP, a misspelt district) and its Total row take that state; a row the place table put
    elsewhere gives way to a clear majority. A state NCRB printed is never overridden."""
    idx = district_rows(df)
    if not len(idx): return df
    df["parent_state_code"] = df.parent_state_code.cat.add_categories([c for c in ORDER if c not in df.parent_state_code.cat.categories])
    s = df.iloc[idx]
    f, sh, tt, en = (s[c].cat.codes.to_numpy() for c in ("file", "sheet", "table_title", "entity"))
    par, tot, inf = s.parent_state_code.cat.codes.to_numpy(), s.is_total.to_numpy(bool), s.state_inferred.to_numpy(bool)
    new_sheet = np.r_[True, (f[1:] != f[:-1]) | (sh[1:] != sh[:-1]) | (tt[1:] != tt[:-1])]
    start = np.flatnonzero(new_sheet | np.r_[True, en[1:] != en[:-1]])  # one run = the facts of one source row (they share the entity and sit together)
    run = np.cumsum(np.isin(np.arange(len(idx)), start)) - 1
    r_par, r_tot, r_inf = np.maximum.reduceat(par, start), tot[start], inf[start]
    blk = np.cumsum(new_sheet[start] | np.r_[True, r_tot[:-1]]) - 1  # a block ends with its Total row
    k = pd.DataFrame({"blk": blk, "par": r_par})[(~r_tot) & (r_par >= 0)]
    cnt = k.groupby(["blk", "par"]).size().rename("n").reset_index().sort_values(["blk", "n"], ascending=[True, False])
    top = cnt.drop_duplicates("blk").set_index("blk")
    top["share"] = top.n / cnt.groupby("blk").n.sum().reindex(top.index)
    rows = pd.Series(~r_tot).groupby(blk).sum().reindex(top.index)  # places in the block
    top = top[(top.share >= 0.8) & ((top.n >= 2) | (rows == 1))]
    nb = blk[-1] + 1
    bp = np.full(nb, -1); bp[top.index] = top.par
    cats = list(df.parent_state_code.cat.categories)
    yr = pd.Series(s.year.to_numpy()[start]).groupby(blk).first().to_numpy()
    sheet_of = pd.Series(np.cumsum(new_sheet[start])).groupby(blk).first().to_numpy()
    for sh_id in np.unique(sheet_of):  # NCRB stacks its district sheets in the order of the state names: a block no place told apart sits between its neighbours' states
        bs = np.flatnonzero(sheet_of == sh_id)
        if not 2014 <= yr[bs[0]] < 2020: continue
        order = [c for c in ORDER if c != "TS" or yr[bs[0]] >= 2014]
        known = {cats[bp[b]]: b for b in bs if bp[b] >= 0}
        i = 0
        while i < len(bs):
            if bp[bs[i]] >= 0: i += 1; continue
            j = i
            while j < len(bs) and bp[bs[j]] < 0: j += 1  # blocks i..j-1 are unplaced
            a = cats[bp[bs[i - 1]]] if i else None
            z = cats[bp[bs[j]]] if j < len(bs) else None
            if (a is None or a in order) and (z is None or z in order):
                free = [c for c in order[order.index(a) + 1 if a else 0:order.index(z) if z else len(order)] if c not in known and c in cats]
                if len(free) == j - i:
                    for b, c in zip(bs[i:j], free): bp[b] = cats.index(c)
            i = j
    b_par = bp[blk]
    b_n = pd.Series(blk).map(top.n).fillna(0).to_numpy()
    r_new = np.where((r_par < 0) | (r_inf & (r_par != b_par) & (b_n >= 4)), b_par, r_par)  # unplaced rows, and place-table rows against a clear majority
    r_ch = (r_new != r_par) & (r_new >= 0)
    ch = r_ch[run]
    full = df.parent_state_code.cat.codes.to_numpy().copy()
    full[idx[ch]] = r_new[run][ch]
    df["parent_state_code"] = pd.Categorical.from_codes(full, categories=df.parent_state_code.cat.categories)
    flag = df.state_inferred.to_numpy(bool).copy(); flag[idx[ch]] = True
    df["state_inferred"] = flag
    print(f"blocks: {len(top):,} district blocks settled a state; {ch.sum():,} facts placed or corrected ({int((r_ch & (r_par >= 0)).sum()):,} source rows overridden)", flush=True)
    return df

def finish(df, out):
    df = fix_years(df)
    df = block_states(infer_states(df))
    df = qc(df)
    # redundancy: identical fact seen in several files collapses to one row; same key with different values is kept and flagged
    tk = {t: re.sub(r"\s+", " ", re.sub(r"\d+|table\s*[\w.]*", "", t.lower())).strip() for t in df.table_title.cat.categories}  # per distinct title, not per row
    df["title_key"] = df.table_title.map(tk).astype("category")
    # A spreadsheet's columns are what they say. A PDF's are read from text lines, so a PDF row is trusted only when its figures add up (state rows to the all-India row,
    # districts to their Total): a column in the wrong place would not sum. The other PDF rows (confidence=low) live in their own file.
    df["trusted"] = ((df.format == "xls") | df.qc.isin(["sum_ok", "block_ok"])).to_numpy()
    ntrusted = df[df.trusted].file.astype(object).value_counts()  # per document, before identical facts of several documents collapse into the first one's
    key = ["entity_type", "entity", "parent_state_code", "year", "metric", "column_label", "title_key", "is_total", "trusted"]
    g = df.groupby(key, dropna=False, observed=True).value
    df["n_sources"] = g.transform("size"); df["conflict"] = g.transform("nunique") > 1
    df = df.iloc[np.argsort((df.format != "xls").to_numpy(), kind="stable")].drop_duplicates(key + ["value"])  # the same fact in a spreadsheet and a PDF: the spreadsheet's row stays
    df[df.trusted].drop(columns="trusted").to_parquet(f"{out}/facts.parquet", index=False)
    df[~df.trusted].drop(columns="trusted").to_parquet(f"{out}/facts_pdf_lowconf.parquet", index=False)
    if os.path.exists(f"{out}/conflicts.csv"): os.remove(f"{out}/conflicts.csv")  # retired: 460 MB that only repeated facts.parquet rows with conflict == True
    build_panel(df, out)
    df.loc[(df.entity_type == "state") & df.state_code.isna() & ~df.is_total, "entity"].value_counts().to_csv(f"{out}/unmapped_states.csv")
    print(len(df), "facts;", df.conflict.sum(), "conflicting;", df.qc.value_counts().to_dict(), df.format.value_counts().to_dict(), f"{int(df.trusted.sum()):,} trusted")
    return ntrusted

def catalogue(raw, out, nfacts, ntrusted):
    """documents.csv: one row per stored document: what it is, where it came from (live URL + Wayback permalink), and whether it became facts."""
    from urllib.parse import unquote, urlparse
    m = pd.read_csv(f"{raw}/manifest.csv", dtype=str).fillna("")
    for c in ("publisher", "retrieved"):
        if c not in m: m[c] = ""
    m = m.sort_values("wayback_timestamp", kind="stable")
    g = m.groupby("file", sort=True)
    d = g.agg(publisher=("publisher", "first"), source_url=("url", "first"), n_urls=("url", "nunique")).reset_index()
    last = g.tail(1).set_index("file")  # latest capture of the bytes: the best permalink
    d["wayback_url"] = [f"https://web.archive.org/web/{ts}/{u}" if ts else "" for ts, u in zip(d.file.map(last.wayback_timestamp), d.file.map(last.url))]
    d["first_capture"] = d.file.map(g.wayback_timestamp.min().str[:8]).replace("", None)
    d["last_capture"] = d.file.map(last.wayback_timestamp.str[:8]).replace("", None)
    d["raw_path"] = "raw-" + d.file.str[0] + "/" + d.file
    d["ext"] = d.file.str.rsplit(".", n=1).str[-1]
    d["bytes"] = [os.path.getsize(f"{raw}/{f}") if os.path.exists(f"{raw}/{f}") else None for f in d.file]
    d["title_hint"] = [re.sub(r"[_+\-\s]+", " ", unquote(os.path.basename(urlparse(u).path)).rsplit(".", 1)[0]).strip() for u in d.source_url]
    d["year_hint"] = [pub_year(u, "", "")[0] for u in d.source_url]
    d["n_facts"] = d.file.map(nfacts).fillna(0).astype(int)
    d["status"] = ["facts" if t else "facts_low_confidence" if n else "no_tables_found" if e in ("xls", "xlsx", "pdf") else "not_parsed" for n, t, e in zip(d.n_facts, d.file.map(ntrusted).fillna(0), d.ext)]
    d[["file", "raw_path", "ext", "bytes", "publisher", "title_hint", "year_hint", "source_url", "wayback_url", "first_capture", "last_capture", "n_urls", "status", "n_facts"]].to_csv(f"{out}/documents.csv", index=False)

def work(a):
    return a[0], parse_file(*a)

def main(raw="data/raw", out="data/clean", pdf_limit=8e6, budget=int(os.getenv("PARSE_BUDGET", 9000))):
    """Incremental: only files not yet in parse_state.json are parsed (in parallel); everything is re-QC'd and re-deduped each run."""
    import json, multiprocessing
    os.makedirs(out, exist_ok=True)
    sf, rf = f"{out}/parse_state.json", f"{out}/facts_raw.parquet"
    st = json.load(open(sf)) if os.path.exists(sf) else {}
    done, old = (set(st.get("files", [])), pd.read_parquet(rf)) if st.get("files") and os.path.exists(rf) else (set(), None)
    changed = lambda f: st.get("pdf_version", 10) != PDF_VERSION if f.lower().endswith(".pdf") else st.get("version") != PARSER_VERSION  # spreadsheets and PDFs have parsers of their own
    stale = {f for f in done if changed(f) and os.path.exists(f"{raw}/{f}")}
    if stale: old, done = old[~old.file.isin(stale)], done - stale; print(f"parser changed: {len(stale):,} documents are parsed again (rows of documents no longer on disk are kept)")
    src = {}  # same content under several URLs is parsed once; the first URL supplies year hints
    for r in csv.DictReader(open(f"{raw}/manifest.csv")): src.setdefault(r["file"], (r["url"], r["wayback_timestamp"]))
    ok = lambda f: f.lower().endswith((".xls", ".xlsx")) or (f.lower().endswith(".pdf") and os.path.getsize(f"{raw}/{f}") < pdf_limit)
    todo = [(f"{raw}/{f}", *u) for f, u in sorted(src.items()) if f not in done and os.path.exists(f"{raw}/{f}") and ok(f)]
    rows, chunks, new_done, t0 = [], [], set(), time.time()
    with multiprocessing.Pool() as pool:
        for i, (p, r) in enumerate(pool.imap_unordered(work, todo, chunksize=4)):
            rows += r; new_done.add(os.path.basename(p))
            if len(rows) > 200_000: chunks.append(pack([pd.DataFrame(rows, columns=COLS)])); rows = []
            if i % 200 == 0: print(i, "/", len(todo), flush=True)
            if time.time() - t0 > budget: pool.terminate(); print("parse budget hit; next run resumes"); break
    chunks.append(pd.DataFrame(rows, columns=COLS))
    df = pack([old, *chunks]); del rows, chunks, old
    df.to_parquet(rf, index=False)
    json.dump({"version": PARSER_VERSION, "pdf_version": PDF_VERSION, "files": sorted(done | new_done)}, open(sf, "w"))
    nfacts = df.file.astype(object).value_counts()
    ntrusted = finish(df, out); write_reference(out); catalogue(raw, out, nfacts, ntrusted)

if __name__ == "__main__": main(*sys.argv[1:])
