"""Every upstream the project reads, with who published it. scrape.py walks `ARCHIVE`; parse.py and news.py use `publisher()` for provenance."""
import re
from urllib.parse import urlparse

NCRB = "National Crime Records Bureau, Ministry of Home Affairs, Government of India"
# Only files whose URL *path* matches ALLOW are kept for the broader agencies (their sites are mostly circulars/notices, not data); the host name doesn't count, or every file on a police site would match 'police'.
ALLOW = re.compile(r"crime|statist|stats|annual|report|\bdata|prison|police|accident|suicide|ndps|narcotic|custod|traffick|missing|violence|atrocit|cyber|victim|terror|naxal|insurg|complaint", re.I)
ARCHIVE = {  # host (matches subdomains) -> (publisher, restrict to ALLOW?)
    "ncrb.gov.in": (NCRB, False), "ncrb.nic.in": (NCRB, False),
    "bprd.nic.in": ("Bureau of Police Research & Development, Government of India", True),
    "nhrc.nic.in": ("National Human Rights Commission, India", True),
    "ncw.nic.in": ("National Commission for Women, India", True),
    "ncpcr.gov.in": ("National Commission for Protection of Child Rights, India", True),
    "morth.gov.in": ("Ministry of Road Transport & Highways, Government of India", True),
    "narcoticsindia.nic.in": ("Narcotics Control Bureau, Government of India", True),
    "ncb.gov.in": ("Narcotics Control Bureau, Government of India", True),  # narcoticsindia.nic.in redirects here today
    "mha.gov.in": ("Ministry of Home Affairs, Government of India", True),
    "xn--i1b5bzbybhfo5c8b4bxh.xn--11b7cb3a6a.xn--h2brj9c": ("Ministry of Home Affairs, Government of India", True),  # where mha.gov.in redirects today
    "data.gov.in": ("Open Government Data Platform India, Government of India", True),  # carries NCRB's older open datasets as csv/xls
    "doj.gov.in": ("Department of Justice, Government of India", True),
    # state and city police: crime statistics, annual reports. Hosts that don't exist (or don't answer) just yield nothing.
    "delhipolice.gov.in": ("Delhi Police", True), "mumbaipolice.gov.in": ("Mumbai Police", True), "keralapolice.gov.in": ("Kerala Police", True),
    "tspolice.gov.in": ("Telangana State Police", True), "uppolice.gov.in": ("Uttar Pradesh Police", True), "haryanapolice.gov.in": ("Haryana Police", True),
    "punjabpolice.gov.in": ("Punjab Police", True), "rajasthanpolice.gov.in": ("Rajasthan Police", True), "mppolice.gov.in": ("Madhya Pradesh Police", True),
    "odishapolice.gov.in": ("Odisha Police", True), "wbpolice.gov.in": ("West Bengal Police", True), "ksp.karnataka.gov.in": ("Karnataka State Police", True),
    "chennaicitypolice.gov.in": ("Greater Chennai Police", True), "biharpolice.bih.nic.in": ("Bihar Police", True), "jkpolice.gov.in": ("Jammu & Kashmir Police", True),
    "hppolice.gov.in": ("Himachal Pradesh Police", True), "uttarakhandpolice.uk.gov.in": ("Uttarakhand Police", True), "assampolice.gov.in": ("Assam Police", True),
    "goapolice.gov.in": ("Goa Police", True), "cgpolice.gov.in": ("Chhattisgarh Police", True), "jhpolice.gov.in": ("Jharkhand Police", True),
    "police.gujarat.gov.in": ("Gujarat Police", True), "mahapolice.gov.in": ("Maharashtra Police", True), "tnpolice.gov.in": ("Tamil Nadu Police", True),
}
NEWS = {"thehindu.com": "The Hindu", "timesofindia.indiatimes.com": "The Times of India", "indianexpress.com": "The Indian Express",
        "hindustantimes.com": "Hindustan Times", "ndtv.com": "NDTV", "news18.com": "News18", "indiatoday.in": "India Today",
        "firstpost.com": "Firstpost", "deccanchronicle.com": "Deccan Chronicle", "orissapost.com": "Odisha Post",
        "dnaindia.com": "DNA India", "mid-day.com": "Mid-day", "siasat.com": "The Siasat Daily", "mathrubhumi.com": "Mathrubhumi English"}

def wanted(url): return bool(ALLOW.search(urlparse(url).path))

def site(url):
    """(publisher, restricted-to-ALLOW) of the registry host serving `url`, or None if it is not a registered upstream."""
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return next((v for h, v in ARCHIVE.items() if host == h or host.endswith("." + h)), None)

def publisher(url):
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").removeprefix("www.")
    for table in (ARCHIVE, NEWS):
        for h, v in table.items():
            if host == h or host.endswith("." + h): return v[0] if isinstance(v, tuple) else v
    return host
