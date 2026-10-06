"""Curated tables from the long facts, in the shape analysts want. Both keep only crime-head figures (no sex / age splits), collapse identical numbers
reported by several files into one row, and where files disagree keep the value most of them report and say so in `disputed`.
  crime_state_year.csv  one row per state/UT x year x table family x crime head x measure. Only figures that add up: state rows against NCRB's all-India row (qc = sum_ok), or NCRB's state Total row of a district table against its districts (qc = block_ok).
  crime_india_year.csv  the same for all-India: NCRB's national crime-head tables, plus the all-India row of each state table (so 2001-2015 and 2016-2022 join up).
Everything else stays in facts.parquet."""
import re
import pandas as pd
from taxonomy import STATES, crime_category, state_code

SCOPES = [("women", r"against women"), ("children", r"against children|crimes? by children"), ("scheduled_castes", r"scheduled castes?|against scs|\bscs\b"),
          ("scheduled_tribes", r"scheduled tribes?|against sts|\bsts\b"), ("senior_citizens", r"senior citizen"), ("juveniles", r"juvenile"),
          ("cyber", r"cyber|\bit act|i t act"), ("sll", r"\bsll\b"), ("ipc", r"\bipc\b")]
_SCOPES = [(k, re.compile(p)) for k, p in SCOPES]
HEADWISE = re.compile(r"head-?wise|various crime|various crimes|cases registered (under|for)|cases reported ?\(cr\)|\(cr\)")  # crime-head tables ...
DISTRICTWISE = re.compile(r"district-?wise")  # NCRB's district tables: one block of districts per state, closed by that state's own Total row
NOT_HEADWISE = re.compile(r"disposal|trial|custod|duration|by place of occ|property stolen|motive|firing|human rights|police personnel|age.?group|by sex|sex-?wise|gender|profile|metropolitan|city-wise|\bgrp\b|cr\.?p\.?c")  # ... not case-lifecycle, demographic, city or railway-police (GRP) ones, nor registrations split by police station / court order (Cr.PC 156(3)): their columns are parts of a total
METRIC_TOK = {"cr", "ccs", "cs", "cv", "con", "par", "part", "pcs", "pcst", "pcv", "pcvt", "pcr", "caq", "cncfr", "chr", "csr", "cvr", "i", "v", "r", "sl", "value"}
DEMOGRAPHIC = re.compile(r"^(?:fe)?male$|transgender|\d\s*(?:years?|yrs)\b|\byrs?\b|\byears\b|^(?:above|below|between)\b|^total (?:fe)?male|^(?:total|grand total)$|^a60|^b\d\d|^gtot|^tot[fm]$|persons|^cases ", re.I)
BANNER = re.compile(r"head-?wise|ut-wise|city-wise|state/ut|^table\b|\(continued\)|\(concluded\)", re.I)  # table-title fragments that leak into header cells
KEEP = ("cases_registered", "cases_chargesheeted", "cases_convicted", "persons_arrested", "persons_chargesheeted", "persons_convicted", "victims")  # rates are not sum-checkable, so no state rates
SYNONYM = {  # the same NCRB head, spelled differently across editions
    "thefts": "theft", "other ipc crime": "other ipc crimes", "total ipc crimes": "total cognizable ipc crimes", "total sll crimes": "total cognizable sll crimes",
    "cruelty by husband or relatives": "cruelty by husband or his relatives", "importation of girls": "importation of girls from foreign country",
    "ch not amounting murder": "culpable homicide not amounting to murder", "making preparation and assembly for committing dacoity": "preparation & assembly for dacoity",
    "molestation": "assault on women with intent to outrage her modesty", "sexual harrassment": "insult to the modesty of women", "insult to modesty of women": "insult to the modesty of women",
    "kidnapping and abduction": "kidnapping & abduction", "kidnapping & abduction total": "kidnapping & abduction"}

FAMILY_TITLE = re.compile(r"\b(?:ipc|sll|cyber) crimes?\b|crimes? (?:committed )?against|atrocities")  # 2016-style titles: 'IPC Crimes Against Women - 2016', no 'head-wise'

def scope(title):
    if not (HEADWISE.search(title) or DISTRICTWISE.match(title) and "missing" not in title or FAMILY_TITLE.search(title)) or NOT_HEADWISE.search(title): return None
    return next((k for k, r in _SCOPES if r.search(title)), "")  # "": a head-wise table of no named family; a per-head table (see per_head) says which by its head

BOTH = re.compile(r"\bipc\b.*\bsll\b|\bsll\b.*\bipc\b")
SLL_HEAD = re.compile(r"\bacts?\b|\bsll\b", re.I)

def rescope(f):
    """A title naming both 'IPC & SLL' (older national and all-India tables) lists IPC heads and SLL heads together: the head says which family each belongs to."""
    m = f.scope.isin(["ipc", "sll"]) & f.title_key.str.contains(BOTH)
    f.loc[m, "scope"] = f.loc[m, "head"].map(lambda h: "sll" if SLL_HEAD.search(h) else "ipc")
    return f

