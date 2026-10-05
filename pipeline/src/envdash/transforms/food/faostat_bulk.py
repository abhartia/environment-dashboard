"""Shared reading of FAOSTAT bulk zips for the country-level FAOSTAT transforms (land use, food loss, agrifood
emissions by country). Not an indicator module: `transforms()` returns nothing.

Bulk files. Each domain's zip holds `<Domain>_E_All_Data_(Normalized).csv` (UTF-8, CRLF, every field quoted), a flag
codebook `<Domain>_E_Flags.csv` and an area list `<Domain>_E_AreaCodes.csv`. Rows are matched by code (area, item,
element); the producer's names are never used to decide anything.

Vintage. FAOSTAT's bulk catalogue datasets_E.json gives each domain's DateUpdate and FileRows. A zip can be re-uploaded
after its DateUpdate, so the date alone does not identify the bytes: the catalogue entry must name the zip's URL as its
FileLocation and its FileRows must equal the number of data rows in the CSV, or the transform stops. The vintage is
that DateUpdate (ISO date); its year fills {year} in FAO's citation.

Areas. FAO area codes are mapped to our entity codes by AREAS below, an explicit table declared from the area lists of
the GT, RL and SDGB zips (Emissions_Totals_E_AreaCodes.csv, Inputs_LandUse_E_AreaCodes.csv,
SDG_BulkDownloads_E_AreaCodes.csv in the snapshots of 2026-10-04/05). Each entry also states the area's M49 code, and
a row whose "Area Code (M49)" differs from it stops the transform, so a re-used FAO code cannot be mapped silently.
Our codes were checked against Natural Earth's ISO_N3 for the same M49 number (ISO 3166-1 numeric codes are the M49
country codes); France (250) and Norway (578), which Natural Earth gives ISO_N3 -99, and the territories of
EXTRA_TERRITORIES in envdash/geo.py (Christmas Island, Bouvet Island, Cocos (Keeling) Islands, French Guiana, Réunion,
United States Minor Outlying Islands, the Channel Islands, Svalbard and Jan Mayen, Mayotte), which have no Natural
Earth polygon of their own, are declared by hand. FAO's "Serbia and Montenegro" (186, reported 1992-2005, before
Serbia (272) and Montenegro (273)) is SRB_MNE, Serbia and Montenegro as reported together. Every code then goes
through geo.resolve(…, "iso3"), which raises for anything not in pipeline/geo/entities.csv.

Areas that are not published, each listed with its reason (an area in neither table stops the transform):
- FORMER: states and territories FAO reports only before their dissolution (USSR to 1991, Sudan (former) to 2011,
  ...). There is no entity for them, and their values are never re-assigned to successor states.
- NO_ENTITY: areas FAO reports separately that have no row in pipeline/geo/entities.csv (Sark).
- FAO_GROUPS: FAO's regional and analytical groups (M49 regions, LDCs, OECD, Annex I, ...). M49 regions are not
  entities here (M49 is registered as display-only terms). "China" (351) is FAO's sum of mainland China, Hong Kong,
  Macao and Taiwan, which are published separately. World (5000) and the European Union (27) (5707) are published as
  WLD and EU27.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from envdash import geo
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Transform

SOURCE = "faostat"
CATALOGUE = Input(SOURCE, "datasets-catalogue")
ENCODING = "utf-8"

# FAO Area Code -> (M49 code as printed in "Area Code (M49)" without its leading apostrophe, our entity code).
AREAS: dict[str, tuple[str, str]] = {
    "1": ("051", "ARM"),  # Armenia
    "2": ("004", "AFG"),  # Afghanistan
    "3": ("008", "ALB"),  # Albania
    "4": ("012", "DZA"),  # Algeria
    "5": ("016", "ASM"),  # American Samoa
    "6": ("020", "AND"),  # Andorra
    "7": ("024", "AGO"),  # Angola
    "8": ("028", "ATG"),  # Antigua and Barbuda
    "9": ("032", "ARG"),  # Argentina
    "10": ("036", "AUS"),  # Australia
    "11": ("040", "AUT"),  # Austria
    "12": ("044", "BHS"),  # Bahamas
    "13": ("048", "BHR"),  # Bahrain
    "14": ("052", "BRB"),  # Barbados
    "16": ("050", "BGD"),  # Bangladesh
    "17": ("060", "BMU"),  # Bermuda
    "18": ("064", "BTN"),  # Bhutan
    "19": ("068", "BOL"),  # Bolivia (Plurinational State of)
    "20": ("072", "BWA"),  # Botswana
    "21": ("076", "BRA"),  # Brazil
    "22": ("533", "ABW"),  # Aruba
    "23": ("084", "BLZ"),  # Belize
    "24": ("086", "IOT"),  # Chagos Archipelago
    "25": ("090", "SLB"),  # Solomon Islands
    "26": ("096", "BRN"),  # Brunei Darussalam
    "27": ("100", "BGR"),  # Bulgaria
    "28": ("104", "MMR"),  # Myanmar
    "29": ("108", "BDI"),  # Burundi
    "32": ("120", "CMR"),  # Cameroon
    "33": ("124", "CAN"),  # Canada
    "35": ("132", "CPV"),  # Cabo Verde
    "36": ("136", "CYM"),  # Cayman Islands
    "37": ("140", "CAF"),  # Central African Republic
    "38": ("144", "LKA"),  # Sri Lanka
    "39": ("148", "TCD"),  # Chad
    "40": ("152", "CHL"),  # Chile
    "41": ("156", "CHN"),  # China; mainland
    "42": ("162", "CXR"),  # Christmas Island
    "44": ("170", "COL"),  # Colombia
    "45": ("174", "COM"),  # Comoros
    "46": ("178", "COG"),  # Congo
    "47": ("184", "COK"),  # Cook Islands
    "48": ("188", "CRI"),  # Costa Rica
    "49": ("192", "CUB"),  # Cuba
    "50": ("196", "CYP"),  # Cyprus
    "52": ("031", "AZE"),  # Azerbaijan
    "53": ("204", "BEN"),  # Benin
    "54": ("208", "DNK"),  # Denmark
    "55": ("212", "DMA"),  # Dominica
    "56": ("214", "DOM"),  # Dominican Republic
    "57": ("112", "BLR"),  # Belarus
    "58": ("218", "ECU"),  # Ecuador
    "59": ("818", "EGY"),  # Egypt
    "60": ("222", "SLV"),  # El Salvador
    "61": ("226", "GNQ"),  # Equatorial Guinea
    "63": ("233", "EST"),  # Estonia
    "64": ("234", "FRO"),  # Faroe Islands
    "65": ("238", "FLK"),  # Falkland Islands (Malvinas)
    "66": ("242", "FJI"),  # Fiji
    "67": ("246", "FIN"),  # Finland
    "68": ("250", "FRA"),  # France
    "70": ("258", "PYF"),  # French Polynesia
    "71": ("260", "ATF"),  # French Southern Territories
    "72": ("262", "DJI"),  # Djibouti
    "73": ("268", "GEO"),  # Georgia
    "74": ("266", "GAB"),  # Gabon
    "75": ("270", "GMB"),  # Gambia
    "79": ("276", "DEU"),  # Germany
    "80": ("070", "BIH"),  # Bosnia and Herzegovina
    "81": ("288", "GHA"),  # Ghana
    "82": ("292", "GIB"),  # Gibraltar
    "83": ("296", "KIR"),  # Kiribati
    "84": ("300", "GRC"),  # Greece
    "85": ("304", "GRL"),  # Greenland
    "86": ("308", "GRD"),  # Grenada
    "87": ("312", "GLP"),  # Guadeloupe
    "88": ("316", "GUM"),  # Guam
    "89": ("320", "GTM"),  # Guatemala
    "90": ("324", "GIN"),  # Guinea
    "91": ("328", "GUY"),  # Guyana
    "92": ("334", "HMD"),  # Heard Island and McDonald Islands
    "93": ("332", "HTI"),  # Haiti
    "94": ("336", "VAT"),  # Holy See
    "95": ("340", "HND"),  # Honduras
    "96": ("344", "HKG"),  # China; Hong Kong SAR
    "97": ("348", "HUN"),  # Hungary
    "98": ("191", "HRV"),  # Croatia
    "99": ("352", "ISL"),  # Iceland
    "100": ("356", "IND"),  # India
    "101": ("360", "IDN"),  # Indonesia
    "102": ("364", "IRN"),  # Iran (Islamic Republic of)
    "103": ("368", "IRQ"),  # Iraq
    "104": ("372", "IRL"),  # Ireland
    "105": ("376", "ISR"),  # Israel
    "106": ("380", "ITA"),  # Italy
    "107": ("384", "CIV"),  # Côte d'Ivoire
    "108": ("398", "KAZ"),  # Kazakhstan
    "109": ("388", "JAM"),  # Jamaica
    "110": ("392", "JPN"),  # Japan
    "112": ("400", "JOR"),  # Jordan
    "113": ("417", "KGZ"),  # Kyrgyzstan
    "114": ("404", "KEN"),  # Kenya
    "115": ("116", "KHM"),  # Cambodia
    "116": ("408", "PRK"),  # Democratic People's Republic of Korea
    "117": ("410", "KOR"),  # Republic of Korea
    "118": ("414", "KWT"),  # Kuwait
    "119": ("428", "LVA"),  # Latvia
    "120": ("418", "LAO"),  # Lao People's Democratic Republic
    "121": ("422", "LBN"),  # Lebanon
    "122": ("426", "LSO"),  # Lesotho
    "123": ("430", "LBR"),  # Liberia
    "124": ("434", "LBY"),  # Libya
    "125": ("438", "LIE"),  # Liechtenstein
    "126": ("440", "LTU"),  # Lithuania
    "127": ("584", "MHL"),  # Marshall Islands
    "128": ("446", "MAC"),  # China; Macao SAR
    "129": ("450", "MDG"),  # Madagascar
    "130": ("454", "MWI"),  # Malawi
    "131": ("458", "MYS"),  # Malaysia
    "132": ("462", "MDV"),  # Maldives
    "133": ("466", "MLI"),  # Mali
    "134": ("470", "MLT"),  # Malta
    "135": ("474", "MTQ"),  # Martinique
    "136": ("478", "MRT"),  # Mauritania
    "137": ("480", "MUS"),  # Mauritius
    "138": ("484", "MEX"),  # Mexico
    "140": ("492", "MCO"),  # Monaco
    "141": ("496", "MNG"),  # Mongolia
    "142": ("500", "MSR"),  # Montserrat
    "143": ("504", "MAR"),  # Morocco
    "144": ("508", "MOZ"),  # Mozambique
    "145": ("583", "FSM"),  # Micronesia (Federated States of)
    "146": ("498", "MDA"),  # Republic of Moldova
    "147": ("516", "NAM"),  # Namibia
    "148": ("520", "NRU"),  # Nauru
    "149": ("524", "NPL"),  # Nepal
    "150": ("528", "NLD"),  # Netherlands (Kingdom of the)
    "153": ("540", "NCL"),  # New Caledonia
    "154": ("807", "MKD"),  # North Macedonia
    "155": ("548", "VUT"),  # Vanuatu
    "156": ("554", "NZL"),  # New Zealand
    "157": ("558", "NIC"),  # Nicaragua
    "158": ("562", "NER"),  # Niger
    "159": ("566", "NGA"),  # Nigeria
    "160": ("570", "NIU"),  # Niue
    "161": ("574", "NFK"),  # Norfolk Island
    "162": ("578", "NOR"),  # Norway
    "163": ("580", "MNP"),  # Northern Mariana Islands
    "165": ("586", "PAK"),  # Pakistan
    "166": ("591", "PAN"),  # Panama
    "167": ("203", "CZE"),  # Czechia
    "168": ("598", "PNG"),  # Papua New Guinea
    "169": ("600", "PRY"),  # Paraguay
    "170": ("604", "PER"),  # Peru
    "171": ("608", "PHL"),  # Philippines
    "172": ("612", "PCN"),  # Pitcairn
    "173": ("616", "POL"),  # Poland
    "174": ("620", "PRT"),  # Portugal
    "175": ("624", "GNB"),  # Guinea-Bissau
    "176": ("626", "TLS"),  # Timor-Leste
    "177": ("630", "PRI"),  # Puerto Rico
    "178": ("232", "ERI"),  # Eritrea
    "179": ("634", "QAT"),  # Qatar
    "180": ("585", "PLW"),  # Palau
    "181": ("716", "ZWE"),  # Zimbabwe
    "183": ("642", "ROU"),  # Romania
    "184": ("646", "RWA"),  # Rwanda
    "185": ("643", "RUS"),  # Russian Federation
    "187": ("654", "SHN"),  # Ascension; Saint Helena and Tristan da Cunha
    "188": ("659", "KNA"),  # Saint Kitts and Nevis
    "189": ("662", "LCA"),  # Saint Lucia
    "190": ("666", "SPM"),  # Saint Pierre and Miquelon
    "191": ("670", "VCT"),  # Saint Vincent and the Grenadines
    "192": ("674", "SMR"),  # San Marino
    "193": ("678", "STP"),  # Sao Tome and Principe
    "194": ("682", "SAU"),  # Saudi Arabia
    "195": ("686", "SEN"),  # Senegal
    "196": ("690", "SYC"),  # Seychelles
    "197": ("694", "SLE"),  # Sierra Leone
    "198": ("705", "SVN"),  # Slovenia
    "199": ("703", "SVK"),  # Slovakia
    "200": ("702", "SGP"),  # Singapore
    "201": ("706", "SOM"),  # Somalia
    "202": ("710", "ZAF"),  # South Africa
    "203": ("724", "ESP"),  # Spain
    "205": ("732", "ESH"),  # Western Sahara
    "207": ("740", "SUR"),  # Suriname
    "208": ("762", "TJK"),  # Tajikistan
    "209": ("748", "SWZ"),  # Eswatini
    "210": ("752", "SWE"),  # Sweden
    "211": ("756", "CHE"),  # Switzerland
    "212": ("760", "SYR"),  # Syrian Arab Republic
    "213": ("795", "TKM"),  # Turkmenistan
    "214": ("158", "TWN"),  # China; Taiwan Province of
    "215": ("834", "TZA"),  # United Republic of Tanzania
    "216": ("764", "THA"),  # Thailand
    "217": ("768", "TGO"),  # Togo
    "218": ("772", "TKL"),  # Tokelau
    "219": ("776", "TON"),  # Tonga
    "220": ("780", "TTO"),  # Trinidad and Tobago
    "221": ("512", "OMN"),  # Oman
    "222": ("788", "TUN"),  # Tunisia
    "223": ("792", "TUR"),  # Türkiye
    "224": ("796", "TCA"),  # Turks and Caicos Islands
    "225": ("784", "ARE"),  # United Arab Emirates
    "226": ("800", "UGA"),  # Uganda
    "227": ("798", "TUV"),  # Tuvalu
    "229": ("826", "GBR"),  # United Kingdom of Great Britain and Northern Ireland
    "230": ("804", "UKR"),  # Ukraine
    "231": ("840", "USA"),  # United States of America
    "233": ("854", "BFA"),  # Burkina Faso
    "234": ("858", "URY"),  # Uruguay
    "235": ("860", "UZB"),  # Uzbekistan
    "236": ("862", "VEN"),  # Venezuela (Bolivarian Republic of)
    "237": ("704", "VNM"),  # Viet Nam
    "238": ("231", "ETH"),  # Ethiopia
    "239": ("092", "VGB"),  # British Virgin Islands
    "240": ("850", "VIR"),  # United States Virgin Islands
    "243": ("876", "WLF"),  # Wallis and Futuna Islands
    "244": ("882", "WSM"),  # Samoa
    "249": ("887", "YEM"),  # Yemen
    "250": ("180", "COD"),  # Democratic Republic of the Congo
    "251": ("894", "ZMB"),  # Zambia
    "255": ("056", "BEL"),  # Belgium
    "256": ("442", "LUX"),  # Luxembourg
    "258": ("660", "AIA"),  # Anguilla
    "264": ("833", "IMN"),  # Isle of Man
    "271": ("239", "SGS"),  # South Georgia and the South Sandwich Islands
    "272": ("688", "SRB"),  # Serbia (FAO has no separate row for Kosovo)
    "273": ("499", "MNE"),  # Montenegro
    "274": ("831", "GGY"),  # Guernsey
    "276": ("729", "SDN"),  # Sudan (from 2012)
    "277": ("728", "SSD"),  # South Sudan
    "278": ("535", "BES"),  # Bonaire; Sint Eustatius and Saba
    "279": ("531", "CUW"),  # Curaçao
    "280": ("534", "SXM"),  # Sint Maarten (Dutch part)
    "281": ("663", "MAF"),  # Saint Martin (French part)
    "282": ("652", "BLM"),  # Saint Barthélemy
    "283": ("832", "JEY"),  # Jersey
    "284": ("248", "ALA"),  # Åland Islands
    "299": ("275", "PSE"),  # Palestine
    # envdash/geo.py EXTRA_TERRITORIES (no Natural Earth polygon of their own) and AGGREGATES.
    "31": ("074", "BVT"),  # Bouvet Island
    "43": ("166", "CCK"),  # Cocos (Keeling) Islands
    "69": ("254", "GUF"),  # French Guiana
    "182": ("638", "REU"),  # Réunion
    "186": ("891", "SRB_MNE"),  # Serbia and Montenegro (1992-2005)
    "232": ("581", "UMI"),  # United States Minor Outlying Islands
    "259": ("830", "CHI"),  # Channel Islands
    "260": ("744", "SJM"),  # Svalbard and Jan Mayen Islands
    "270": ("175", "MYT"),  # Mayotte
    "5000": ("001", "WLD"),  # World
    "5707": ("097", "EU27"),  # European Union (27)
}

# FAO Area Code -> (M49 code, FAO's name), for areas that are not published.
FORMER: dict[str, tuple[str, str]] = {
    "15": ("058", "Belgium-Luxembourg"),
    "51": ("200", "Czechoslovakia"),
    "62": ("230", "Ethiopia PDR"),
    "151": ("530", "Netherlands Antilles (former)"),
    "164": ("582", "Pacific Islands Trust Territory"),
    "206": ("736", "Sudan (former)"),
    "228": ("810", "USSR"),
    "248": ("890", "Yugoslav SFR"),
}
NO_ENTITY: dict[str, tuple[str, str]] = {
    "285": ("680", "Sark"),
}
FAO_GROUPS: dict[str, tuple[str, str]] = {
    "351": ("159", "China"),
    "420": ("202", "Sub-Saharan Africa"),
    "5100": ("002", "Africa"),
    "5101": ("014", "Eastern Africa"),
    "5102": ("017", "Middle Africa"),
    "5103": ("015", "Northern Africa"),
    "5104": ("018", "Southern Africa"),
    "5105": ("011", "Western Africa"),
    "5200": ("019", "Americas"),
    "5203": ("021", "Northern America"),
    "5204": ("013", "Central America"),
    "5205": ("419", "Latin America and the Caribbean"),
    "5206": ("029", "Caribbean"),
    "5207": ("005", "South America"),
    "5208": ("513", "Northern America and Europe"),
    "5300": ("142", "Asia"),
    "5301": ("143", "Central Asia"),
    "5302": ("030", "Eastern Asia"),
    "5303": ("034", "Southern Asia"),
    "5304": ("035", "South-eastern Asia"),
    "5305": ("145", "Western Asia"),
    "5306": ("062", "Central Asia and Southern Asia"),
    "5307": ("753", "Eastern Asia and South-eastern Asia"),
    "5308": ("747", "Western Asia and Northern Africa"),
    "5400": ("150", "Europe"),
    "5401": ("151", "Eastern Europe"),
    "5402": ("154", "Northern Europe"),
    "5403": ("039", "Southern Europe"),
    "5404": ("155", "Western Europe"),
    "5500": ("009", "Oceania"),
    "5501": ("053", "Australia and New Zealand"),
    "5502": ("054", "Melanesia"),
    "5503": ("057", "Micronesia"),
    "5504": ("061", "Polynesia"),
    "5801": ("199", "Least Developed Countries (LDCs)"),
    "5802": ("432", "Land Locked Developing Countries (LLDCs)"),
    "5803": ("722", "Small Island Developing States (SIDS)"),
    "5807": ("543", "Oceania excluding Australia and New Zealand"),
    "5815": ("901", "Low Income Food Deficit Countries (LIFDCs)"),
    "5817": ("902", "Net Food Importing Developing Countries (NFIDCs)"),
    "5848": ("907", "Annex I countries"),
    "5849": ("908", "Non-Annex I countries"),
    "5873": ("198", "OECD"),
}

_NOT_PUBLISHED = {**FORMER, **NO_ENTITY, **FAO_GROUPS}


class FaostatBulkError(ValueError):
    pass


def area_entity(code: str, m49_field: str) -> str | None:
    """Our entity code for an FAO area, or None for an area listed as not published. Raises for anything else."""
    m49 = m49_field.removeprefix("'")
    if code in AREAS:
        declared, ours = AREAS[code]
    elif code in _NOT_PUBLISHED:
        declared, ours = _NOT_PUBLISHED[code][0], None
    else:
        raise FaostatBulkError(
            f"FAO area code {code} (M49 {m49}) is not declared in faostat_bulk.AREAS or the not-published tables"
        )
    if m49 != declared:
        raise FaostatBulkError(f"FAO area code {code} has M49 {m49}, but {declared} is declared for it")
    return geo.resolve(ours, "iso3") if ours is not None else None


def not_published_step(seen: Iterable[str]) -> str:
    """Words for the areas of the file that were left out, by reason."""
    seen = set(seen)
    parts = []
    for table, why in (
        (FORMER, "former states and territories reported only before their dissolution, with no entity here"),
        (NO_ENTITY, "territories with no entity in pipeline/geo/entities.csv"),
        (FAO_GROUPS, "FAO regional and analytical groups"),
    ):
        names = sorted(table[c][1] for c in seen if c in table)
        if names:
            parts.append(f"{why} ({', '.join(names)})")
    if not parts:
        return "Every area in the rows used is published."
    return "Left out " + "; ".join(parts) + ". Their values are never re-assigned to other entities."


def catalogue_entry(raw: bytes, dataset_code: str, url: str) -> tuple[date, int]:
    """(DateUpdate, FileRows) of one domain's entry of datasets_E.json, which must name `url` as its file."""
    doc = json.loads(raw.decode("utf-8"))
    entries = [d for d in doc["Datasets"]["Dataset"] if d["DatasetCode"] == dataset_code]
    if len(entries) != 1:
        raise FaostatBulkError(f"datasets_E.json has {len(entries)} entries for {dataset_code}")
    e = entries[0]
    if e["FileLocation"] != url:
        raise FaostatBulkError(f"datasets_E.json gives {dataset_code} at {e['FileLocation']!r}, not {url!r}")
    return date.fromisoformat(e["DateUpdate"][:10]), int(e["FileRows"])


