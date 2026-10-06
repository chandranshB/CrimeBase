from taxonomy import CATEGORY_DOC, CRIME_RULES, state_code, crime_category, metric, victim_group

def test_all():
    assert [k for k, _ in CRIME_RULES] + ["other_crime"] == list(CATEGORY_DOC)  # every rule category is documented
    assert state_code("ORISSA") == "OD" and state_code("D&N Haveli") == "DH" and state_code("TOTAL (ALL INDIA)") is None
    assert crime_category("Offences against Property | Theft | Other Kidnapping & Abduction") == "kidnapping"  # leaf wins
    assert crime_category("Liquor contractor shot dead in Hisar") == "murder"
    assert crime_category("Rape of minor") == "sexual_offence" and crime_category("Total") == "all_crimes" and crime_category("Murder | Total") == "murder" and crime_category("Act") == "other"
    assert metric("CV") == "cases_convicted" and metric("PAR") == "persons_arrested" and metric("Rate of Crime") == "rate"
    assert victim_group("Crimes against Senior Citizens") == "senior_citizens" and victim_group("SC orders probe") is None
    assert crime_category("The Wildlife Protection Act") == "environment_wildlife" and crime_category("Credit Card/Debit Card") == "cyber" and crime_category("Criminal Intimidation") == "hurt_assault"
    assert metric("Female | Total Female") == "victims" and metric("Murder", "Cases") == "cases_registered"
    t = "Cases reported (CR), Cases Chargesheeted (CCS), Cases Convicted (CON), Persons arrested (PART) Under Crime against Women During 2014"
    assert [metric(f"Rape | {a}", t) for a in ("CR", "CCS", "CON", "PART", "CAQ", "CVR")] == ["cases_registered", "cases_chargesheeted", "cases_convicted", "persons_arrested", "cases_acquitted", "rate"]
    assert metric("Rape", t) == "unknown" and metric("Murder", "Cases registered under IPC crimes during 2011") == "cases_registered"  # a multi-measure title can't label a bare column
    assert [metric(f"Murder | {a}", "TABLE 4A.2 IPC Crimes against Children - 2021") for a in "IVR"] == ["cases_registered", "victims", "rate"]
    assert [crime_category(x) for x in ("IT - Others", "Infanti cide", "OTHER CRIMES AGAINST SC", "Commission of Sati (P) Act, 1987", "Buying of Minor Girls (Sec. 373 IPC)")] == ["cyber", "child_specific_offence", "crime_against_sc_st", "gambling_other_sll", "trafficking"]
    assert metric("2021 | Percentage Share in Total IPC Crimes") == "percentage" and metric("2021 | Crime Rate") == "rate" and metric("2021 | Cases") == "cases_registered"