HAS_YEAR = re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)")
TITLE_HEAD = re.compile(r"\bunder (.+?),? *(?:during|in india)\b", re.I)
SUMMARY = re.compile(r"state.?/?ut.?wise", re.I)  # 'IPC Crimes (State/UT-wise)': a family's total per state and year
FAMILY_TOTAL = {"ipc": "Total Cognizable IPC Crimes", "sll": "Total Cognizable SLL Crimes", "women": "Total Crimes against Women", "children": "Total Crimes against Children",
                "scheduled_castes": "Total Crimes against Scheduled Castes", "scheduled_tribes": "Total Crimes against Scheduled Tribes", "senior_citizens": "Total Crimes against Senior Citizens",
                "cyber": "Total Cyber Crimes", "juveniles": "Total Crimes by Juveniles"}

def segments(label):
    """The parts of a column label that say what is counted: no measure abbreviations, years or banners."""
    segs = [x.strip() for x in str(label).split(" | ")]
    return [x for x in segs if x and not re.fullmatch(r"(19|20)\d\d", x) and x.lower() not in METRIC_TOK and not re.match(r"(source|states?)\s*:", x, re.I)
            and not BANNER.search(x) and not re.fullmatch(r"(ipc|sll) crimes( against .*)?", x, re.I)]

def head(label):
    """The crime head a column is about: its label path without measure abbreviations, years and banners ('Murder | A) Murder with Rape'). None for sex / age splits."""
    segs = segments(label)
    return None if not segs or any(DEMOGRAPHIC.search(x) for x in segs) else " | ".join(segs)

def title_head(title):
    """'... & persons convicted under Rape during 2007-2012' -> 'Rape' (the last one: tables stacked in a sheet leave the previous title's words in this one)."""
    ms = TITLE_HEAD.findall(str(title))
    h = ms and re.sub(r"\b(ipc|sll)\b", lambda x: x[1].upper(), re.sub(r"\s+", " ", re.sub(r" for crimes? (?:against|committed against) \w+$", "", ms[-1].strip(" *,"), flags=re.I)), flags=re.I)
    return h[:1].upper() + h[1:] if h else None

def family(title):
    return next((k for k, r in _SCOPES if r.search(title)), "")

def per_head(f):
    """Columns that are only a year (and a measure) name no head, so the table says it: NCRB's 2001-2015 and 2006-2012 files have one table per crime head ('Cases registered
    under Rape during ...'), and its summary tables give a family's total per state and year ('IPC Crimes (State/UT-wise)'). The family is IPC unless the head is an Act."""
    lab = pd.Series(f.column_label.unique())
    bare = dict(zip(lab, lab.map(lambda l: bool(HAS_YEAR.search(l)) and not segments(l))))
    m = f["head"].isna() & f.column_label.map(bare) & ~f.title_key.str.contains(NOT_HEADWISE)
    f.loc[m, "head"] = f.loc[m, "table_title"].map(title_head)
    f.loc[m, "scope"] = [family(t) or ("sll" if SLL_HEAD.search(h) else "ipc") if isinstance(h, str) else None for t, h in zip(f.loc[m, "title_key"], f.loc[m, "head"])]
    t = m & f["head"].isna() & f.title_key.str.contains(SUMMARY) & ~f.title_key.str.contains(BOTH) & ~f.title_key.str.contains("head-?wise")
    fam = f.loc[t, "title_key"].map(family)
    f.loc[t, "scope"], f.loc[t, "head"] = fam, fam.map(FAMILY_TOTAL)
    return f[f.scope.fillna("").ne("") & f["head"].notna()]

def key(h):
    h = re.sub(r"\(\s*total\s*\)", " total ", h, flags=re.I)  # 'Kidnapping and Abduction (Total)' is the sum of its sub-heads, not 'Kidnapping and Abduction (Sec.363 IPC)': different numbers
    k = re.sub(r"\s+", " ", re.sub(r"\(.*?\)|sec\.?\s*[\d\w\- ,&]+(ipc)?|[,.:;]| act$|, ?\d{4}", "", h.lower())).strip()
    return SYNONYM.get(k, k)

IN_STATE = re.compile(r"\b(?:in|of) (?:(?:ut|state) of )?([a-z&. ]+?) (?:during|from)\b")

def in_state(title):
    """'... crimes in Andhra Pradesh during 2001': one state's own table, not a national one."""
    m = IN_STATE.search(title)
    return bool(m and state_code(m[1], False))

def plain(f): return f.assign(**{c: f[c].astype(object) for c in f.columns if str(f[c].dtype) == "category"})  # plain strings: cheap merges, no category mismatches

