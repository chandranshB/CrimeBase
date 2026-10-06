"""Shared vocab: state/UT canonicalisation (ISO 3166-2:IN) and crime-category rules, used by parse.py and news.py."""
import csv, difflib, functools, re
from pathlib import Path

STATES = {  # ISO code -> canonical name
    "AN": "Andaman and Nicobar Islands", "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar",
    "CH": "Chandigarh", "CG": "Chhattisgarh", "DH": "Dadra and Nagar Haveli and Daman and Diu", "DL": "Delhi", "GA": "Goa",
    "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir", "JH": "Jharkhand", "KA": "Karnataka",
    "KL": "Kerala", "LA": "Ladakh", "LD": "Lakshadweep", "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur",
    "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha", "PY": "Puducherry", "PB": "Punjab", "RJ": "Rajasthan",
    "SK": "Sikkim", "TN": "Tamil Nadu", "TS": "Telangana", "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal"}
ALIAS = {"orissa": "OD", "uttaranchal": "UK", "pondicherry": "PY", "chattisgarh": "CG", "a&n islands": "AN", "a and n islands": "AN",
         "andaman and nicobar": "AN", "d&n haveli": "DH", "dadra and nagar haveli": "DH", "daman and diu": "DH", "daman & diu": "DH",
         "d and n haveli": "DH", "delhi ut": "DL", "nct of delhi": "DL", "j&k": "JK", "jammu and kashmir": "JK", "jammu kashmir": "JK",
         "tamilnadu": "TN", "bengal": "WB", "kashmir": "JK", "telengana": "TS", "andhra pradesh": "AP", "dadra nagar haveli": "DH", "daman diu": "DH"}
_N = {re.sub(r"[^a-z]+", " ", v.lower()).strip(): k for k, v in STATES.items()}

def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z&]+", " ", str(s).lower().replace(" and ", " & ").replace("&", " & ")).replace(" & ", " and ")).strip()

_LOOK = {**_N, **{norm(k): v for k, v in ALIAS.items()}}

@functools.lru_cache(maxsize=None)
def state_code(s, fuzzy=True):
    """ISO code for a state/UT name, or None. Fuzzy only above 0.88 so 'Total' never maps."""
    n = norm(s)
    if n in _LOOK: return _LOOK[n]
    m = difflib.get_close_matches(n, _LOOK, 1, 0.88) if fuzzy else []
    return _LOOK[m[0]] if m else None

@functools.lru_cache(maxsize=None)
def states_in(text):
    """{state code: count} of state / UT names found in free text (longest first, so 'Arunachal Pradesh' is not read as 'Pradesh')."""
    t, out, i = norm(text).split(), {}, 0
    while i < len(t):
        for n in (4, 3, 2, 1):
            c = _LOOK.get(" ".join(t[i:i + n]))
            if c: out[c] = out.get(c, 0) + 1; i += n; break
        else: i += 1
    return out

GENERIC = {"east", "west", "north", "south", "central", "north east", "north west", "south east", "south west", "new", "old", "other", "others", "total", "city", "rural", "urban", "railway", "railways", "grp", "cid", "headquarters", "hq"}  # directions and labels, not places

PLACE_ALIAS = {"navi mum": "navi mumbai", "vasai virar": "virar", "durg bhilainagar": "bhilai"}  # abbreviations headlines use, and NCRB city names GeoNames spells differently
PLACE_QUALIFIERS = {"city", "rural", "urban", "commr", "commissionerate", "commissionarate", "commissioner", "railway", "railways", "police", "pc", "district", "dist", "old", "range", "zone"}  # NCRB suffixes: 'Ahmedabad City', 'Aurangabad Commr'

