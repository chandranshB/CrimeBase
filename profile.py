"""Data profile of data/clean -> data/clean/PROFILE.md: what is actually in the published tables (coverage, gaps, label quality). Regenerated every run."""
import os, sys
import pandas as pd

def md(s, n=25): return "```\n" + s.head(n).to_string() + "\n```\n"

def main(out="data/clean"):
    L = ["# CrimeBase data profile (auto-generated)\n"]
    f = f"{out}/facts.parquet"
    if os.path.exists(f):
        d = pd.read_parquet(f, columns=["entity_type", "state_code", "parent_state_code", "is_total", "metric", "crime_category", "year", "year_source", "qc", "conflict", "publisher", "table_title", "format", "value", "column_label", "entity"])
        import pyarrow.parquet as pq
        d["state_inferred"] = pd.read_parquet(f, columns=["state_inferred"]).state_inferred if "state_inferred" in pq.read_schema(f).names else False  # absent before the place inference
        L += [f"## facts.parquet: {len(d):,} rows, years {d.year.min():.0f}-{d.year.max():.0f}, {d.conflict.mean():.1%} conflicting, {d.year.isna().mean():.1%} without a year\n",
              "### rows by entity_type\n", md(d.entity_type.value_counts()), "### rows by metric (unknown = header not understood)\n", md(d.metric.value_counts()),
              "### rows by crime_category\n", md(d.crime_category.value_counts(), 30), "### qc\n", md(d.qc.value_counts()), "### rows by publisher\n", md(d.publisher.value_counts()),
              "### rows by year_source\n", md(d.year_source.value_counts(dropna=False))]
        pl = d[d.entity_type.isin(["city", "district"]) & ~d.is_total]
        L += ["### city / district rows: how many have a state (inferred = from the place table, see DATA_DICTIONARY)\n", md(pl.groupby("entity_type", observed=True).agg(rows=("value", "size"), with_state=("parent_state_code", "count"), inferred=("state_inferred", "sum")))]
        s = d[(d.entity_type == "state") & ~d.is_total & d.state_code.notna() & (d.metric == "cases_registered")]
        L += ["### state-level cases_registered: states and categories covered per year\n", md(s.groupby("year").agg(states=("state_code", "nunique"), categories=("crime_category", "nunique"), rows=("value", "size")), 80),
              "### most common column labels whose category is still 'other' (taxonomy gaps)\n", md(d[d.crime_category == "other"].column_label.astype(str).str.split(" | ").str[-1].str[:70].value_counts(), 60),
              "### most common column labels with metric 'unknown'\n", md(d[d.metric == "unknown"].column_label.astype(str).str[:90].value_counts(), 30),
              "### most common crime_head entities still 'other'\n", md(d[(d.entity_type == "crime_head") & (d.crime_category == "other")].entity.astype(str).str[:70].value_counts(), 40),
              "### state-level cases_registered series: label, #years, #states\n", md(s.assign(lab=s.column_label.astype(str).str[:80]).groupby("lab").agg(years=("year", "nunique"), states=("state_code", "nunique"), rows=("value", "size")).sort_values("rows", ascending=False), 45),
              "### most common table titles\n", md(d.table_title.str[:90].value_counts(), 25)]
    for name, by in (("crime_state_year.csv", "state_code"), ("crime_india_year.csv", None)):
        f = f"{out}/{name}"
        if os.path.exists(f):
            t = pd.read_csv(f)
            L += [f"## {name}: {len(t):,} rows, years {t.year.min()}-{t.year.max()}, {t.disputed.mean():.1%} disputed\n", "### rows by year and scope\n", md(t.groupby(["year", "scope"]).size().unstack(fill_value=0), 40),
                  "### rows by metric\n", md(t.metric.value_counts()), "### rows by crime_category\n", md(t.crime_category.value_counts(), 30)]
            if by: L += ["### states / UTs per year\n", md(t.groupby("year")[by].nunique(), 40)]
    f = f"{out}/documents.csv"
    if os.path.exists(f):
        t = pd.read_csv(f)
        L += [f"## documents.csv: {len(t):,} stored documents, {t.bytes.sum() / 1e6:,.0f} MB\n", "### by type and parse status\n", md(t.groupby(["ext", "status"]).size(), 40),
              "### spreadsheets by year named in the URL (a year with none is a gap to fill)\n", md(t[t.ext.isin(["xls", "xlsx"])].groupby("year_hint").size(), 40)]
    f = f"{out}/news.parquet"
    if os.path.exists(f):
        n = pd.read_parquet(f)
        L += [f"## news.parquet: {len(n):,} articles, {n.cluster_id.nunique():,} events, {n.state_code.isna().mean():.1%} without a state\n", "### by labeller\n", md(n.labeller.value_counts()), "### where the state came from (headline = a state or place named in it; feed = a section feed about one state; llm)\n", md(n.state_basis.value_counts(dropna=False)),
              "### by category\n", md(n.category.value_counts(), 30), "### by publisher\n", md(n.publisher.value_counts()), "### by year\n", md(n.groupby(n.published.astype(str).str[:4]).size(), 30)]
    open(f"{out}/PROFILE.md", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))

if __name__ == "__main__": main(*sys.argv[1:])
