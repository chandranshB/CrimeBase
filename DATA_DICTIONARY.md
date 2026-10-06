# CrimeBase data dictionary

Every column of every published table is also described on Kaggle (column descriptions come from [kaggle/columns.py](kaggle/columns.py), the single source of truth). This page adds the meaning and the caveats.

## crime_state_year.csv and crime_india_year.csv - the clean tables
One row per **state/UT x year x scope x crime head x measure** (all-India for `crime_india_year.csv`). Built from `facts.parquet` by [panel.py](panel.py), with these rules:
* Only crime-head columns: sex and age-band splits stay in `facts.parquet`.
* State table: only state rows that add up (within 0.5%) to NCRB's own all-India row (`qc = sum_ok`). National table: NCRB's national crime-head tables plus the all-India row of each state table; `checked` says whether a state-sum-verified row backs the value.
* `scope` is the NCRB table family (`ipc`, `sll`, `women`, `children`, `scheduled_castes`, `scheduled_tribes`, `senior_citizens`, `juveniles`, `cyber`). The families overlap (rape appears under `ipc`, `women` and `children`), so **never add across scopes**; always filter on `scope`.
* `crime_head` is the head as NCRB prints it, parent heads first (`Murder (Sec.302 IPC) | A) Murder with Rape/POCSO`). NCRB renames heads across editions; a handful of well-known spelling variants are merged, others stay separate.
* `metric`: `cases_registered`, `cases_chargesheeted`, `cases_convicted`, `persons_arrested`, `persons_chargesheeted`, `persons_convicted`, `victims` (all-India also `rate`, per lakh population, and `percentage`, share of the table total).
* The same number reported by several files is one row. If files disagree, the value most of them report is shown and `disputed` is true.
* `file` joins to `documents.csv`. Coverage by year and scope is in `PROFILE.md`; gaps follow what NCRB published as spreadsheets and what the Wayback Machine holds.