@functools.lru_cache(maxsize=1)
def _places():
    """name -> {state: (population, kind)}, from places.csv (GeoNames, CC BY 4.0; built by ci/make_places.py)."""
    d = {}
    with open(Path(__file__).with_name("places.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f): d.setdefault(r["name"], {})[r["state_code"]] = (int(r["population"]), r["kind"])
    return d

@functools.lru_cache(maxsize=None)
def place_candidates(name):
    """{state: (population, kind)} for a city, town or district name; {} if unknown. NCRB's 'City' / 'Rural' / 'Commr' suffixes are dropped, and 'A-B' / 'A and B' count if every half that is known agrees."""
    p = _places()
    k = norm(name).split()
    while len(k) > 1 and k[-1] in PLACE_QUALIFIERS: k.pop()
    key = PLACE_ALIAS.get(" ".join(k), " ".join(k))
    if key in GENERIC: return {}
    if key in p: return p[key]
    halves = [h for h in (place_candidates(x) for x in re.split(r"\s*(?:-|/|,|&|\band\b)\s*", str(name)) if x.strip() and x.strip() != str(name)) if h]
    return halves[0] if halves and all(len(h) == 1 and set(h) == set(halves[0]) for h in halves) else {}

def place_unique(name):
    """The state of a place name that exists in one state only, else None."""
    c = place_candidates(name)
    return next(iter(c)) if len(c) == 1 else None

def place_state(name, hints=None, year=None, min_votes=5, veto=True, metro=False):
    """ISO state of a city, town or district, or None when it can't be told. `hints` (state -> votes from the same table or headline) only count when concentrated: at least
    `min_votes` votes with one state holding 80% of them (a sheet listing every state favours the biggest one, which is no evidence at all). Then they settle names shared by
    several states (Aurangabad, Bilaspur ...) and, with `veto`, drop a place elsewhere as a probable namesake. Without usable hints, a name shared by states resolves only if
    one is at least 3x the size of the next; otherwise None rather than a guess. `year` maps today's Telangana / Ladakh back to the states they were part of then, so a 2010
    table agrees with its own state rows."""
    c = place_candidates(name)
    if not c: return None
    top = max(hints, key=hints.get) if hints else None
    strong = bool(hints) and sum(hints.values()) >= min_votes and hints[top] >= 0.8 * sum(hints.values())
    if len(c) == 1:
        s = next(iter(c))
        if strong and veto and s != top: s = None
    elif strong and top in c: s = top
    else:
        by_size = sorted(c, key=lambda x: -c[x][0])
        shared_district = sum(1 for x in c if c[x][1] == "district") > 1  # two real districts with one name (Bilaspur, Balrampur): size settles nothing, unless `metro`: a table of big cities means the big one
        s = by_size[0] if (metro or not shared_district) and c[by_size[0]][0] >= 3 * max(c[by_size[1]][0], 1) else None
    if year and s == "TS" and year < 2014: s = "AP"
    if year and s == "LA" and year < 2019: s = "JK"
    return s

NAME_LIKE = {"sagar", "anand", "raja", "ganga", "krishna", "mohan", "hari", "shiva", "lalit", "amar", "prem", "arun", "ajay", "vijay", "deepak", "sunil", "rani", "nagar", "kishan", "mandi", "bagh", "port", "siddhi", "madan", "ashok", "ravi", "usha"}  # towns that are also given names / words: only with 'in', 'at' ...
_ABBREV = re.compile(r"\b(UP|TN|WB|J ?& ?K)\b")  # safe, case-sensitive; not MP / AP / HP, which mean Member of Parliament / Associated Press / horsepower
_TOKEN = re.compile(r"[A-Za-z]+")

def find_places(text):
    """State and place mentions in a headline: [{start, end, text, kind: 'state' | 'place', state, weak}], in reading order. Names must be capitalised like names (unless the whole
    headline is). `weak` marks names that are too often something else (a given name, a tiny town): the caller should trust them only after 'in' / 'at' or as a dateline."""
    toks = [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(text)]
    low = [t[2].lower() for t in toks]
    capital = [t[2][0].isupper() for t in toks]
    loose = text.isupper() or text == text.lower()
    out, i = [], 0
    while i < len(toks):
        for n in (4, 3, 2, 1):
            if i + n > len(toks): continue
            span = " ".join(low[i:i + n])
            if not (loose or all(capital[i:i + n])): continue
            st = _LOOK.get(span)
            c = {} if st or span in GENERIC else place_candidates(span)
            if st or c:
                weak = bool(c) and n == 1 and (span in NAME_LIKE or (max(v[0] for v in c.values()) < 100000 and not any(v[1] == "district" for v in c.values())))
                out.append({"start": toks[i][0], "end": toks[i + n - 1][1], "text": text[toks[i][0]:toks[i + n - 1][1]], "kind": "state" if st else "place", "state": st, "weak": weak})
                i += n; break
        else: i += 1
    for m in _ABBREV.finditer(text):
        out.append({"start": m.start(), "end": m.end(), "text": m.group(), "kind": "state", "state": {"UP": "UP", "TN": "TN", "WB": "WB"}.get(m.group(), "JK"), "weak": False})
    return sorted(out, key=lambda m: m["start"])

# first match wins, so specific heads precede generic ones
CRIME_RULES = [
    ("cyber", r"cyber|information technology|\bit act\b|computer|online|internet|hacking|phishing|ransomware|sextortion|deepfake|credit card|debit card|^\s*atms?\s*$|\bi\.? ?t\.? act|^it\b|digital signature|electronic (record|evidence|signature|form)"),
    ("trafficking", r"traffick|immoral traffic|bonded labou?r|sold|buying of girls|selling of girls|importation|prostitution|procura|procuring|(buying|selling) of minor"),
    ("dowry", r"dowry"),
    ("domestic_violence", r"cruelty by husband|domestic violence|protection of women from domestic"),
    ("sexual_offence", r"rape|sexual|molest|modesty|disclosure of identity|pocso|eve.?teas|stalking|voyeur|acid attack|outraging|unnatural"),
    ("murder", r"murder|homicide|stabbed to death|shot dead|lynch|hacked to death|strangled|bludgeoned|beaten to death|done to death|slit throat"),
    ("narcotics", r"narcotic|ndps|drug|ganja|opium|heroin|cocaine|charas|brown sugar|\bmdma\b|liquor|excise|prohibition"),
    ("kidnapping", r"kidnap|abduct|missing"),
    ("robbery_dacoity", r"robbery|dacoity|dacoit|loot|chain.?snatch|highway"),
    ("theft_burglary", r"theft|burglar|stolen|house.?breaking|pickpocket|vehicle lifting|\bsteal"),
    ("fraud_economic", r"cheat|fraud|forgery|counterfeit|criminal breach of trust|embezzle|scam|ponzi|cheque|swindl|money laundering|extort|black.?mail"),
    ("corruption", r"corruption|bribe|prevention of corruption|disproportionate assets|\bacb\b"),
    ("riot_unrest", r"\brio?t|communal|mob violence|arson|unlawful assembly|stone.?pelting|clash"),
    ("hurt_assault", r"hurt|assault|grievous|beaten|attacked|stabb|thrash|cruelty|intimidat|threat"),
    ("road_accident", r"road accident|rash driving|hit.?and.?run|negligence|accident|drunk driving"),
    ("suicide", r"suicide|abetment of suicide|hanged (himself|herself)|ended (his|her) life"),
    ("arms_explosives", r"arms act|explosive|firearm|illegal weapon|country.?made|bomb|ammunition|terror|\buapa\b|unlawful activities|official secrets|offences? against (the )?state|sedition|waging war"),
    ("child_specific_offence", r"infanti ?cide|foeti ?cide|feticide|miscarriage|child marriage|child labou?r|exposure (and|&) abandonment|selling of minors|buying of minors|child abuse|juvenile justice"),
    ("crime_against_sc_st", r"scheduled caste|scheduled tribe|\bsc/?st\b|atrocit|dalit|civil rights act|untouchab|against (scs?|sts?)\b|manual scaveng"),
    ("property_damage", r"mischief|trespass|vandal|encroach|damage to public property"),
    ("environment_wildlife", r"forest|wildlife|wild life|environment|pollution|noise|green tribunal|tobacco|cigarette"),
    ("gambling_other_sll", r"gambling|copy ?right|trade ?mark|essential commodit|passport|foreigners act|customs act|electricity act|sati\b|transplantation of human|railways act|antiquities|indecent rep"),
]
_RULES = [(k, re.compile(p, re.I)) for k, p in CRIME_RULES]

CATEGORY_DOC = {  # one line per category: published as ref_categories.csv and shown to the optional LLM labeller
    "cyber": "online fraud, hacking, phishing, sextortion, deepfakes, IT Act offences", "trafficking": "human trafficking, bonded labour, immoral traffic",
    "dowry": "dowry demands, dowry deaths", "domestic_violence": "cruelty by husband or relatives, domestic violence",
    "sexual_offence": "rape, molestation, POCSO, stalking, voyeurism, acid attacks", "murder": "murder, homicide, lynching, honour killing",
    "narcotics": "drug seizures and trafficking (NDPS), illicit liquor", "kidnapping": "kidnapping, abduction, missing persons",
    "robbery_dacoity": "robbery, dacoity, loot, chain snatching", "theft_burglary": "theft, burglary, house-breaking, vehicle theft",
    "fraud_economic": "cheating, fraud, forgery, scams, extortion, money laundering", "corruption": "bribery, disproportionate assets, anti-corruption cases",
    "riot_unrest": "riots, communal clashes, arson, stone-pelting", "hurt_assault": "hurt, grievous hurt, assault, attacks", "road_accident": "road accidents, rash driving, hit-and-run",
    "suicide": "suicides and abetment of suicide", "arms_explosives": "illegal arms, explosives, terror cases (UAPA)",
    "child_specific_offence": "child marriage, child labour, infanticide, foeticide, child abuse", "crime_against_sc_st": "atrocities against Scheduled Castes / Tribes",
    "property_damage": "mischief, trespass, vandalism, damage to public property",
    "environment_wildlife": "forest, wildlife, environment, pollution and tobacco-law offences",
    "gambling_other_sll": "gambling, copyright, essential commodities and other special-law offences", "other_crime": "a real crime that fits none of the above"}
STAGES = ["incident", "arrest", "investigation", "trial", "verdict"]  # where the story sits in the criminal process

def write_reference(out):
    import pandas as pd
    pd.DataFrame({"state_code": list(STATES), "state": list(STATES.values())}).to_csv(f"{out}/ref_states.csv", index=False)
    pd.DataFrame({**CATEGORY_DOC, "all_crimes": "grand total across all heads, not one crime type (facts only)"}.items(), columns=["category", "description"]).to_csv(f"{out}/ref_categories.csv", index=False)

TOTAL = re.compile(r"^\s*(grand )?total( cognizable)?( ipc| sll| ipc & sll)?( crimes?| cases)?( against .+)?\s*$|^total (cognizable )?(ipc|sll)", re.I)

@functools.lru_cache(maxsize=None)
def crime_category(text):
    """Canonical category for a crime-head label or headline; 'other' if nothing matches, None for empty text.
    Hierarchical labels ('Group | Sub | Leaf') are judged leaf-first so a group name can't override the actual head."""
    if not isinstance(text, str) or not text.strip(): return None
    for seg in reversed(text.split(" | ")):
        for k, r in _RULES:
            if r.search(seg): return k
    return "all_crimes" if any(TOTAL.search(seg) for seg in text.split(" | ")) else "other"  # a bare 'Total' that no head claimed is a grand total, not an unknown

VICTIM_RULES = [("senior_citizens", r"senior citizen|elderly|old age"), ("children", r"against children|child victim|minor girl|minor boy|\bminor\b|\bpocso\b|\bchild\b|toddler|infant"),
                ("women", r"against women|\bwoman\b|\bwomen\b|\bwife\b|\bbride\b|\bgirl\b|housewife"), ("scheduled_castes", r"scheduled castes?|\bdalit\b"),
                ("scheduled_tribes", r"scheduled tribes?|\badivasi\b"), ("foreigners", r"foreigner|foreign national|tourist"),
                ("juvenile_offenders", r"juveniles? (in conflict|apprehended)|by juveniles")]
_VICTIMS = [(k, re.compile(p, re.I)) for k, p in VICTIM_RULES]

@functools.lru_cache(maxsize=None)
def victim_group(text):
    """Who the crime was against (or, for juvenile_offenders, who committed it), from a table title/label or headline; None if not stated."""
    return next((k for k, r in _VICTIMS if isinstance(text, str) and r.search(text)), None)

SEXAGE = re.compile(r"\b(fe)?male\b|trans ?gender|\d\s*(years?|yrs)\b", re.I)
METRIC_RULES = [  # applied to column label + table title; first match wins
    ("percentage", r"percent|\bshare\b|%"),
    ("rate", r"\brate\b|per 1,?00,?000|per lakh"),
    ("persons_convicted", r"persons? convicted|\bpcv\b"), ("persons_chargesheeted", r"persons?.*charge.?sheet|\bpcs\b"),
    ("cases_convicted", r"cases? convicted|\bcv\b"), ("cases_final_report", r"not laid|final report"),
    ("cases_chargesheeted", r"cases?.*charge.?sheet|\bcs\b"), ("persons_convicted", r"convicted|conviction"), ("persons_acquitted", r"acquit"),
    ("persons_arrested", r"arrest|apprehend|\bpar\b"),
    ("victims", r"victim|persons? (killed|injured)|deaths?\b|died|dead|suicides"),
    ("quantity_seized", r"seiz|recover"),
    ("cases_pending", r"pending"), ("cases_disposed", r"dispos|trial completed|abated|withdrawn|ended as|compounded|quashed"),
    ("cases_registered", r"cases? (registered|reported)|\bcr\b|registered|reported|incidence|cases|crimes?\b"),
]
_METRICS = [(k, re.compile(p, re.I)) for k, p in METRIC_RULES]

# NCRB's own column abbreviations (defined in the table titles); an exact match on the label's last segment beats any keyword in the title,
# which would otherwise label every CCS / CON / PART... column of a 'cases reported (CR), ...' table as cases_registered or rate.
_LEGEND = re.compile(r"\((?:cr|ccs|cs|con|cv|par|part|pcs|pcst|pcv|pcvt|pcr)\)", re.I)
ABBR = {"cr": "cases_registered", "ccs": "cases_chargesheeted", "cs": "cases_chargesheeted", "csr": "rate", "chr": "rate", "con": "cases_convicted", "cv": "cases_convicted",
        "cvr": "rate", "cncfr": "cases_final_report", "caq": "cases_acquitted", "par": "persons_arrested", "part": "persons_arrested", "pcs": "persons_chargesheeted",
        "pcst": "persons_chargesheeted", "pcv": "persons_convicted", "pcvt": "persons_convicted", "pcr": "persons_convicted",
        "i": "cases_registered", "v": "victims", "r": "rate"}  # 2019-22 tables: I(ncidents), V(ictims), R(ate) per crime head

@functools.lru_cache(maxsize=None)
def metric(label, title=""):
    if isinstance(label, str) and (a := ABBR.get(label.rsplit(" | ", 1)[-1].strip().lower())): return a
    if isinstance(label, str):
        for k, r in _METRICS:
            if r.search(label): return k
    if isinstance(title, str) and len(_LEGEND.findall(title)) < 2:  # a title that defines a whole legend '(CR), (CCS), (PART)...' says nothing about one bare column
        for k, r in _METRICS:
            if r.search(title): return k
    return "victims" if any(isinstance(x, str) and SEXAGE.search(x) for x in (label, title)) else "unknown"  # last resort: person-counts by sex / age band
