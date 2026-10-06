# Contributing

Thanks for helping. Good contributions: new public, legally collectable sources; parser fixes for tables that parse wrongly; taxonomy fixes (states, crime categories, metrics); docs.

## Ground rules
- **Every row needs a source.** A new upstream goes in [sources.py](sources.py) with its publisher name and an entry in [SOURCES.md](SOURCES.md).
- **Stay legal and polite.** Respect robots.txt and rate limits. No captcha bypass, logins, or sites whose terms forbid scraping. No FIR or victim-level personal data.
- **Never redundant.** New collectors must skip content already stored (see the digest logic in `scrape.py`).
- **Accuracy over volume.** Flag uncertainty instead of guessing.

## Workflow
1. Fork, branch, and keep changes small.
2. `pip install -r requirements.txt` and `python -c "import test_taxonomy as t; t.test_all()"` must pass. Add assertions to `test_taxonomy.py` for taxonomy changes.
3. For parser changes, bump `PARSER_VERSION` in `parse.py` and say which table you checked.
4. Open a pull request using the template.

By contributing you agree your code is licensed under [AGPL-3.0](LICENSE). Commits should not carry tool-attribution trailers.
