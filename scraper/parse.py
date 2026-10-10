"""Turn raw posting text into structured fields.

Everything here is a pure function of the posting text so it can be unit
tested. When a field can't be found it is left as None and the site shows
"Not stated" -- nothing is guessed beyond what the posting says, except the
season year, which is marked `season_inferred` when it is filled in from the
posted date.
"""
from __future__ import annotations

import html as htmllib
import re
from datetime import date, datetime, timedelta

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MONTH_RE = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
            r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
SEASONS = ["Winter", "Spring", "Summer", "Fall"]
GRAD_CONTEXT = re.compile(r"(?i)graduat|class of|degree (completion|conferral)|expected to complete|complete (your|their) degree|receive (your|their) degree")


# --------------------------------------------------------------------- text
def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmllib.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])|\n+", text)
    return [p.strip() for p in parts if p.strip()]


# --------------------------------------------------------------- relevance
INTERN_RE = re.compile(
    r"\b(intern(ship)?s?|summer analysts?|summer associates?|co-?ops?|externships?|"
    r"sophomores?|freshm[ae]n|first[- ]year students?|early insights?|insight (day|week|program|series)|"
    r"spring (week|insight)|discovery (day|program)|explore program|launch program|"
    r"pre-?internship|winter analysts?|fall analysts?|off-?cycle)\b", re.I)
NOT_INTERN_RE = re.compile(
    r"\b(internal|international|senior (vice president|associate|manager)|director|"
    r"intern(al)? audit|internally)\b", re.I)
WEALTH_RE = re.compile(
    r"(wealth|private bank|private client|private wealth|financial advis[eo]r|"
    r"financial planning|financial plann?er|client associate|advisor development|"
    r"\bpwm\b|\bwm\b|\bawm\b|family office|trust (and|&) estate|trust management|"
    r"high[- ]net[- ]worth|\bhnw\b|\buhnw\b|personal trust|investment advis)", re.I)
MBA_RE = re.compile(r"\b(mba|summer associate|graduate (student|program)|master'?s student|ph\.?d)\b", re.I)


def is_internship(title: str, text_head: str = "") -> bool:
    t = title or ""
    if INTERN_RE.search(t) and not re.fullmatch(r"(?i).*\binternal\b.*", t):
        return True
    # titles like "2027 Wealth Management Program" -> check the opening text
    if re.search(r"\b20\d\d\b", t) and re.search(r"(?i)program|analyst", t):
        return bool(INTERN_RE.search(text_head[:1500]))
    return False


# Strong signals used when reading a description (boilerplate like
# "retirement plans" or "relationship" is too common to count there).
WEALTH_STRONG_RE = re.compile(r"(wealth management|private bank|private wealth|private client|financial advis[eo]r|"
                              r"wealth & investment|wealth and investment|global wealth|wealth division)", re.I)
# Titles that clearly belong to another division or to pure tech roles
OTHER_DIVISION_RE = re.compile(
    r"(investment banking|corporate bank|commercial bank|global markets|sales (and|&) trading|\bmarkets\b|"
    r"asset management|\bgam\b|quant|software|engineer|developer|data scien|cyber|\bit\b|technology|"
    r"audit|accounting|tax\b|legal|human resources|\bhr\b|people partner|marketing|treasury|real estate|"
    r"forestry|insurance|actuar|underwrit|lending|credit|research analyst|equity research|fraud|crypto|"
    r"financial institutions|institutional|restructuring|\bm&a\b|mergers|capital markets|leveraged|"
    r"private equity|asset servicing|custody|fund services|chief operations|corporate finance|"
    r"social media|communications|conference|hospitality|event|sustainab|model risk|third-party risk|"
    r"operational risk|enterprise risk|facilities|procurement|graphic|creative|design|talent|"
    r"\bai\b|machine learning)", re.I)


def is_wealth(title: str, text: str, focus: str) -> bool:
    t = title or ""
    if WEALTH_RE.search(t):
        return True
    if OTHER_DIVISION_RE.search(t):
        return False
    if focus == "wealth":
        return True
    # A generic title ("Summer Analyst", "Intern") at a big firm counts when
    # the opening of the posting is about wealth management.
    head = (text or "")[:1200]
    return len(WEALTH_STRONG_RE.findall(head)) >= 2


