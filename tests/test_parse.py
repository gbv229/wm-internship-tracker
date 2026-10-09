from datetime import date

from scraper import parse

TODAY = date(2026, 10, 8)


def test_season_from_titles():
    assert parse.season("2027 | Americas | Dallas Metro Area | Wealth Management, Financial Planning | Summer Analyst", "", TODAY) == ("Summer 2027", False)
    assert parse.season("Wealth Management Internship, Summer 2027 -New York (10 Weeks)", "", TODAY) == ("Summer 2027", False)
    assert parse.season("Wealth Management Summer Analyst Program - MAD- 2027", "", TODAY) == ("Summer 2027", False)
    assert parse.season("2027 Wealth & Investment Management Summer Internship - Early Careers", "", TODAY) == ("Summer 2027", False)
    assert parse.season("Fall 2026 Wealth Intern", "", TODAY) == ("Fall 2026", False)
    assert parse.season("Wealth Management Summer Intern", "", TODAY) == ("Summer 2027", True)
    assert parse.season("Private Bank Intern", "Start date: June 2027. This 10-week summer 2027 program", TODAY)[0] == "Summer 2027"


def test_class_year_from_graduation_window():
    t = ("Candidates are required to be pursuing a bachelor's degree from an accredited college or university "
         "with a graduation time frame between November 2027 and August 2028.")
    assert parse.class_years(t, "Summer 2027")[0] == [2028]
    t = "Must have an expected graduation date between December 2028 and June 2029."
    assert parse.class_years(t, "Summer 2028")[0] == [2029]
    t = "Open to students graduating in May 2028 or May 2029."
    assert parse.class_years(t, "Summer 2027")[0] == [2028, 2029]
    t = "Undergraduate students in the Class of 2029 are eligible."
    assert parse.class_years(t, "Summer 2027")[0] == [2029]


def test_class_year_from_words():
    t = "WIM Early Careers seeks to attract exceptional rising-senior students to Wealth & Investment Management."
    # "rising-senior" with a hyphen
    assert parse.class_years(t.replace("rising-senior", "rising senior"), "Summer 2027")[0] == [2028]
    t = "This program is open to current sophomores and juniors pursuing a bachelor's degree."
    assert parse.class_years(t, "Summer 2027")[0] == [2028, 2029]
    t = "The Early Insights program is for first-year and sophomore undergraduate students."
    assert parse.class_years(t, "Spring 2027")[0] == [2029, 2030]
    t = "You will partner with senior advisors and junior analysts on client work."
    assert parse.class_years(t, "Summer 2027")[0] == []


def test_deadline():
    d, ev = parse.deadline("Applications are due by November 15, 2026. Interviews follow.", TODAY)
    assert d == date(2026, 11, 15)
    d, _ = parse.deadline("The application deadline is 12/1/2026.", TODAY)
    assert d == date(2026, 12, 1)
    d, _ = parse.deadline("Please apply by January 9 to be considered.", TODAY)
    assert d == date(2027, 1, 9)
    d, _ = parse.deadline("Applications open September 1 and close October 31, 2026.", TODAY)
    assert d == date(2026, 10, 31)
    assert parse.deadline("Founded in 1935, the firm grew rapidly.", TODAY) == (None, None)


def test_relevance():
    assert parse.is_internship("Wealth Management Summer Analyst Program - MAD- 2027")
    assert parse.is_internship("2027 Private Wealth Management Summer Intern")
    assert parse.is_internship("Sophomore Early Insights Program 2027")
    assert not parse.is_internship("Internal Audit Manager")
    assert not parse.is_internship("Senior Wealth Advisor")
    assert parse.is_wealth("Summer Analyst - Private Bank", "", "mixed")
    assert not parse.is_wealth("Software Engineer Intern", "Build trading systems.", "mixed")
    assert parse.is_wealth("Client Associate Intern", "", "wealth")
    assert not parse.is_wealth("Software Engineer Intern", "", "wealth")
    assert parse.is_wealth("Summer 2027 US Wealth Management Technology Internship", "", "mixed")
    assert not parse.is_wealth("2027 Asset Management Investments - Summer Internship", "Asset & Wealth Management Asset & Wealth Management", "mixed")
    assert not parse.is_wealth("2027 Summer Internship Program - Commercial Banking", "", "mixed")
    assert parse.is_wealth("Intern", "Join Wealth Management. Our Wealth Management division serves clients.", "mixed")


def test_region():
    assert parse.region("New York, NY") == "US"
    assert parse.region("San Antonio, Texas, United States of America") == "US"
    assert parse.region("", "Wealth - LATAM, Summer Analyst, Miami - USA, 2027") == "US"
    assert parse.region("Halifax, NS") == "Canada"
    assert parse.region("Luxembourg 2 Blvd K. Adenauer") == "International"
    assert parse.region("", "Wealth - Citigold, Summer Analyst, Hong Kong, 2027") == "International"
    assert parse.region("2 Locations") == ""


def test_extras():
    assert parse.pay("The expected hourly rate is $25.00 - $32.00 per hour.") == "$25–$32/hr"
    assert parse.pay("Salary range: $85,000 to $95,000 annually") .startswith("$41–$46/hr")
    assert parse.gpa("Minimum cumulative GPA of 3.2 required.") == "3.2+"
    assert parse.gpa("GPA 3.5 or higher preferred") == "3.5+"
    assert parse.sponsorship("We are unable to sponsor visas for this role.") == "No sponsorship"
    assert parse.weeks("This 10-week program runs June to August.") == 10
    assert parse.weeks("a ten week internship") == 10
    assert parse.relative_posted("Posted 3 Days Ago", TODAY) == date(2026, 10, 5)
    assert parse.relative_posted("Posted 30+ Days Ago", TODAY) == date(2026, 9, 8)
    assert parse.level("Summer Associate - Wealth (MBA)", "") == "Graduate/MBA"
