"""Offline check of the news pipeline with a faked feed and a faked LLM: labels applied, non-crime rejected, nothing relabelled on a second run."""
import os, json, shutil, tempfile
os.environ.update(LLM_API_KEY="k", LLM_URL="http://x", LLM_MODEL="m")
import news, requests
news.OUT = tempfile.mkdtemp(); news.time.sleep = lambda s: None
RSS = b"""<rss><channel><item><title>Man held for murder of neighbour in Pune</title><link>http://a.com/1?x=1</link><pubDate>Tue, 06 Oct 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;police said&lt;/p&gt;</description></item>
<item><title>Minister slams opponents over police reforms</title><link>http://a.com/2</link><pubDate>Tue, 06 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
news.FEEDS = ["http://feed"]
class R:  # fake HTTP
    def __init__(s, c=b"", j=None, code=200): s.content, s._j, s.status_code, s.headers = c, j, code, {}
    def json(s): return s._j
    def raise_for_status(s): pass
news.get = lambda url, **kw: R(RSS)
def post(url, headers, timeout, json):
    return R(j={"choices": [{"message": {"content": '```json\n{"labels":[{"i":0,"crime":true,"category":"murder","state":"MH","victim":null,"stage":"arrest"},{"i":1,"crime":false}]}\n```'}}]})
requests.post = post
news.main()
df = news.pd.read_parquet(news.OUT + "/news.parquet"); print(df.T)
assert len(df) == 1 and df.labeller[0] == "llm" and df.state_code[0] == "MH" and df.stage[0] == "arrest" and "a.com/2" in open(news.OUT + "/news_rejected.txt").read()
assert df.summary[0] == "police said" and df.archive_url[0] == "https://web.archive.org/web/http://a.com/1"
news.main()  # second run: nothing new, nothing re-labelled, rejected item skipped
assert len(news.pd.read_parquet(news.OUT + "/news.parquet")) == 1 and len(news.pd.read_parquet(news.OUT + "/news_events.parquet")) == 1
print("OK")