# ------------------------------------------------------------ real estate
# At banks and insurers only explicit real estate wording counts
RE_STRICT_TITLE_RE = re.compile(
    r"(real estate|\bcre\b|realty|\breits?\b|multifamily|multi-family|commercial mortgage|cmbs|"
    r"propert(y|ies) (finance|lending|investment)|real assets)", re.I)
RE_STRONG_RE = re.compile(
    r"(commercial real estate|real estate (investment|development|finance|lending|banking|brokerage|services|"
    r"private equity|capital markets)|\breits?\b|multifamily|property management|leasing|"
    r"investment properties|real assets)", re.I)
# Roles at real estate firms that aren't real estate finance/investing work
RE_OTHER_RE = re.compile(
    r"(software|\bengineer|\bdeveloper\b|data scien|cyber|\bit\b|information technology|human resources|\bhr\b|"
    r"people (partner|team)|talent acquisition|recruit|legal|paralegal|audit|tax\b|graphic design|"
    r"marketing|social media|communications|maintenance|technician|hvac|janitor|custodial|housekeep|"
    r"porter|groundskeep|security officer|electrician|plumb|mechanic|culinary|cook|"
    r"front desk|concierge|call center|customer service|payroll|benefits|technology intern|\bai\b|"
    r"machine learning|computer science|information services|digital product|product analy|"
    r"interior design|architecture|\bdesign\b)", re.I)


def is_real_estate(title: str, text: str, focus: str) -> bool:
    t = title or ""
    if RE_OTHER_RE.search(t):
        return False
    if focus == "real_estate":
        return True
    if RE_STRICT_TITLE_RE.search(t):
        return True
    if WEALTH_RE.search(t):
        return False
    head = (text or "")[:1200]
    return bool(re.search(r"(?i)\b(summer analyst|intern|internship)\b", t)) and len(RE_STRONG_RE.findall(head)) >= 2 \
        and not re.search(r"(?i)investment banking|sales (and|&) trading|global markets", t)


def tracks_for(title: str, text: str, focus: str, tracks: list[str]) -> list[str]:
    """Which tracks ("wealth", "real_estate") this posting belongs to."""
    out = []
    if "wealth" in tracks and is_wealth(title, text, focus if focus in ("wealth", "mixed") else "mixed"):
        out.append("wealth")
    if "real_estate" in tracks and is_real_estate(title, text, focus):
        out.append("real_estate")
    return out


US_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
             "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
US_STATE_NAMES = ("alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|"
                  "idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|"
                  "minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|"
                  "new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|"
                  "south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|"
                  "wisconsin|wyoming")
CA_RE = re.compile(r"(,\s*(ON|BC|AB|QC|NS|NB|MB|SK|PE|NL)\b|\bcanada\b|toronto|vancouver|montreal|calgary|ottawa|halifax)", re.I)
INTL_RE = re.compile(
    r"(london|united kingdom|\buk\b|dublin|ireland|paris|france|frankfurt|germany|luxembourg|geneva|zurich|zürich|"
    r"switzerland|milan|milano|italy|madrid|spain|amsterdam|netherlands|brussels|singapore|hong kong|tokyo|japan|"
    r"sydney|australia|india|mumbai|bengaluru|bangalore|dubai|uae|abu dhabi|riyadh|saudi|mexico|são paulo|"
    r"sao paulo|brazil|buenos aires|chile|colombia|warsaw|poland|budapest|prague|stockholm|monaco|jersey channel|"
    r"emea|apac|latam(?! .*usa)|bahrain|qatar|doha|shanghai|beijing|china|taipei|seoul|korea|manila|"
    r"kuala lumpur|bertrange|glasgow|edinburgh|birmingham, uk)", re.I)


# ------------------------------------------------------------- US regions
REGIONS = ["Northeast", "Mid-Atlantic", "Southeast", "Midwest", "Southwest", "West"]
STATE_REGION = {}
for _r, _codes in {
    "Northeast": "CT ME MA NH RI VT NY NJ PA",
    "Mid-Atlantic": "DE MD DC VA WV",
    "Southeast": "NC SC GA FL AL MS TN KY AR LA",
    "Midwest": "OH IN IL MI WI MN IA MO KS NE ND SD",
    "Southwest": "TX OK NM AZ",
    "West": "CA OR WA NV UT CO ID MT WY AK HI",
}.items():
    for _c in _codes.split():
        STATE_REGION[_c] = _r
STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
# Cities that often appear without a state ("Fort Mill/Charlotte", "Dallas Metro Area", "Miami - USA")
CITY_STATE = {
    "new york": "NY", "nyc": "NY", "manhattan": "NY", "brooklyn, ny": "NY", "albany": "NY", "buffalo": "NY",
    "rochester, ny": "NY", "syracuse": "NY", "white plains": "NY", "uniondale": "NY", "jericho": "NY",
    "boston": "MA", "cambridge, ma": "MA", "hartford": "CT", "stamford": "CT", "greenwich": "CT",
    "providence": "RI", "philadelphia": "PA", "pittsburgh": "PA", "king of prussia": "PA", "malvern": "PA",
    "radnor": "PA", "conshohocken": "PA", "jersey city": "NJ", "newark": "NJ", "princeton": "NJ",
    "washington, d.c": "DC", "washington d.c": "DC", "washington, dc": "DC", "washington dc": "DC",
    "baltimore": "MD", "bethesda": "MD", "mclean": "VA", "tysons": "VA", "richmond, va": "VA",
    "wilmington, de": "DE", "charlotte": "NC", "fort mill": "SC", "raleigh": "NC", "durham": "NC",
    "atlanta": "GA", "miami": "FL", "tampa": "FL", "orlando": "FL", "jacksonville": "FL",
    "st. petersburg": "FL", "st petersburg": "FL", "boca raton": "FL", "west palm beach": "FL",
    "palm beach": "FL", "fort lauderdale": "FL", "nashville": "TN", "memphis": "TN", "louisville": "KY",
    "birmingham, al": "AL", "new orleans": "LA", "chicago": "IL", "detroit": "MI", "cleveland": "OH",
    "columbus, oh": "OH", "cincinnati": "OH", "indianapolis": "IN", "milwaukee": "WI", "minneapolis": "MN",
    "st. paul": "MN", "saint paul": "MN", "st. louis": "MO", "saint louis": "MO", "st louis": "MO",
    "kansas city": "MO", "overland park": "KS", "omaha": "NE", "des moines": "IA", "dallas": "TX",
    "houston": "TX", "austin": "TX", "san antonio": "TX", "fort worth": "TX", "plano": "TX",
    "westlake, tx": "TX", "phoenix": "AZ", "scottsdale": "AZ", "tempe": "AZ", "oklahoma city": "OK",
    "tulsa": "OK", "denver": "CO", "salt lake city": "UT", "las vegas": "NV", "los angeles": "CA",
    "century city": "CA", "irvine": "CA", "orange county": "CA", "newport beach": "CA",
    "san francisco": "CA", "san diego": "CA", "san jose": "CA", "sunnyvale": "CA", "palo alto": "CA",
    "menlo park": "CA", "seattle": "WA", "bellevue, wa": "WA", "portland, or": "OR", "honolulu": "HI",
}
_STATE_CODE_RE = re.compile(r"(?:^|[\s,(/|-])(" + "|".join(STATE_REGION) + r")(?=$|[\s,)/|.-])")
_STATE_NAME_RE = re.compile(r"\b(" + "|".join(sorted(STATE_NAMES, key=len, reverse=True)) + r")\b", re.I)
_CITY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in sorted(CITY_STATE, key=len, reverse=True)) + r")\b", re.I)
MORE_INTL_RE = re.compile(
    r"(?i)\b(greece|athens|denmark|copenhagen|vietnam|hanoi|ho chi minh|belgium|bruxelles|sweden|norway|oslo|"
    r"finland|helsinki|austria|vienna|portugal|lisbon|israel|tel aviv|south africa|johannesburg|new zealand|"
    r"auckland|indonesia|jakarta|thailand|bangkok|malaysia|turkey|istanbul|egypt|cairo|nigeria|lagos|kenya|"
    r"nairobi|peru|lima|argentina|uruguay|panama|cayman|bermuda|bahamas|guernsey|czech|philippines|"
    r"netherlands|hungary|romania|bucharest|slovakia|croatia|cyprus|malta|morocco|kuwait|oman|pakistan|"
    r"bangladesh|sri lanka|vietnam|neuilly|gurgaon|gurugram|hyderabad|chennai|pune|telangana)\b")
