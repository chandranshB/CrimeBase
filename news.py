"""Collect crime news from Indian publishers' RSS feeds (live, and historic via Wayback snapshots of the same feeds) into
data/clean/news.parquet: one row per article, classified with taxonomy.py, located to state and place (any town, city or district), near-duplicates clustered.
Privacy: headlines and summaries are withheld for sexual-offence and child-victim stories (identification risk). Kept per article: URL, outlet, date, headline, the feed's one-line summary, labels."""
import hashlib, os, re, sys, time, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import pandas as pd, requests
from sources import publisher
from taxonomy import STATES, CATEGORY_DOC, STAGES, crime_category, victim_group, write_reference, find_places, place_state, place_candidates, states_in

H = "https://www.thehindu.com/news/"
FEEDS = ([H + p + "/feeder/default.rss" for p in ("national", "cities", "national/tamil-nadu", "national/kerala", "national/karnataka", "national/andhra-pradesh",
                                                 "national/telangana", "national/other-states", "cities/Delhi", "cities/mumbai", "cities/chennai", "cities/Hyderabad", "cities/kolkata")]
         + [f"https://timesofindia.indiatimes.com/rssfeeds/{i}.cms" for i in ("-2128936835", "2647163", "-2128839596", "-2128838597", "-2128833038", "-2128816011",
                                                                           "-2128821153", "-2128830821", "-2128817995", "-2128819658", "-2128816762", "-2128932452", "-2128821991", "3947060", "7098551")]
         + [f"https://indianexpress.com/section/{p}/feed/" for p in ("india", "cities", "cities/delhi", "cities/mumbai", "cities/pune", "cities/lucknow", "cities/chandigarh",
                                                                    "cities/ahmedabad", "cities/kolkata", "cities/bangalore", "cities/hyderabad", "cities/patna", "cities/jaipur", "cities/bhopal")]
         + [f"https://www.hindustantimes.com/feeds/rss/{p}/rssfeed.xml" for p in ("india-news", "cities", "cities/delhi-news", "cities/mumbai-news", "cities/lucknow-news",
                                                                                 "cities/bengaluru-news", "cities/kolkata-news", "cities/chandigarh-news", "cities/pune-news", "cities/ranchi-news", "cities/bhopal-news")]
         + ["https://feeds.feedburner.com/ndtvnews-india-news", "https://feeds.feedburner.com/ndtvnews-latest", "https://www.news18.com/commonfeeds/v1/eng/rss/india.xml",
            "https://www.indiatoday.in/rss/1206514", "https://www.indiatoday.in/rss/1206550", "https://www.firstpost.com/commonfeeds/v1/mfp/rss/india.xml",
            "https://www.deccanchronicle.com/rss_feed/", "https://www.orissapost.com/feed/", "https://www.dnaindia.com/feeds/india.xml",
            "https://www.mid-day.com/Resources/midday/rss/mumbai-news.xml", "https://www.siasat.com/feed/", "https://english.mathrubhumi.com/rss",
            "https://feeds.feedburner.com/ScrollinArticles.rss", "https://www.oneindia.com/rss/news-india-fb.xml", "https://www.barandbench.com/feed",
            "https://www.indiatvnews.com/rssnews/topstory-india.xml", "https://news.abplive.com/news/india/feed", "https://www.news18.com/commonfeeds/v1/eng/rss/cities.xml",
            "https://zeenews.india.com/rss/india-national-news.xml", "https://www.hindustantimes.com/feeds/rss/cities/noida-news/rssfeed.xml",
            "https://www.hindustantimes.com/feeds/rss/cities/gurugram-news/rssfeed.xml"])
CRIME = re.compile(r"arrest|murder|kill|dead|death|rape|assault|robber|theft|stolen|fraud|cheat|kidnap|abduct|loot|burglar|molest|accused|"
                   r"\bfir\b|booked|chargesheet|\bheld\b|scam|smuggl|seiz|traffick|busted|attack|lynch|stabb|shot|dowry|suicide|crime|custody|"
                   r"remand|encounter|cyber|extort|ransom|hacked|gang|police", re.I)
NOT_CRIME = re.compile(r"on democracy|cricket|box office|\bipl\b|sensex|nifty|\bmovie\b|\bfilm\b|trailer|horoscope", re.I)
OUT, DELAY = "data/clean", 3
S = requests.Session(); S.headers["User-Agent"] = "CrimeBase-archiver (public-data research; github.com/chandranshB/CrimeBase)"

