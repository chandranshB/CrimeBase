import os, tempfile
import pandas as pd
import panel

def row(**kw):
    base = dict(entity_type="state", entity="Kerala", state_code="KL", is_total=False, year=2021.0, qc="sum_ok", metric="cases_registered", format="xls", title_key="ipc crimes against women (crime head-wise & state/ut-wise)",
                column_label="Rape | I", value=10.0, wayback_timestamp="20240101000000", table_id="TABLE 3A.2", table_title="t", publisher="NCRB", source_url="u", wayback_url="w", file="ab12.xlsx")
    return {**base, **kw}

def test_all():
    rows = [row(), row(file="cd34.xlsx", wayback_timestamp="20230101000000"),  # same fact reported twice: one row
            row(column_label="Murder | I", value=5.0), row(column_label="Murder | I", value=7.0, file="x"), row(column_label="Murder | I", value=5.0, file="y"),  # disagreement: most-reported wins, flagged
            row(column_label="Male | I"), row(qc="sum_mismatch", column_label="Arson | I"), row(entity_type="district", column_label="Theft | I"),  # excluded: sex split, failed check, not a state
            row(title_key="disposal of cases by police and court under rape", column_label="Rape | I"),  # excluded: not a head-wise table
            row(column_label="Rape | V", metric="victims", value=3.0),
            # all-India: a national crime-head table, the all-India row of a state table, a state's own table and a heads-by-states table (these two are not national)
            row(entity_type="crime_head", entity="Murder", state_code=None, qc="unchecked", title_key="ipc crimes (crime head-wise)", column_label="2021 | Cases", value=29272.0, file="n1.xlsx"),
            row(entity_type="state", entity="TOTAL ALL INDIA", state_code=None, is_total=True, column_label="Robbery", year=2015.0, value=70000.0, title_key="cases registered under ipc crimes during", file="t1.xls"),
            row(entity_type="crime_head", entity="Murder", state_code=None, qc="unchecked", title_key="cases registered under ipc crimes in ut of puducherry during", column_label="2021", value=25.0, file="n2.xls"),
            row(entity_type="crime_head", entity="Murder", state_code=None, qc="unchecked", title_key="ipc crimes (crime head-wise)", column_label="Kerala", value=99.0, file="n3.xls")]
    with tempfile.TemporaryDirectory() as d:
        s, i = panel.build(pd.DataFrame(rows), d)
        assert os.path.exists(f"{d}/crime_state_year.csv") and os.path.exists(f"{d}/crime_india_year.csv")
    got = {(r.crime_head, r.metric): (r.value, r.disputed) for r in s.itertuples()}
    assert got == {("Rape", "cases_registered"): (10.0, False), ("Murder", "cases_registered"): (5.0, True), ("Rape", "victims"): (3.0, False)}, got
    assert set(s.scope) == {"women"} and s.state.iat[0] == "Kerala" and s.file.iat[0].endswith(".xlsx")
    assert {(r.year, r.crime_head, r.value, r.checked) for r in i.itertuples()} == {(2021, "Murder", 29272.0, False), (2015, "Robbery", 70000.0, True)}, i
    assert panel.head("IPC Crimes against Women (Crime Head-wise & City-wise) - 2020 | Murder (Sec.302 IPC) | A) Other | I") == "Murder (Sec.302 IPC) | A) Other"
    assert panel.key("Thefts") == "theft" and panel.key("Murder (Sec.302 IPC)") == "murder"
    assert panel.in_state("cases registered under ipc crimes in ut of puducherry during") and not panel.in_state("ipc crimes (crime head-wise)")

if __name__ == "__main__": test_all(); print("OK")