_US_RE = re.compile(r"(?i)united states|\busa?\b|\bu\.s\.(a\.)?")
_REMOTE_RE = re.compile(r"(?i)\bremote\b|work from home|virtual")


def _states_in(seg: str) -> set[str]:
    found = set()
    # "Washington, DC" must not also count as Washington state
    rest = re.sub(r"(?i)washington,? d\.?c\.?|district of columbia", " DC ", seg)
    for m in _STATE_CODE_RE.finditer(rest):
        found.add(m.group(1))
    for m in _STATE_NAME_RE.finditer(rest):
        found.add(STATE_NAMES[m.group(1).lower()])
    if not found:
        # only fall back to city names when no state is written ("Albany, OR" is Oregon)
        for m in _CITY_RE.finditer(seg):
            found.add(CITY_STATE[m.group(1).lower()])
    return found


def regions(location: str, title: str = "") -> list[str]:
    """US regions (Northeast, Mid-Atlantic, Southeast, Midwest, Southwest,
    West), plus "Remote", "US" (US but no state given), "Canada" and
    "International". A posting with several locations gets several."""
    out: set[str] = set()
    us_generic = False
    for seg in re.split(r";|\n|\s\|\s", location or ""):
        seg = seg.strip()
        if not seg or re.fullmatch(r"(?i)\d+\s+locations?", seg):
            continue
        states = _states_in(seg)
        if states:
            out.update(STATE_REGION[s] for s in states)
        elif CA_RE.search(seg):
            out.add("Canada")
        elif INTL_RE.search(seg) or MORE_INTL_RE.search(seg) or re.search(r"CW Site - (?!USA\b)[A-Z]{2,3}\b", seg):
            out.add("International")
        elif _US_RE.search(seg):
            us_generic = True
        if _REMOTE_RE.search(seg) and (states or _US_RE.search(seg) or not (CA_RE.search(seg) or INTL_RE.search(seg))):
            out.add("Remote")
    if not out - {"Remote"}:
        # nothing usable in the location: titles often carry it ("Capital Markets Internship - Atlanta, GA")
        t = title or ""
        states = {m.group(1) for m in re.finditer(r",\s*(" + "|".join(STATE_REGION) + r")\b", t)}
        states |= {CITY_STATE[m.group(1).lower()] for m in _CITY_RE.finditer(t)}
        if states:
            out.update(STATE_REGION[s] for s in states)
        elif CA_RE.search(t):
            out.add("Canada")
        elif INTL_RE.search(t):
            out.add("International")
        elif _US_RE.search(t) or us_generic:
            us_generic = True
    if us_generic and not (out & set(REGIONS)):
        out.add("US")
    order = REGIONS + ["Remote", "US", "Canada", "International"]
    return [r for r in order if r in out]


def region(location: str, title: str = "") -> str:
    """US / Canada / International / '' (unknown)."""
    loc = location or ""
    s = f"{loc} {title or ''}"
    if re.search(r"(?i)united states|\busa\b|\bu\.s\.", s):
        return "US"
    if re.search(r",\s*(" + "|".join(US_STATES) + r")\b", loc) or re.search(r"(?i)\b(" + US_STATE_NAMES + r")\b", loc):
        return "US"
    if CA_RE.search(s):
        return "Canada"
    if INTL_RE.search(s):
        return "International"
    if re.search(r"(?i)\b(new york|chicago|boston|charlotte|philadelphia|dallas|houston|miami|atlanta|san francisco|"
                 r"los angeles|denver|seattle|pittsburgh|baltimore|st\.? louis|minneapolis|nashville|remote - us)\b", s):
        return "US"
    return ""


def level(title: str, text: str) -> str:
    if MBA_RE.search(title or ""):
        return "Graduate/MBA"
    if MBA_RE.search((text or "")[:600]) and not re.search(r"(?i)undergrad|bachelor", (text or "")[:1500]):
        return "Graduate/MBA"
    return "Undergraduate"


