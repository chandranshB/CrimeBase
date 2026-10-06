"""Offline checks of place -> state: the resolver, headline locating, and the inference for cities / districts whose table printed no state."""
import pandas as pd
import news, parse
from taxonomy import place_state, states_in

def test_all():
    assert place_state("Ahmedabad City") == "GJ" and place_state("Bombay") == "MH" and place_state("West") is None and place_state("All Districts") is None
    assert place_state("Aurangabad") is None and place_state("Aurangabad", {"BR": 1}, min_votes=1) == "BR" and place_state("Aurangabad", metro=True) == "MH"  # shared name: context, or the big city in a table of big cities
    assert place_state("Bilaspur") is None and place_state("Bilaspur", {"HP": 6}) == "HP"
    assert place_state("Hyderabad") == "TS" and place_state("Hyderabad", year=2010) == "AP" and place_state("Leh", year=2015) == "JK"  # a 2010 table agrees with its own state rows
    assert states_in("District-wise IPC crimes in Haryana, 2019") == {"HR": 1}
    L = news.locate
    assert L("Hyderabad: Begum Bazar Businessman Attacked")[:2] == ("TS", "Hyderabad") and L("Woman beaten to death in Ghaziabad")[0] == "UP"
    assert L("Mumbai man held in UP for fraud")[0] == "UP"  # where it happened ('in UP'), not where the man is from
    assert L("Aurangabad youth held in Patna robbery")[0] == "BR" and L("Aurangabad man killed")[0] is None  # a shared name with nothing to settle it: no guess
    assert L("Sagar Dhankhar murder case: chargesheet filed")[0] is None and L("CRPF jawan dead, 5 hurt as truck rams 2 vehicles")[0] is None
    assert L("IIT Bombay to review exam rules")[0] == "MH" and L("2 held for kidnapping Navi Mum builder")[0] == "MH"
    assert L("Senior citizen loses Rs 8 lakh in scam", "https://www.hindustantimes.com/feeds/rss/cities/lucknow-news/rssfeed.xml") == ("UP", None, None, "feed")
    cat = lambda xs: pd.Series(xs, dtype="category")
    df = pd.DataFrame({"file": cat(["a", "a", "a", "b", "b", "c", "c"]), "sheet": cat(["s"] * 7), "table_title": cat(["t"] * 7),
                       "entity_type": cat(["city", "district", "district", "city", "district", "district", "district"]),
                       "entity": cat(["Bhopal", "Cuttack", "Sonepur", "Aurangabad", "Panipat", "Puri", "Sonepur"]),
                       "state_code": cat([None] * 7), "parent_state_code": cat([None, None, None, None, None, "OD", None]), "is_total": False, "year": 2020.0})
    out = parse.infer_states(df)
    got = dict(zip(zip(out.file, out.entity), out.parent_state_code))
    assert got[("a", "Bhopal")] == "MP" and out.state_code.iat[0] == "MP"  # a city's own state_code too
    assert got[("a", "Cuttack")] == "OD" and got[("b", "Aurangabad")] == "MH" and got[("b", "Panipat")] == "HR"
    assert pd.isna(got[("a", "Sonepur")]) and got[("c", "Sonepur")] is None or pd.isna(got[("c", "Sonepur")])  # two states have a Sonepur: left empty
    assert out.state_inferred.tolist() == [True, True, False, True, True, False, False]

if __name__ == "__main__": test_all(); print("OK")