def items(xml):
    try: root = ET.fromstring(xml)
    except ET.ParseError: return
    for it in root.iter("item"):
        t, l, d, sm = (it.findtext(k) for k in ("title", "link", "pubDate", "description"))
        try: d = d.strip()[:10] if re.match(r"\d{4}-\d\d-\d\d", d.strip()) else parsedate_to_datetime(d).date().isoformat()  # TOI uses ISO, others RFC 822
        except Exception:
            try: d = pd.Timestamp(d.strip()).date().isoformat()
            except Exception: continue
        if t and l: yield re.sub(r"\s+", " ", t).strip(), l.strip().split("?")[0], d, re.sub(r"<[^>]+>|\s+", " ", sm or "").strip()[:240]  # summary: the feed's own one-liner; kept unless the story is sensitive

PREPOSITION = re.compile(r"(?:^|\s)(?:in|at|near|outside|inside)\s*$", re.I)
GENERIC_FEED = {"news", "cities", "city", "national", "india", "feed", "rss", "rssfeed", "default", "other", "states", "state", "latest", "top", "stories", "english", "main"}

def feed_state(feed):
    """State a section feed is about ('.../cities/lucknow-news/rssfeed.xml' -> UP, '.../national/tamil-nadu/...' -> TN), or None for national feeds."""
    words = [w for w in re.findall(r"[a-z]+", urlparse(feed).path.lower()) if w not in GENERIC_FEED]
    for n in (3, 2, 1):
        for k in range(len(words) - n + 1):
            span = " ".join(words[k:k + n])
            st = next(iter(states_in(span)), None) or place_state(span, min_votes=1, veto=False)
            if st: return st
    return None

def locate(title, feed=""):
    """(state_code, place, district, basis) for a headline. Named states and places in it: a dateline ('Hyderabad: ...') first, then after 'in' / 'at', then the earliest.
    A place shared by several states (Aurangabad, Bilaspur) is settled by a state also named in the headline, else by size, else skipped. Failing all that, a section feed that is
    itself about one state or city ('cities/lucknow-news') supplies the state, basis 'feed'. Never a guess between equals."""
    ms = find_places(title)
    named = {}
    for m in ms:
        if m["kind"] == "state": named[m["state"]] = named.get(m["state"], 0) + 1
    def rank(m):
        dateline = title[m["end"]:].lstrip()[:1] == ":" and m["start"] < 40
        prep = bool(PREPOSITION.search(title[:m["start"]]))
        return (0 if dateline else 1 if prep else 2, m["start"]), dateline or prep
    for m in sorted(ms, key=lambda m: rank(m)[0]):
        if m["kind"] == "state": return m["state"], None, None, "headline"
        if m["weak"] and not rank(m)[1]: continue  # 'Sagar Dhankhar', a tiny town mentioned in passing
        st = place_state(m["text"], named, min_votes=1, veto=False)
        if st:
            dist = m["text"] if place_candidates(m["text"]).get(st, (0, ""))[1] == "district" else None
            return st, m["text"], dist, "headline"
    st = feed_state(feed) if feed else None
    return (st, None, None, "feed") if st else (None, None, None, None)

def sig(title):
    return " ".join(sorted({hashlib.md5(w.encode()).hexdigest()[:6] for w in re.findall(r"[a-z]{4,}", title.lower())})[:12])

def llm_on(): return bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_URL") and os.getenv("LLM_MODEL"))

def classify(rows, feed, snap=None, rejected=()):
    for t, url, d, sm in rows:
        if url in rejected: continue
        cat = crime_category(t)
        if (cat in (None, "other") and not llm_on()) or not CRIME.search(t) or NOT_CRIME.search(t): continue  # with an LLM, rule misses are kept for it to judge
        sc, place, dist, basis = locate(t, feed)
        vg = victim_group(t)
        hide = cat == "sexual_offence" or vg == "children"  # identification risk: no headline, no summary
        yield dict(url=url, domain=url.split("/")[2].removeprefix("www."), publisher=publisher(url), source_feed=feed, archived_snapshot=snap, published=d, category="other_crime" if cat == "other" else cat,
                   victim_group=vg, state_code=sc, state_basis=basis, place=place, district=dist, stage=None, title=None if hide else t, summary=None if hide or not sm else sm, sig=sig(t), labeller="rules", _t=t, _s=sm)