FUNCTION_RULES = [
    ("Advisory / Client Service", r"advis|client associate|client service|relationship|private bank|private client|planning"),
    ("Investments", r"invest|portfolio|research|analyst program|trading|asset management|markets"),
    ("Operations", r"operations|\bops\b|middle office|back office|trust admin"),
    ("Technology / Data", r"technolog|software|engineer|developer|\bdata\b|\bit\b|cyber|digital|\bai\b"),
    ("Sales / Marketing", r"sales|distribution|marketing|business development"),
    ("Risk / Compliance", r"risk|compliance|audit|legal|control"),
]


RE_FUNCTION_RULES = [
    ("Capital Markets / Investment Sales", r"capital markets|investment sales|debt (and|&) equity|\bdebt\b|equity placement"),
    ("Leasing / Brokerage", r"leasing|brokerage|broker|tenant|landlord|agency"),
    ("Acquisitions / Investments", r"acquisition|invest|private equity|fund|portfolio|underwrit"),
    ("Development / Construction", r"develop|construct|project manag|design|planning"),
    ("Asset / Property Management", r"asset manag|property manag|operations|facilit|portfolio manag"),
    ("Lending / Mortgage", r"lend|loan|mortgage|cmbs|credit|servicing|originat"),
    ("Valuation / Research", r"valuation|apprais|research|analytics|market (analy|research)|data"),
]


def function(title: str, track: str = "wealth") -> str:
    if track == "real_estate":
        for name, pat in RE_FUNCTION_RULES:
            if re.search(pat, title or "", re.I):
                return name
        return "Real Estate (general)"
    for name, pat in FUNCTION_RULES:
        if re.search(pat, title or "", re.I):
            return name
    return "Wealth Management"


# ------------------------------------------------------------------ season
SEASON_WORD = r"(summer|fall|autumn|winter|spring)"


def season(title: str, text: str, posted: date | None) -> tuple[str | None, bool]:
    """Return ("Summer 2027", inferred?)."""
    # graduation sentences ("graduating between December 2027 and Summer 2028")
    # describe the student, not the program, so they're left out here
    body = " ".join(x for x in sentences((text or "")[:4000]) if not GRAD_CONTEXT.search(x))
    title_year = re.search(r"\b(20\d\d)\b", title or "")
    for src in (title or "", body):
        m = re.search(SEASON_WORD + r"[\s,/-]*(?:of\s+)?(20\d\d)", src, re.I)
        if m and src is body and title_year and m.group(2) != title_year.group(1):
            m = None  # e.g. a 2027 externship mentioning the "Summer 2028 internship" it leads to
        if m:
            return f"{_season_name(m.group(1))} {m.group(2)}", False
        m = re.search(r"(20\d\d)[\s|,/-]+(?:[\w&|,/ -]{0,80}?\b)?" + SEASON_WORD, src, re.I)
        if m and src is title:
            return f"{_season_name(m.group(2))} {m.group(1)}", False
    # "Winter Co-op 2027": a few words between season and year, title only
    m = re.search(SEASON_WORD + r"(?:[\s-]+[A-Za-z&/-]+){1,3}[\s,/-]+(20\d\d)\b", title or "", re.I)
    if m:
        return f"{_season_name(m.group(1))} {m.group(2)}", False
    # "2027 Summer Analyst" style where the year and season are far apart
    ty = re.search(r"\b(20\d\d)\b", title or "")
    if ty and re.search(r"(?i)summer|analyst program|internship program", title or ""):
        return f"Summer {ty.group(1)}", False
    m = re.search(r"(?i)\bsummer (analyst|intern|internship|associate)", title or "")
    if m or re.search(r"(?i)\bsummer\b", title or ""):
        return _infer("Summer", posted), True
    for s in ("Fall", "Winter", "Spring"):
        if re.search(rf"(?i)\b{s}\b", title or ""):
            return _infer(s, posted), True
    # season named only in the description ("our summer internship program")
    m = re.search(r"(?i)\b(summer|fall|winter|spring)\s+(internship|intern|analyst|program|co-?op)", body)
    if m:
        return _infer(_season_name(m.group(1)), posted), True
    return None, False