def read_flags(raw: bytes, member: str) -> dict[str, str]:
    """A flag codebook: {"E": "Estimated value", ...}."""
    rows = list(csv.reader(io.StringIO(raw.decode(ENCODING))))
    if [c.strip() for c in rows[0]] != ["Flag", "Description"]:
        raise FaostatBulkError(f"{member}: header {rows[0]} is not Flag, Description")
    return {r[0].strip(): r[1].strip() for r in rows[1:] if r}


def fields(line: bytes) -> list[str]:
    return next(csv.reader(io.StringIO(line.decode(ENCODING))))


@dataclass(frozen=True)
class Table:
    data_rows: int
    """Every data row in the CSV, for comparison with the catalogue's FileRows."""
    rows: tuple[dict[str, str], ...]
    """The rows kept, as {column: value}."""


def read_member(
    lines: Iterable[bytes], member: str, columns: list[str], keep: Callable[[dict[str, str]], bool], marker: bytes
) -> Table:
    """Count every data row and keep those for which `keep` is true. `lines` is the CSV member, header first. Only
    lines containing `marker` (bytes every wanted row has, e.g. its quoted item code) are parsed; `keep` decides."""
    it = iter(lines)
    header = fields(next(it))
    if header != columns:
        raise FaostatBulkError(f"{member}: columns {header} != expected {columns}")
    n = 0
    kept: list[dict[str, str]] = []
    for line in it:
        n += 1
        if not line.startswith(b'"'):
            raise FaostatBulkError(f"{member}: data row {n} does not start with a quoted Area Code")
        if marker not in line:
            continue
        f = fields(line)
        if len(f) != len(columns):
            raise FaostatBulkError(f"{member}: data row {n} has {len(f)} fields, not {len(columns)}")
        row = dict(zip(columns, f, strict=True))
        if keep(row):
            kept.append(row)
    return Table(n, tuple(kept))


