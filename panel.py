"""Curated tables from the long facts, in the shape analysts want. Both keep only crime-head figures (no sex / age splits), collapse identical numbers
reported by several files into one row, and where files disagree keep the value most of them report and say so in `disputed`.
  crime_state_year.csv  one row per state/UT x year x table family x crime head x measure. Only state rows that add up to NCRB's own all-India row (qc = sum_ok).
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
NOT_HEADWISE = re.compile(r"disposal|trial|custod|duration|by place of occ|property stolen|motive|firing|human rights|police personnel|age.?group|by sex|gender|metropolitan|city-wise")  # ... not case-lifecycle, demographic or city ones
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

def scope(title):
    if not HEADWISE.search(title) or NOT_HEADWISE.search(title): return None
    return next((k for k, r in _SCOPES if r.search(title)), None)

def head(label):
    """The crime head a column is about: its label path without measure abbreviations, years and banners ('Murder | A) Murder with Rape'). None for sex / age splits."""
    segs = [x.strip() for x in str(label).split(" | ")]
    segs = [x for x in segs if x and not re.fullmatch(r"(19|20)\d\d", x) and x.lower() not in METRIC_TOK and not re.match(r"(source|states?)\s*:", x, re.I)
            and not BANNER.search(x) and not re.fullmatch(r"(ipc|sll) crimes( against .*)?", x, re.I)]
    return None if not segs or any(DEMOGRAPHIC.search(x) for x in segs) else " | ".join(segs)

def key(h):
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
    votes = f.groupby(by + ["value"]).agg(votes=("file", "size"), checked=("qc", lambda q: bool((q == "sum_ok").any()))).reset_index()
    n_values = votes.groupby(by).size().rename("n_values").reset_index()
    win = votes.sort_values("votes", ascending=False, kind="stable").drop_duplicates(by)
    f = f.merge(win[by + ["value", "checked"]], on=by + ["value"]).sort_values("wayback_timestamp", ascending=False, na_position="last", kind="stable").drop_duplicates(by)
    f = f.merge(n_values, on=by)
    f["disputed"] = f.n_values > 1
    f["crime_head"] = f["head"].str.replace(r"\s+", " ", regex=True).str.strip()
    f["crime_category"] = f.crime_head.map(crime_category)
    f["year"] = f.year.astype(int)
    return f.sort_values(by[:1] + ["year", "scope", "crime_head", "metric"]).reset_index(drop=True)

def state_table(facts):
    f = plain(facts[(facts.entity_type == "state") & facts.state_code.notna() & ~facts.is_total & facts.year.notna() & (facts.qc == "sum_ok") & facts.metric.isin(KEEP) & (facts.format == "xls")])
    f["scope"], f["head"] = f.title_key.map(scope), f.column_label.map(head)
    f = f[f.scope.notna() & f["head"].notna()]
    f["head_key"] = f["head"].map(key)
    f = collapse(f, ["state_code", "year", "scope", "head_key", "metric"])
    f["state"] = f.state_code.map(STATES)
    return f[["state_code", "state", "year", "scope", "crime_head", "crime_category", "metric", "value", "disputed", "table_id", "file"]]

def india_table(facts):
    ok = facts.year.notna() & facts.metric.isin(KEEP + ("rate", "percentage")) & (facts.format == "xls")
    nat = plain(facts[ok & (facts.entity_type == "crime_head")])  # NCRB's national tables: rows are crime heads, columns are years x measures
    nat = nat[~nat.column_label.str.contains(DEMOGRAPHIC) & nat.column_label.map(lambda l: state_code(l.split(" | ")[-1], False)).isna() & ~nat.title_key.map(in_state)]  # a state in the column or the title: not national
    nat["head"] = nat.entity.map(lambda e: None if DEMOGRAPHIC.search(e) and not re.match(r"total", e, re.I) else e)
    tot = plain(facts[ok & (facts.entity_type == "state") & facts.is_total & (facts.qc == "sum_ok")])  # the all-India row of each state table
    tot = tot[tot.entity.str.contains("india", case=False)]
    tot["head"] = tot.column_label.map(head)
    f = pd.concat([nat, tot])
    f["scope"] = f.title_key.map(scope)
    f = f[f.scope.notna() & f["head"].notna()]
    f["head_key"] = f["head"].map(key)
    f = collapse(f, ["year", "scope", "head_key", "metric"])
    return f[["year", "scope", "crime_head", "crime_category", "metric", "value", "disputed", "checked", "table_id", "file"]]

def build(facts, out):
    """facts: the full facts frame. Writes crime_state_year.csv and crime_india_year.csv; returns both."""
    s, i = state_table(facts), india_table(facts)
    s.to_csv(f"{out}/crime_state_year.csv", index=False); i.to_csv(f"{out}/crime_india_year.csv", index=False)
    return s, i