def _season_name(w: str) -> str:
    w = w.lower()
    return "Fall" if w in ("fall", "autumn") else w.capitalize()


def _infer(s: str, posted: date | None) -> str:
    """The next occurrence of season `s` after the posting date."""
    p = posted or date.today()
    start_month = {"Winter": 1, "Spring": 3, "Summer": 6, "Fall": 9}[s]
    y = p.year
    if s == "Summer":
        # Summer internships are recruited 9-12 months ahead
        y = p.year + (1 if p.month >= 6 else 0)
    elif p.month >= start_month:
        y += 1
    return f"{s} {y}"


# ----------------------------------------------------------- class year
def _parse_month_year(s: str) -> list[tuple[int, int]]:
    out = []
    for m in re.finditer(MONTH_RE + r"\.?\s*,?\s*(?:\d{1,2}(?:st|nd|rd|th)?,?\s*)?(20\d\d)", s, re.I):
        out.append((int(m.group(2)), MONTHS[_mkey(m.group(1))]))
    for m in re.finditer(r"\b(0?[1-9]|1[0-2])/(20\d\d)\b", s):
        out.append((int(m.group(2)), int(m.group(1))))
    return out


def _classes_from_window(lo: tuple[int, int], hi: tuple[int, int]) -> list[int]:
    """Graduation classes whose Dec..Aug graduation season overlaps [lo, hi]."""
    classes = []
    for y in range(lo[0] - 1, hi[0] + 2):
        season_lo, season_hi = (y - 1, 12), (y, 8)
        if season_lo <= hi and lo <= season_hi:
            classes.append(y)
    return classes




def class_years(text: str, season_label: str | None) -> tuple[list[int], str | None]:
    """Return (sorted class years, evidence sentence)."""
    text = text or ""
    found: set[int] = set()
    evidence = None

    for sent in sentences(text):
        if not GRAD_CONTEXT.search(sent):
            continue
        for m in re.finditer(r"(?i)class(?:es)? of\s*'?(20\d\d|\d\d)\b(?:\s*(?:and|or|&|,|/)\s*'?(20\d\d|\d\d))?", sent):
            for g in m.groups():
                if g:
                    found.add(int(g) if len(g) == 4 else 2000 + int(g))
        dates = _parse_month_year(sent)
        if len(dates) >= 2:
            dates.sort()
            found.update(_classes_from_window(dates[0], dates[-1]))
        elif len(dates) == 1:
            y, mo = dates[0]
            found.update(_classes_from_window((y, mo), (y, mo)))
        elif not found:
            ys = [int(y) for y in re.findall(r"\b(20[2-3]\d)\b", sent)]
            if 1 <= len(ys) <= 2 and re.search(r"(?i)graduat\w*\s+(in|by|between|from|date)", sent):
                found.update(range(min(ys), max(ys) + 1))
        if found:
            evidence = sent
            break

    if not found and season_label:
        found, ev = _class_from_words(text, season_label)
        evidence = evidence or ev
    return sorted(found), _trim(evidence)