## Places to states
A city or district row whose table printed no state (all the metropolitan-city tables, and sheets without 'State:' headings) gets its state from `places.csv`, a compact place table built from [GeoNames](https://www.geonames.org) (CC BY 4.0) by `ci/make_places.py`: towns and cities of 5,000+ people, every district and sub-district seat, and their other Latin spellings (Bombay, Madras, Gurgaon ...). NCRB's suffixes are dropped ('Ahmedabad City', 'Aurangabad Commr'). Rows filled this way have `state_inferred = true`; nothing printed in a table is ever overwritten.
* **Shared names** (Aurangabad, Bilaspur, Balrampur: two real districts in different states) are filled only when the evidence is concentrated (80% of at least 5 same-sheet places and table-title mentions point to one state), or, for the metropolitan-city tables, when one is at least 3x the size of the other. Otherwise the row stays empty rather than guessed.
* A 2010 table agrees with its own state rows: Telangana places are Andhra Pradesh before 2014, Ladakh places are Jammu and Kashmir before 2019.
* Measured by hiding the printed state of whole sheets and recovering it: about 98% correct at 80% coverage; the remaining misses are mostly mislabels in the source tables themselves. City rows with a state went from 12% to 98%.
* News uses the same table: `state_code` comes from a state or any place named in the headline (dateline first, then after 'in' / 'at'); a name shared by states is skipped unless the headline settles it. `state_basis` says how (`headline`, `feed` = the section feed is about one state or city, `llm`), `place` is the name found.

## documents.csv - the catalogue of source documents
One row per stored file: `raw_path` (where it is in `crimebase-raw`), `ext`, `bytes`, `publisher`, `title_hint`, `year_hint`, `source_url`, `wayback_url` (newest capture), `first_capture` / `last_capture`, `n_urls` (URLs that served these bytes), `status` (`facts`, `facts_low_confidence`, `no_tables_found`, `not_parsed`) and `n_facts`.

## facts.parquet — one published number per row (NCRB Excel tables, long format)
| column | meaning |
|---|---|
| file | raw file in the companion `crimebase-raw` dataset (content-addressed) |
| source_url, wayback_url, wayback_timestamp, publisher | **provenance of every row**: original URL, the Internet Archive permalink of the exact capture, capture time, and who published it |
| sheet | sheet (or `pdf`) inside the file |
| table_id, table_title | NCRB's own table number and title |
| entity_type | `state`, `district`, `city`, `crime_head`, `other` |
| entity | name exactly as printed (`TOTAL (ALL INDIA)` etc. keep `is_total=True`) |
| state_code | ISO 3166-2:IN suffix (`MH`, `DL`…) for states/UTs and cities; null if not a state |
| parent_state_code, state_inferred | for districts/cities: the state they belong to. Printed by the table, or worked out from the place name when it printed none (`state_inferred = true`, see *Places to states* below) |
| column_label | full column header, hierarchy joined with ` \| ` |
| metric | `cases_registered`, `cases_chargesheeted`, `cases_convicted`, `cases_acquitted`, `persons_arrested`, `persons_chargesheeted`, `persons_convicted`, `persons_acquitted`, `victims`, `cases_pending`, `cases_disposed`, `cases_final_report`, `rate`, `percentage`, `quantity_seized` or `unknown`. **Inferred from the header text and NCRB's own column abbreviations** (CR, CCS, CON, PART, PCST, I/V/R ...), which beat any keyword in the table title. |
| crime_category | canonical category (`murder`, `sexual_offence`, `cyber`, …) judged leaf-first from the header or crime-head row. **Inferred.** |
| year, year_source | calendar year and where it came from (`row`, `column`, `sheet`, `title`, `path`). Null when ambiguous (ranges are never guessed). |
| value | the number (rates are per lakh population as published) |
| qc | `sum_ok` / `sum_mismatch` = state rows add up (±0.5%) to NCRB's all-India row; `unchecked` = no total to test against. A mismatch is often NCRB's own inconsistency (e.g. Telangana missing in 2014). |
| n_sources, conflict | how many files reported this exact fact; `conflict` = a different file reports a different value for the same key (filter `conflict` to list them). Nothing is silently overwritten. |

## facts_pdf_lowconf.parquet - same schema, extracted from archived PDF tables (`format=pdf`)
Row entity, year and **value** are usually right, but PDFs flatten multi-line headers, so `column_label`/`metric` can be shifted by a column. Use only after checking against the source PDF (`source_url`, or `file` in `crimebase-raw`). Kept out of `facts.parquet` on purpose.

## news.parquet - one crime article per row
`url, domain, publisher, source_feed, archived_snapshot, published, category, victim_group, state_code, state_basis, place, district, stage, title, summary, sig, cluster_id, labeller, archive_url`.
* `summary` is the one-line description the publisher's own feed carries; `archive_url` opens the newest Internet Archive capture of the article if one exists (otherwise the archive offers to save it).
* `category`: one of `ref_categories.csv`. `state_code`: ISO 3166-2:IN suffix, worked out from a state or any town, city or district named in the headline (`place`; `state_basis` says how). `district`: set when that place is a district. `victim_group`: women, children, senior_citizens, scheduled_castes, scheduled_tribes, foreigners, juvenile_offenders. `stage`: where the story sits in the criminal process: `incident`, `arrest`, `investigation`, `trial`, `verdict` (filled only by the LLM pass).
* `labeller`: `rules` (keyword classifier) or `llm` (a small LLM - any OpenAI-compatible endpoint - read the headline and the feed's summary line, judged whether it is a crime story at all, and set category/state/victim group/stage; replies are validated against fixed lists, non-crime items are dropped, and every article is labelled once). Without an API key everything is `rules`, and `stage` is empty. When a key is added later, the existing `rules` rows are re-labelled gradually.
* `cluster_id` groups near-duplicate reports of the same event (same category + state, ±1 day, ≥40% headline-word overlap). Count distinct `cluster_id`, not rows, for incidents.
* `title` and `summary` are null for sexual-offence and child-victim stories (victim-identification risk). Full article text is never collected.
* News is a sample of what public feeds expose, **not** a census of crime. Classification is imperfect; filter on `labeller == 'llm'` for the cleaner subset.

## news_events.parquet - one row per distinct event (cluster)
`cluster_id, first_published, last_published, category, state_code, district, victim_group, stage, n_articles, n_publishers, publishers, example_url`. Use this for incident counts and for "how widely was it reported".

## ref_states.csv, ref_categories.csv
The code lists behind `state_code` and `category`/`crime_category`. `all_crimes` appears only in facts: a grand total across heads, not one crime type. `other` in facts means no keyword rule recognised the label.

## PROFILE.md
Auto-generated every run: row counts, years and states covered, label-quality gaps (what is still `other`/`unknown`), news volume by outlet and labeller. Read it first to know what the data can and cannot answer yet.

## Caveats
Reported crime ≠ actual crime: counts reflect registration practices that differ by state and year. Cross-year comparisons across IPC→BNS (2024+) need care. Pre-2012 data is mostly PDF-only: it is archived in `crimebase-raw` and parsed at low confidence (see above).


## Live-site rows
Facts from files fetched from a live government site (`live.py`) have empty `wayback_timestamp` / `wayback_url`; `source_url` is the live URL and `manifest.csv` (in `crimebase-raw`) records the fetch date in `retrieved`.