def year_of(row: dict[str, str], what: str) -> int:
    if row["Year"] != row["Year Code"] or not row["Year"].isdigit() or len(row["Year"]) != 4:
        raise FaostatBulkError(f"{what}: Year {row['Year']!r} / Year Code {row['Year Code']!r} is not one year")
    return int(row["Year"])


def value_of(row: dict[str, str], what: str) -> Decimal | None:
    """The printed value, or None when the cell is empty (the caller decides whether an empty cell is allowed)."""
    v = row["Value"]
    return Decimal(v) if v != "" else None


def flag_words(flags: dict[str, str], used: Iterable[str], member: str) -> dict[str, str]:
    out = {}
    for f in sorted(set(used)):
        if f not in flags:
            raise FaostatBulkError(f"flag {f!r} is not in {member}")
        out[f] = flags[f]
    return out


def flag_step(words: dict[str, str], counts: Counter[str]) -> str:
    if len(words) == 1:
        ((f, w),) = words.items()
        return f"Every value used carries FAO's flag {f}, which the file's codebook defines as \"{w}\"."
    listed = "; ".join(f'{f} "{w}" ({counts[f]:,} values)' for f, w in words.items())
    return f"The values used carry several FAO flags ({listed}); each observation names its flag in a note."


def vintage_of(
    files: dict[str, InputFile], data: Input, dataset_code: str, data_rows: int, member: str
) -> tuple[date, str]:
    """(DateUpdate, the processing step stating it) for a domain zip whose CSV has `data_rows` rows."""
    t, c = files[data.key], files[CATALOGUE.key]
    url = str(t.snapshot.url) if t.snapshot.url else ""
    updated, file_rows = catalogue_entry(c.path.read_bytes(), dataset_code, url)
    if data_rows != file_rows:
        raise FaostatBulkError(
            f"datasets_E.json says {dataset_code} has {file_rows} rows but {member} has {data_rows}: the catalogue "
            "describes another file, so its DateUpdate cannot be this file's vintage"
        )
    modified = (
        f" The zip was last modified on the server on {t.snapshot.last_modified}." if t.snapshot.last_modified else ""
    )
    step = (
        f"Read {member} from FAOSTAT's {dataset_code} bulk zip. The vintage is the domain's DateUpdate, "
        f"{updated.day} {updated:%B %Y}, from FAOSTAT's bulk-download catalogue (datasets_E.json), whose entry names "
        f"this zip and gives FileRows {file_rows:,}, the number of data rows in this file.{modified}"
    )
    return updated, step


def transforms(paths: Paths) -> list[Transform]:
    return []