def _class_from_words(text: str, season_label: str) -> tuple[set[int], str | None]:
    """'rising juniors', 'sophomores and juniors' -> class years, relative to
    the program's own season (a Summer 2027 sophomore program = class of 2029)."""
    try:
        s_name, s_year = season_label.split()
        s_year = int(s_year)
    except ValueError:
        return set(), None
    # During a fall/winter/spring term the student is in the academic year
    # that ends the following spring; summer programs sit after year end.
    ay_end = s_year if s_name in ("Summer", "Spring", "Winter") else s_year + 1
    if s_name == "Summer":
        rising = {"sophomore": ay_end + 3, "junior": ay_end + 2, "senior": ay_end + 1}
        current = {"freshman": ay_end + 3, "first-year": ay_end + 3, "sophomore": ay_end + 2,
                   "junior": ay_end + 1, "senior": ay_end}
    else:
        rising = {"sophomore": ay_end + 2, "junior": ay_end + 1, "senior": ay_end}
        current = {"freshman": ay_end + 3, "first-year": ay_end + 3, "sophomore": ay_end + 2,
                   "junior": ay_end + 1, "senior": ay_end}
    found: set[int] = set()
    evidence = None
    for sent in sentences(text):
        if not re.search(r"(?i)freshm|first-year|sophomore|junior|senior", sent):
            continue
        if not re.search(r"(?i)student|undergrad|candidate|year|standing|applicant|eligib|program|intern|college|university|rising|currently", sent):
            continue
        hits: set[int] = set()
        s = sent
        for m in re.finditer(r"(?i)rising (sophomore|junior|senior)s?", s):
            hits.add(rising[m.group(1).lower()])
        s = re.sub(r"(?i)rising (sophomore|junior|senior)s?", " ", s)
        # senior/junior as job ranks ("senior advisor", "junior analyst") are not class years
        s = re.sub(r"(?i)\b(senior|junior)\s+(vice|managing|associate|analyst|advisor|adviser|banker|manager|director|leader|partner|staff|management|executive|team|level|role)s?\b", " ", s)
        for m in re.finditer(r"(?i)\b(freshm[ae]n|first-year|sophomores?|juniors?|seniors?)\b", s):
            w = m.group(1).lower().rstrip("s")
            w = "freshman" if w.startswith("freshm") else w
            if w in current:
                hits.add(current[w])
        if hits:
            found |= hits
            evidence = evidence or sent
    return found, evidence


def _trim(s: str | None, n: int = 260) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


# ----------------------------------------------------------------- deadline
DEADLINE_CUE = re.compile(
    r"(?i)(deadline|apply by|applications?\b[^.]{0,60}\bclos(e|es|ing)\b|applications? (are |will be )?(due|close|accepted (until|through))|"
    r"close[sd]? on|closing date|no later than|submit (your )?application(s)? by|"
    r"application window (closes|ends)|priority (deadline|consideration)|will close|posting (end|close)s?)")
DATE_PATTERNS = [
    re.compile(MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(20\d\d)?", re.I),
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+" + MONTH_RE + r"\.?,?\s*(20\d\d)?", re.I),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d|\d\d)\b"),
]


def _mk_date(y, mo, d):
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def find_dates(s: str, ref: date) -> list[date]:
    out = []
    for m in DATE_PATTERNS[0].finditer(s):
        mo = MONTHS[_mkey(m.group(1))]
        y = int(m.group(3)) if m.group(3) else _guess_year(mo, ref)
        d = _mk_date(y, mo, int(m.group(2)))
        if d:
            out.append(d)
    for m in DATE_PATTERNS[1].finditer(s):
        mo = MONTHS[_mkey(m.group(2))]
        y = int(m.group(3)) if m.group(3) else _guess_year(mo, ref)
        d = _mk_date(y, mo, int(m.group(1)))
        if d:
            out.append(d)
    for m in DATE_PATTERNS[2].finditer(s):
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        d = _mk_date(y, int(m.group(1)), int(m.group(2)))
        if d:
            out.append(d)
    return out


def _mkey(w: str) -> str:
    w = w.lower().rstrip(".")
    return w if w in MONTHS else w[:3]


def _guess_year(mo: int, ref: date) -> int:
    return ref.year + (1 if mo < ref.month - 1 else 0)


def deadline(text: str, ref: date) -> tuple[date | None, str | None]:
    for sent in sentences(text or ""):
        if not DEADLINE_CUE.search(sent):
            continue
        ds = [d for d in find_dates(sent, ref) if ref - timedelta(days=60) <= d <= ref + timedelta(days=540)]
        if ds:
            # "open Sept 1 and close Oct 15" -> the later date is the deadline
            return max(ds), _trim(sent)
    return None, None


# --------------------------------------------------------------- extras
PAY_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*(k)?\s*(?:-|–|—|to)\s*\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*(k)?"
    r"(?:\s*(?:usd|USD))?\s*(?:/|per|an|a)?\s*(hour|hr|year|yr|annually|annum|week|month)?", re.I)
PAY_SINGLE_RE = re.compile(r"\$\s?(\d{1,3}(?:\.\d{1,2})?)\s*(?:/|per|an)\s*(hour|hr)\b", re.I)