def cluster(df):
    """Same-day-ish reports of one event by different outlets share a cluster_id (same category+state, >=40% headline-word overlap)."""
    df = df.sort_values("published").reset_index(drop=True)
    parent = list(range(len(df)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    sets = [set(s.split()) for s in df.sig]
    day = pd.to_datetime(df.published).dt.normalize().map(pd.Timestamp.toordinal)
    for _, g in df.groupby([df.category, df.state_code.fillna("")]):
        ix, lo = list(g.index), 0  # df is date-sorted, so only a sliding +/-1 day window needs comparing
        for b, j in enumerate(ix):
            while day[ix[lo]] < day[j] - 1: lo += 1
            for i in ix[lo:b]:
                if sets[i] and sets[j] and len(sets[i] & sets[j]) / min(len(sets[i]), len(sets[j])) >= 0.4: parent[find(j)] = find(i)
    df["cluster_id"] = [hashlib.md5(df.url[find(i)].encode()).hexdigest()[:12] for i in range(len(df))]
    return df

CATS = list(CATEGORY_DOC)
GUIDE = "\n".join(f"- {k}: {v}" for k, v in CATEGORY_DOC.items())
VG = ["women", "children", "senior_citizens", "scheduled_castes", "scheduled_tribes", "foreigners", "juvenile_offenders"]

def llm_refine(rows, max_calls=100, batch=30, gap=12):
    """Optional pass (any OpenAI-compatible endpoint): a small LLM judges each headline plus the feed's summary line: is it a crime story, which
    category, which state, which victim group, how far along the criminal process. Replies are validated against fixed lists; any failure leaves
    the rule label untouched. Rows already labelled by the LLM are skipped, so each article is paid for once. gap=12s stays under free-tier limits."""
    import json
    if not llm_on(): return rows, set()
    url, model, key = os.environ["LLM_URL"], os.environ["LLM_MODEL"], os.environ["LLM_API_KEY"]
    todo = [r for r in rows if r["labeller"] != "llm" and r.get("_t")][:max_calls * batch]
    drop, fmt = set(), True
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        prompt = ("You label Indian crime-news headlines. Reply with JSON only, shaped like "
                  '{"labels": [{"i": 0, "crime": true, "category": "murder", "state": "MH", "victim": null, "stage": "arrest"}]}\n'
                  "crime: false for politics, sport, entertainment, metaphors, and accidents or disasters with no criminal angle.\n"
                  f"category, one of:\n{GUIDE}\n"
                  "state: ISO 3166-2:IN suffix of the state/UT where it happened (MH, DL, ...), or null if unclear.\n"
                  f"victim: one of {VG} or null.\nstage: one of {STAGES} (incident = just reported; verdict = conviction, acquittal or sentence).\n"
                  "Headlines:\n" + "\n".join(f"{n}. {r['_t']}" + (f" -- {r['_s']}" if r.get("_s") else "") for n, r in enumerate(chunk)))
        for attempt in range(4):
            time.sleep(gap)
            try:
                body = {"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}
                if fmt: body["response_format"] = {"type": "json_object"}
                r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, timeout=90, json=body)
                if r.status_code == 429: time.sleep(min(float(r.headers.get("retry-after", 30)), 120)); continue
                if r.status_code == 400 and fmt: fmt = False; continue  # endpoint without JSON mode: the prompt alone asks for JSON
                r.raise_for_status()
                txt = re.sub(r"^```(?:json)?|```$", "", r.json()["choices"][0]["message"]["content"].strip()).strip()
                for l in json.loads(txt)["labels"]:
                    row = chunk[l["i"]]
                    if l.get("crime") is False: drop.add(row["url"]); continue
                    if l.get("category") in CATS: row["category"] = l["category"]
                    if l.get("state") in STATES: row["state_code"], row["state_basis"] = l["state"], "llm"
                    if l.get("victim") in VG: row["victim_group"] = l["victim"]
                    if l.get("stage") in STAGES: row["stage"] = l["stage"]
                    row["labeller"] = "llm"
                break
            except (requests.RequestException, KeyError, ValueError, IndexError, TypeError) as e:
                print("llm batch skipped:", type(e).__name__)
                break
    return [r for r in rows if r["url"] not in drop], drop

def events(df):
    """One row per real-world event (cluster): how widely and for how long it was reported, and by whom."""
    mode = lambda s: s.mode().iat[0] if s.notna().any() else None
    e = df.groupby("cluster_id").agg(first_published=("published", "min"), last_published=("published", "max"), category=("category", mode), state_code=("state_code", mode),
                                     district=("district", mode), victim_group=("victim_group", mode), stage=("stage", "max"), n_articles=("url", "size"),
                                     n_publishers=("publisher", "nunique"), publishers=("publisher", lambda s: ", ".join(sorted(set(s)))), example_url=("url", "first"))
    return e.reset_index()

def get(url, **kw):
    for i in range(5):
        time.sleep(DELAY)
        try:
            r = S.get(url, timeout=60, **kw)
            if r.status_code == 200: return r
            if r.status_code in (403, 404): return None
        except requests.RequestException: pass
        time.sleep(20 * 2 ** i)

def main(backfill=False, budget=5 * 3600):
    os.makedirs(OUT, exist_ok=True)
    t0, new = time.time(), []
    seen_f = f"{OUT}/news_snapshots.txt"
    seen = set(open(seen_f).read().split()) if os.path.exists(seen_f) else set()
    rej = set(open(f"{OUT}/news_rejected.txt").read().split()) if os.path.exists(f"{OUT}/news_rejected.txt") else set()
    for feed in FEEDS:
        if not backfill:
            r = get(feed)
            got = list(classify(items(r.content), feed, rejected=rej)) if r else []
            print(f"{len(got):4d} kept  {'ok ' if r else 'FAILED'} {feed}"); new += got  # a blocked feed shows up here instead of silently yielding nothing
            continue
        c = get("https://web.archive.org/cdx/search/cdx", params={"url": feed, "output": "json", "fl": "timestamp", "filter": "statuscode:200", "collapse": "timestamp:8"})
        for (ts,) in (c.json()[1:] if c else []):
            if f"{feed}@{ts}" in seen: continue
            if time.time() - t0 > budget: break
            r = get(f"https://web.archive.org/web/{ts}id_/{feed}")
            if r: new += classify(items(r.content), feed, f"https://web.archive.org/web/{ts}/{feed}", rejected=rej)
            seen.add(f"{feed}@{ts}")
    f, rf = f"{OUT}/news.parquet", f"{OUT}/news_rejected.txt"
    old = pd.read_parquet(f).drop(columns="cluster_id") if os.path.exists(f) else pd.DataFrame()
    if len(old):
        for c in ("place", "state_basis"):
            if c not in old: old[c] = None
        old.loc[old.state_code.notna() & old.state_basis.isna(), "state_basis"] = "headline"  # set by the earlier, narrower locator from the headline
        for i in old.index[old.state_code.isna() & old.title.notna()]:  # the places we know have grown since: look again
            sc, place, dist, basis = locate(old.at[i, "title"], old.at[i, "source_feed"] or "")
            if sc: old.loc[i, ["state_code", "place", "district", "state_basis"]] = [sc, place, dist, basis]
    have = set(old.url) if len(old) else set()
    new = list({r["url"]: r for r in new if r["url"] not in have}.values())  # feeds repeat items for days: label each article once
    back = [dict(r, _t=r["title"], _s=None) for r in old.to_dict("records") if r["labeller"] != "llm" and r["title"]] if llm_on() else []  # enabling the LLM later relabels the backlog
    rows, drop = llm_refine(new + back)
    open(rf, "w").write("\n".join(sorted(rej | drop)))
    open(seen_f, "w").write("\n".join(sorted(seen)))
    final = {r["url"]: r for r in old.to_dict("records") if r["url"] not in drop}
    final.update({r["url"]: {k: v for k, v in r.items() if not k.startswith("_")} for r in rows})
    if not final: return print("no news")
    df = cluster(pd.DataFrame(list(final.values())))
    if "summary" not in df: df["summary"] = None
    df["archive_url"] = "https://web.archive.org/web/" + df.url  # resolves to the newest Wayback capture if one exists
    df.to_parquet(f, index=False)
    ev = events(df); ev.to_parquet(f"{OUT}/news_events.parquet", index=False)
    write_reference(OUT)
    print(len(df), "articles;", len(ev), "distinct events;", (df.labeller == "llm").sum(), "LLM-labelled;", len(drop), "rejected as not crime")

if __name__ == "__main__": main(backfill="backfill" in sys.argv)