def collapse(f, by):
    """One row per key: the value most rows agree on, from its latest capture; `disputed` if any row disagreed; `checked` if a state-sum-verified row backs the value."""
    f = f.assign(pri=f["pri"] if "pri" in f else 0)  # on a tie, the table that prints the figure outranks one that adds it up
    votes = f.groupby(by + ["value"]).agg(votes=("file", "size"), pri=("pri", "min"), checked=("qc", lambda q: bool((q == "sum_ok").any()))).reset_index()
    n_values = votes.groupby(by).size().rename("n_values").reset_index()
    win = votes.sort_values(["votes", "pri"], ascending=[False, True], kind="stable").drop_duplicates(by)
    f = f.merge(win[by + ["value", "checked"]], on=by + ["value"]).sort_values(["pri", "wayback_timestamp"], ascending=[True, False], na_position="last", kind="stable").drop_duplicates(by)
    f = f.merge(n_values, on=by)
    f["disputed"] = f.n_values > 1
    f["crime_head"] = f["head"].str.replace(r"\s+", " ", regex=True).str.strip()
    f["crime_category"] = f.crime_head.map(crime_category)
    f["year"] = f.year.astype(int)
    return f.sort_values(by[:1] + ["year", "scope", "crime_head", "metric"]).reset_index(drop=True)

def state_table(facts):
    """State rows of the state-wise tables (they add up to the all-India row), plus NCRB's own state Total row of each district table (the districts add up to it): that
    is how 2016-2020, which have no state-wise tables, get states."""
    ok = facts.year.notna() & facts.metric.isin(KEEP)  # a PDF row is here only if its figures added up (qc below)
    a = plain(facts[ok & (facts.qc == "sum_ok") & (facts.entity_type == "state") & facts.state_code.notna() & ~facts.is_total]).assign(source="state_table", pri=0)
    is_state_total = (facts.entity_type == "district") & facts.is_total | (facts.entity_type == "state") & ~facts.is_total  # the Total row of a block, or a UT that is its own only district
    b = plain(facts[ok & (facts.qc == "block_ok") & facts.parent_state_code.notna() & is_state_total]).assign(source="district_total", pri=1)
    b["state_code"] = b.parent_state_code
    f = pd.concat([a, b], ignore_index=True)
    f["scope"], f["head"] = f.title_key.map(scope), f.column_label.map(head)
    f = rescope(per_head(f))
    k = ["file", "sheet", "table_title", "column_label", "state_code", "year", "metric"]
    dup = (f.source == "state_table") & f.duplicated(k, keep=False)
    if dup.any():  # Dadra & Nagar Haveli and Daman & Diu are two rows with one code (DH) until they merged in 2020: the merged UT's figure is their sum
        d = f[dup]
        f = pd.concat([f[~dup], d.groupby(k, as_index=False, sort=False).agg({**{c: "first" for c in d.columns.difference(k + ["value"])}, "value": "sum"})], ignore_index=True)
    f["head_key"] = f["head"].map(key)
    f = collapse(f, ["state_code", "year", "scope", "head_key", "metric"])
    f["state"] = f.state_code.map(STATES)
    return f[["state_code", "state", "year", "scope", "crime_head", "crime_category", "metric", "value", "disputed", "source", "table_id", "file"]]

def india_table(facts):
    ok = facts.year.notna() & facts.metric.isin(KEEP + ("rate", "percentage"))
    nat = plain(facts[ok & (facts.format == "xls") & (facts.entity_type == "crime_head")])  # NCRB's national tables: rows are crime heads, columns are years x measures
    nat = nat[~nat.column_label.str.contains(DEMOGRAPHIC) & nat.column_label.map(lambda l: state_code(l.split(" | ")[-1], False)).isna() & ~nat.title_key.map(in_state)]  # a state in the column or the title: not national
    nat["head"] = nat.entity.map(lambda e: None if DEMOGRAPHIC.search(e) and not re.match(r"total", e, re.I) else e)
    tot = plain(facts[ok & (facts.entity_type == "state") & facts.is_total & (facts.qc == "sum_ok")])  # the all-India row of each state table
    tot = tot[tot.entity.str.contains("india", case=False)]
    tot["head"] = tot.column_label.map(head)
    f = pd.concat([nat, tot])
    f["scope"] = f.title_key.map(scope)
    f = rescope(per_head(f))
    f["head_key"] = f["head"].map(key)
    f = collapse(f, ["year", "scope", "head_key", "metric"])
    return f[["year", "scope", "crime_head", "crime_category", "metric", "value", "disputed", "checked", "table_id", "file"]]

def build(facts, out):
    """facts: the full facts frame. Writes crime_state_year.csv and crime_india_year.csv; returns both."""
    s, i = state_table(facts), india_table(facts)
    s.to_csv(f"{out}/crime_state_year.csv", index=False); i.to_csv(f"{out}/crime_india_year.csv", index=False)
    return s, i