def pay(text: str) -> str | None:
    t = text or ""
    for m in PAY_RE.finditer(t):
        lo = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        hi = float(m.group(3).replace(",", "")) * (1000 if m.group(4) else 1)
        unit = (m.group(5) or "").lower()
        if hi < lo or lo <= 0:
            continue
        if unit.startswith(("h", )) or (not unit and hi < 300):
            if 10 <= lo <= 200:
                return f"${lo:,.0f}–${hi:,.0f}/hr" if lo != hi else f"${lo:,.0f}/hr"
        elif unit.startswith(("y", "a")) or (not unit and lo >= 20000):
            if 20000 <= lo <= 500000:
                return f"${lo/2080:,.0f}–${hi/2080:,.0f}/hr (≈ ${lo/1000:,.0f}k–${hi/1000:,.0f}k/yr)"
        elif unit.startswith("w") and 300 <= lo <= 8000:
            return f"${lo/40:,.0f}–${hi/40:,.0f}/hr"
    m = PAY_SINGLE_RE.search(t)
    if m and 10 <= float(m.group(1)) <= 200:
        return f"${float(m.group(1)):,.0f}/hr"
    return None


def gpa(text: str) -> str | None:
    m = re.search(r"(?i)(?:minimum|min\.?|cumulative|overall|at least|of)\s*(?:a\s*)?(?:cumulative\s*)?(?:gpa\s*(?:of)?\s*)?([2-3]\.\d{1,2})\s*(?:/\s*4\.0)?\s*(?:cumulative\s*)?(?:gpa|grade point)?", text or "")
    if m and re.search(r"(?i)gpa|grade point", (text or "")[max(0, m.start() - 60): m.end() + 60]):
        return f"{float(m.group(1)):.1f}+"
    m = re.search(r"(?i)gpa\s*(?:of\s*)?([2-3]\.\d{1,2})\s*(?:or (?:higher|above|better)|\+)", text or "")
    if m:
        return f"{float(m.group(1)):.1f}+"
    return None


def sponsorship(text: str) -> str | None:
    t = text or ""
    if re.search(r"(?i)(not|unable to|will not|won't|cannot|does not|do not)\s+(be able to\s+)?(provide\s+|offer\s+)?sponsor|without (the )?(need for |requiring )?(current or future )?(visa )?sponsorship|sponsorship (is )?not (available|provided)", t):
        return "No sponsorship"
    if re.search(r"(?i)\b(will|can|may)\s+sponsor|sponsorship (is )?available", t):
        return "Sponsors"
    return None


def work_mode(text: str, hint: str | None = None) -> str | None:
    s = f"{hint or ''} {text[:3000] if text else ''}"
    if re.search(r"(?i)\bhybrid\b", s):
        return "Hybrid"
    if re.search(r"(?i)\b(fully remote|100% remote|remote position|work from home)\b", s) or (hint and re.search(r"(?i)remote", hint)):
        return "Remote"
    if re.search(r"(?i)\b(on-?site|in-office|in office|in person)\b", s):
        return "On-site"
    return None


def weeks(text: str) -> int | None:
    m = re.search(r"(?i)\b(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?[- ]weeks?\b", text or "")
    if m:
        w = int(m.group(2) or m.group(1))
        if 2 <= w <= 30:
            return w
    m = re.search(r"(?i)\b(six|seven|eight|nine|ten|eleven|twelve)[- ]weeks?\b", text or "")
    if m:
        return ["six", "seven", "eight", "nine", "ten", "eleven", "twelve"].index(m.group(1).lower()) + 6
    return None


# ---------------------------------------------------------------- dates
def relative_posted(s: str | None, today: date) -> date | None:
    """Workday's 'Posted 3 Days Ago' / 'Posted Today' / 'Posted 30+ Days Ago'."""
    if not s:
        return None
    s = s.lower()
    if "today" in s:
        return today
    if "yesterday" in s:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", s)
    if m:
        return today - timedelta(days=int(m.group(1)))
    return None


def iso_date(s) -> date | None:
    if not s:
        return None
    if isinstance(s, (int, float)):
        ts = s / 1000 if s > 1e11 else s
        return datetime.utcfromtimestamp(ts).date()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    return _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
