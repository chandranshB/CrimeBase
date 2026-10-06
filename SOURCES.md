# Sources

All collection is read-only, rate-limited, and limited to public pages and files. Every output row links back to one of these.

## Government documents (via the Internet Archive's Wayback Machine, which also holds files since removed from the live sites)

| Publisher | Host | Filter |
|---|---|---|
| National Crime Records Bureau (MHA): *Crime in India*, *ADSI*, *Prison Statistics*, tables | ncrb.gov.in, ncrb.nic.in | all pdf/xls/xlsx/csv/zip/doc except procurement and training files |
| Bureau of Police Research & Development | bprd.nic.in | crime/statistics-related filenames |
| National Human Rights Commission | nhrc.nic.in | same |
| National Commission for Women | ncw.nic.in | same |
| National Commission for Protection of Child Rights | ncpcr.gov.in | same |
| Ministry of Road Transport & Highways | morth.gov.in | same |
| Narcotics Control Bureau | narcoticsindia.nic.in | same |
| Ministry of Home Affairs | mha.gov.in | same |
| Open Government Data Platform India | data.gov.in | same (carries NCRB's older open datasets) |
| Department of Justice | doj.gov.in | same |
| State and city police (Delhi, Mumbai, Kerala, Telangana, Uttar Pradesh, Haryana, Punjab, Rajasthan, Madhya Pradesh, Odisha, West Bengal, Karnataka, Chennai, Bihar, Jammu & Kashmir, Himachal Pradesh, Uttarakhand, Assam, Goa, Chhattisgarh, Jharkhand, Gujarat, Maharashtra, Tamil Nadu) | each force's own site | same, matched on the file's path, not the host name |

## Government sites as they are today (`live.py`)

The same registry is also crawled live, every run: robots.txt is honoured, one request every 2 s, same registered hosts only, conditional GETs (ETag / Last-Modified) so unchanged files are not fetched again. Files go through the same content-addressed store as the Wayback ones, so a file seen on both is stored once and both URLs are recorded in `manifest.csv` (`retrieved` holds the live fetch date). **NCRB's robots.txt currently forbids all crawling, so ncrb.gov.in is not crawled live; its documents come from the Wayback Machine.**

The registry lives in [sources.py](sources.py); adding a host there adds it to the next run.

## News (link, date, outlet, headline, the feed's own one-line summary, classification; headline and summary withheld for sensitive stories)

RSS feeds published by The Hindu, The Times of India, The Indian Express, Hindustan Times, NDTV, News18, India Today, Firstpost, Deccan Chronicle, Odisha Post, DNA India, Mid-day, The Siasat Daily, Mathrubhumi English, Scroll, Oneindia, Bar & Bench, India TV, ABP Live and Zee News (national, state and city sections), plus Wayback snapshots of those same feeds. Full article text is never collected; each row links the article and an Internet Archive lookup of it. Feeds that block automated clients (Indian Express, Firstpost) are tried but yield nothing. Feed list: [news.py](news.py).

## Place names

`places.csv` (towns, cities and districts of India with their state and population) is built from the [GeoNames](https://www.geonames.org) gazetteer, licensed CC BY 4.0, by `ci/make_places.py`. It lets the pipeline work out the state of a city, town or district from its name.

## Not used, by design

eCourts and other captcha-protected portals; Indian Kanoon (terms forbid scraping); anything requiring a login; individual FIR or victim-level records.
