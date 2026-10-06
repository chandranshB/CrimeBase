"""Offline checks of the year rule and of the district sheets: a block of districts closed by a Total row is one state, and its districts must add up to that Total."""
import numpy as np, pandas as pd
import parse

def test_all():
    Y = parse.file_year
    assert Y("x/1%20Districtwise%20IPC%20Crimes_2021.xlsx") == 2021 and Y("x/Motive%20of%20Murder%202001-12.xls") is None and Y("x/TABLE%2011.6.xlsx") is None and Y("x/t_2019.pdf") is None
    assert parse.pub_year("x/TABLE%2011.6.xlsx", "", "") == (None, None)  # '%20' + '11' is not 2011
    assert parse.pub_year("x/Districtwise_2021.xlsx", "Districtwise IPC Crimes - 2020", "") == (2021, "path")  # NCRB's copied title says 2020, the file is 2021
    import re
    m = parse.PDF_ROW.match("12 Kerala 9767 10034 11057 0.3 -- 1,234.5")  # a PDF text line: serial, name, figures
    assert m[1] == "12" and m[2] == "Kerala" and re.findall(parse.VAL, m[3]) == ["9767", "10034", "11057", "0.3", "--", "1,234.5"]
    assert parse.PDF_ROW.match("TOTAL ALL INDIA 329243 338954 100.0")[2] == "TOTAL ALL INDIA" and parse.PDF_ROW.match("1 2 3 4 5 6 7 8") is None and parse.PDF_ROW.match("Note : i) Crime Rate 2017") is None
    cat = lambda xs: pd.Series(xs, dtype="category")
    # AP: one place left unplaced (CID) and a Total; BR: Aurangabad put in MH by the place table; CH: a UT that is its own only district
    rows = [("district", "Anantapur", False, "AP", True, 10), ("district", "Chittoor", False, "AP", True, 5), ("district", "CID", False, None, False, 1), ("district", "Total", True, None, False, 16),
            ("district", "Patna", False, "BR", True, 10), ("district", "Gaya", False, "BR", True, 10), ("district", "Nalanda", False, "BR", True, 10), ("district", "Siwan", False, "BR", True, 10),
            ("district", "Aurangabad", False, "MH", True, 5), ("district", "Total", True, None, False, 45),
            ("state", "Chandigarh", False, "CH", False, 7), ("district", "Total", True, None, False, 7)]
    more = [("Imphal", "MN", True, 3), ("Thoubal", "MN", True, 4), ("Total", None, False, 7), ("Garo Hills East", None, False, 2), ("Khasi Hills West", None, False, 3), ("Total", None, False, 5),  # Meghalaya: no place name settles it,
            ("Aizawl", "MZ", True, 1), ("Lunglei", "MZ", True, 1), ("Total", None, False, 2)]  # but the sheet runs Manipur, ?, Mizoram, and only Meghalaya sits between them
    n = len(rows) + len(more)
    ent = lambda e: "Total" == e
    df = pd.DataFrame({"file": cat(["f"] * n), "sheet": cat(["s"] * len(rows) + ["o"] * len(more)), "table_title": cat(["t"] * n),
                       "entity_type": cat([r[0] for r in rows] + ["district"] * len(more)), "entity": cat([r[1] for r in rows] + [m[0] for m in more]),
                       "state_code": cat([None] * n), "parent_state_code": cat([r[3] for r in rows] + [m[1] for m in more]),
                       "is_total": [r[2] for r in rows] + [ent(m[0]) for m in more], "state_inferred": [r[4] for r in rows] + [m[2] for m in more],
                       "year": 2019.0, "metric": "cases_registered", "column_label": "Murder", "value": [float(r[5]) for r in rows] + [float(m[3]) for m in more]})
    out = parse.qc(parse.block_states(df))
    assert out.parent_state_code.astype(object).tolist() == ["AP"] * 4 + ["BR"] * 6 + ["CH"] * 2 + ["MN"] * 3 + ["ML"] * 3 + ["MZ"] * 3, out.parent_state_code.tolist()
    assert out.state_inferred.tolist()[:12] == [True, True, True, True] + [True] * 6 + [False, True] and all(out.state_inferred.tolist()[15:18])
    assert set(out.qc) == {"block_ok"}, out.qc.tolist()
    out.loc[3, "value"] = 99.0  # a Total that its districts do not add up to
    assert parse.qc(out).qc.iat[3] == "sum_mismatch"

if __name__ == "__main__": test_all(); print("OK")
