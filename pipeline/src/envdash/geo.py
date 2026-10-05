"""Entities: the codes observations carry (models.Observation.entity), and how producers' codes map to them.

pipeline/geo/entities.csv is the explicit crosswalk, one row per entity:

  iso3          our entity code: ISO 3166-1 alpha-3 where one exists, else a code of ours (aggregates, stations)
  name          English name (Natural Earth ADMIN for its polygons, GEOUNIT for its tiny-country points)
  kind          country | territory | aggregate | station
  ne_adm0_a3    Natural Earth ADM0_A3 of the 1:50m admin-0 polygon drawn for it; empty if none
  ne_iso_a3_eh  Natural Earth ISO_A3_EH of that polygon (or of its tiny-country point); empty if none
  member_of     aggregates it belongs to, ';'-separated (only memberships stated below; WLD is implied)

It is generated, never edited by hand: `uv run envdash geo build` reads the current natural-earth snapshots
(admin-0-countries-50m and admin-0-tiny-countries-50m, public domain) and writes the CSV and its provenance sidecar
(entities.provenance.json: the snapshot sha256s it was built from).

Rules, all deterministic:
- Every 1:50m admin-0 polygon is one row. Its code is ISO_A3_EH, because Natural Earth sets ISO_A3 to -99 for France
  and Norway; where ISO_A3_EH is -99 (Kosovo, Somaliland, Northern Cyprus, Siachen Glacier) it is ADM0_A3. Where
  several polygons share one ISO_A3_EH (Australia, Indian Ocean Territories and Ashmore and Cartier Islands are all
  AUS), the polygon whose ADM0_A3 equals that code keeps it and the others take their ADM0_A3. A code still shared
  after that stops the build.
- kind: country when Natural Earth's ADMIN equals its SOVEREIGNT and its TYPE is Sovereign country, Country,
  Sovereignty or Disputed; otherwise territory. This is Natural Earth's default de facto point of view (so, for
  example, Palestine and Western Sahara, TYPE Indeterminate, are territories; Kosovo and Somaliland are countries),
  which the map states.
- A tiny-country point whose ISO_A3_EH (not -99) belongs to no polygon row is a row too (San Marino, Monaco, the
  Vatican, Gibraltar, Guadeloupe, Martinique, Tokelau, the Caribbean Netherlands), with ne_adm0_a3 empty.
- EXTRA_TERRITORIES, AGGREGATES and STATIONS below are added as declared. UN M49 regions are not entities here: M49
  is registered as display-only terms.

`resolve(code_or_name, scheme)` maps a producer's code or name to our code and raises UnknownEntity for anything not
in the table, never guessing (no fuzzy names, no prefix matches, no substitute for a missing entity). Schemes are the
table's own columns (iso3, ne_adm0_a3, ne_iso_a3_eh, name) or a source id from SOURCE_SCHEMES, whose explicit alias
table is tried before its base column.
"""

from __future__ import annotations

import csv
import io
import struct
import zipfile
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Literal

from envdash import canonical, snapshots
from envdash.models import ENTITY
from envdash.paths import Paths

COLUMNS = ("iso3", "name", "kind", "ne_adm0_a3", "ne_iso_a3_eh", "member_of")
EntityKind = Literal["country", "territory", "aggregate", "station"]
NE_SOURCE = "natural-earth"
NE_COUNTRIES = "admin-0-countries-50m"
NE_TINY = "admin-0-tiny-countries-50m"
COUNTRY_TYPES = frozenset({"Sovereign country", "Country", "Sovereignty", "Disputed"})

# The 27 member states listed on https://european-union.europa.eu/principles-countries-history/eu-countries_en
# (read 2026-10-04: "Pages (27)", Austria to Sweden), by ISO 3166-1 alpha-3.
EU27_MEMBERS = frozenset(
    {
        "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL",
        "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE",
    }
)  # fmt: skip

# Territories with an ISO 3166-1 code that a registered source reports separately but Natural Earth's 1:50m layers
# do not draw separately. No polygon: a map shows them as "no shape at this scale".
EXTRA_TERRITORIES: dict[str, tuple[str, str]] = {
    # gcp-fossil-co2-2025 mtco2-flat has "Christmas Island","CXR"; Natural Earth draws it inside Indian Ocean
    # Territories (ADM0_A3 IOA, ISO_A3_EH AUS) together with the Cocos (Keeling) Islands.
    "CXR": ("Christmas Island", "gcp-fossil-co2-2025"),
    # Overseas regions and dependencies that producers report separately but Natural Earth draws inside another
    # country's polygon (FRA, NOR) or omits. Reported separately by: Ember, EIA, EDGAR, FAOSTAT, FRA, CCKP.
    "GUF": ("French Guiana", "ember-yearly"),
    "REU": ("Réunion", "ember-yearly"),
    "MYT": ("Mayotte", "faostat"),
    "SJM": ("Svalbard and Jan Mayen", "faostat"),
    "BVT": ("Bouvet Island", "wb-cckp"),
    "CCK": ("Cocos (Keeling) Islands", "wb-cckp"),
    "UMI": ("United States Minor Outlying Islands", "wb-cckp"),
    # The World Bank's WDI reports the Channel Islands (Jersey and Guernsey) as one economy, code CHI.
    "CHI": ("Channel Islands", "wb-wdi"),
}

# Aggregates and producer pseudo-entities: no polygon. Codes are ours (ENTITY: [A-Z0-9_]{2,12}).
AGGREGATES: dict[str, str] = {
    "WLD": "World",
    "EU27": "European Union (27 member states since 1 February 2020)",
    "INTL_AIR": "International aviation",
    "INTL_SEA": "International shipping",
    "INTL_BUNKERS": "International transport (aviation and shipping bunker fuels)",
    # Historical pseudo-entities with their own rows in gcp-fossil-co2-2025 and jones-2025-national-contributions.
    "KWT_OILFIRES": "Kuwaiti oil fires (1991)",
    "PAC_ISLANDS": "Pacific Islands Trust Territory (Palau), as reported before Palau's independence",
    "RYUKYU": "Ryukyu Islands, as reported while under US administration",
    "NH": "Northern Hemisphere",
    "SH": "Southern Hemisphere",
    # EDGAR's row "Serbia and Montenegro" (code SCG), reported as one entity in its historical years.
    "SRB_MNE": "Serbia and Montenegro (as reported together)",
}

STATIONS: dict[str, str] = {
    "MLO": "Mauna Loa Observatory, Hawaii",
    "LAWDOME": "Law Dome ice cores, Antarctica",
    "ALOHA": "Station ALOHA, North Pacific north of Oahu, Hawaii",
    # bereiter-2015-co2: a composite of several Antarctic cores (Law Dome, Dome C, WAIS Divide, Siple Dome, Talos
    # Dome, EDML, Vostok), so not one site.
    "ANT_ICECORES": "Antarctic ice cores (composite of several sites)",
}


@dataclass(frozen=True)
class SourceScheme:
    """How one producer names entities: an explicit alias table, then one column of the entity table."""

    base: Literal["iso3", "name"]
    aliases: dict[str, str] = field(default_factory=dict)
    note: str = ""


# Alias tables, declared from the producers' own files (each entry seen in the snapshot named in the note).
SOURCE_SCHEMES: dict[str, SourceScheme] = {
    "gcp-fossil-co2-2025": SourceScheme(
        base="iso3",
        aliases={
            "KSV": "KOS",
            "XIA": "INTL_AIR",
            "XIS": "INTL_SEA",
            # Rows with an empty code column, by their Country value.
            "Kuwaiti Oil Fires": "KWT_OILFIRES",
            "Pacific Islands (Palau)": "PAC_ISLANDS",
            "Ryukyu Islands": "RYUKYU",
        },
        note="mtco2-flat column 'ISO 3166-1 alpha-3' (Country for rows without a code), sha256 20650c19b394…",
    ),
    "jones-2025-national-contributions": SourceScheme(
        base="iso3",
        aliases={
            "KSV": "KOS",
            "GLOBAL": "WLD",
            "XKW": "KWT_OILFIRES",
            "XPC": "PAC_ISLANDS",
            "XRY": "RYUKYU",
        },
        # ANNEXI, ANNEXII, BASIC, EIT, LDC, LMDC, NONANNEX and OECD are the producer's own country groups: not
        # entities here, so they raise.
        note="emissions-annual-1830 column ISO3, sha256 c718f698de72…",
    ),
}


class UnknownEntity(KeyError):
    pass


@dataclass(frozen=True)
class Entity:
    iso3: str
    name: str
    kind: EntityKind
    ne_adm0_a3: str = ""
    ne_iso_a3_eh: str = ""
    member_of: tuple[str, ...] = ()

    def row(self) -> list[str]:
        return [self.iso3, self.name, self.kind, self.ne_adm0_a3, self.ne_iso_a3_eh, ";".join(self.member_of)]


# --- Natural Earth shapefile attributes (dBase III .dbf) ----------------------------------------------------------


def read_dbf(data: bytes, encoding: str) -> list[dict[str, str]]:
    """Records of a dBase III table as strings (trailing spaces and NUL padding removed); deleted records skipped."""
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields: list[tuple[str, int]] = []
    pos = 32
    while data[pos] != 0x0D:
        name = data[pos : pos + 11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, data[pos + 16]))
        pos += 32
    rows: list[dict[str, str]] = []
    for i in range(count):
        rec = data[header_len + i * record_len : header_len + (i + 1) * record_len]
        if rec[:1] == b"*":
            continue
        off, row = 1, {}
        for name, width in fields:
            row[name] = rec[off : off + width].decode(encoding).strip("\x00 ")
            off += width
        rows.append(row)
    return rows


def shapefile_records(zip_bytes: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        dbf = [n for n in z.namelist() if n.lower().endswith(".dbf")]
        if len(dbf) != 1:
            raise ValueError(f"expected one .dbf in the zip, found {dbf}")
        cpg = dbf[0][:-4] + ".cpg"
        encoding = z.read(cpg).decode("ascii").strip() if cpg in z.namelist() else "latin-1"
        return read_dbf(z.read(dbf[0]), "utf-8" if encoding.upper().replace("-", "") == "UTF8" else encoding)


def _kind(r: dict[str, str]) -> EntityKind:
    return "country" if r["ADMIN"] == r["SOVEREIGNT"] and r["TYPE"] in COUNTRY_TYPES else "territory"


def entities_from_natural_earth(countries_zip: bytes, tiny_zip: bytes) -> list[Entity]:
    polygons = shapefile_records(countries_zip)
    eh_owners: dict[str, list[str]] = {}
    for r in polygons:
        eh_owners.setdefault(r["ISO_A3_EH"], []).append(r["ADM0_A3"])
    rows: list[Entity] = []
    for r in polygons:
        eh = r["ISO_A3_EH"]
        shared = len(eh_owners[eh]) > 1
        code = r["ADM0_A3"] if eh == "-99" or (shared and r["ADM0_A3"] != eh) else eh
        rows.append(
            Entity(
                iso3=code,
                name=r["ADMIN"],
                kind=_kind(r),
                ne_adm0_a3=r["ADM0_A3"],
                ne_iso_a3_eh="" if eh == "-99" else eh,
                member_of=("EU27",) if code in EU27_MEMBERS and _kind(r) == "country" else (),
            )
        )
    taken = {e.iso3 for e in rows} | {e.ne_iso_a3_eh for e in rows}
    for r in shapefile_records(tiny_zip):
        eh = r["ISO_A3_EH"]
        if eh == "-99" or eh in taken:
            continue
        taken.add(eh)
        rows.append(Entity(iso3=eh, name=r["GEOUNIT"], kind=_kind(r), ne_adm0_a3="", ne_iso_a3_eh=eh))
    return rows


def all_entities(countries_zip: bytes, tiny_zip: bytes) -> list[Entity]:
    rows = entities_from_natural_earth(countries_zip, tiny_zip)
    rows += [Entity(code, name, "territory") for code, (name, _) in EXTRA_TERRITORIES.items()]
    rows += [Entity(code, name, "aggregate") for code, name in AGGREGATES.items()]
    rows += [Entity(code, name, "station") for code, name in STATIONS.items()]
    codes = [e.iso3 for e in rows]
    dupes = sorted({c for c in codes if codes.count(c) > 1})
    if dupes:
        raise ValueError(f"entity codes defined more than once: {dupes}")
    bad = [c for c in codes if not ENTITY.fullmatch(c)]
    if bad:
        raise ValueError(f"entity codes not matching {ENTITY.pattern}: {bad}")
    members = {e.iso3 for e in rows if "EU27" in e.member_of}
    if members != EU27_MEMBERS:
        raise ValueError(f"EU27 members without a country row: {sorted(EU27_MEMBERS - members)}")
    return sorted(rows, key=lambda e: e.iso3)


def csv_bytes(rows: list[Entity]) -> bytes:
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for e in rows:
        w.writerow(e.row())
    return out.getvalue().encode("utf-8")


# --- build and load -----------------------------------------------------------------------------------------------


def entities_path(paths: Paths) -> Path:
    return paths.repo / "pipeline" / "geo" / "entities.csv"


def _ne_snapshot(paths: Paths, artifact: str) -> tuple[str, bytes]:
    sha = snapshots.read_current(paths).get(snapshots.key(NE_SOURCE, artifact))
    if sha is None:
        raise FileNotFoundError(f"no snapshot of {NE_SOURCE}/{artifact}; run envdash fetch -s {NE_SOURCE}")
    data = snapshots.cache_path(paths, sha).read_bytes()
    if canonical.sha256_bytes(data) != sha:
        raise ValueError(f"cached bytes of {NE_SOURCE}/{artifact} do not hash to {sha}")
    return sha, data


def build(paths: Paths) -> tuple[bytes, dict]:
    """The entities.csv bytes and provenance sidecar built from the current natural-earth snapshots."""
    c_sha, countries = _ne_snapshot(paths, NE_COUNTRIES)
    t_sha, tiny = _ne_snapshot(paths, NE_TINY)
    data = csv_bytes(all_entities(countries, tiny))
    side = {
        "file": "pipeline/geo/entities.csv",
        "sha256": canonical.sha256_bytes(data),
        "built_by": "uv run envdash geo build (envdash/geo.py)",
        "inputs": {
            f"{NE_SOURCE}/{NE_COUNTRIES}": c_sha,
            f"{NE_SOURCE}/{NE_TINY}": t_sha,
        },
    }
    return data, side


def write(paths: Paths) -> bool:
    data, side = build(paths)
    out = entities_path(paths)
    changed = canonical.write_if_changed(out, data)
    changed |= canonical.write_if_changed(out.with_name("entities.provenance.json"), canonical.dump_bytes(side))
    return changed


@dataclass(frozen=True)
class EntityTable:
    rows: tuple[Entity, ...]

    def by(self, column: str) -> dict[str, list[Entity]]:
        index: dict[str, list[Entity]] = {}
        for e in self.rows:
            v = getattr(e, column)
            if v:
                index.setdefault(v, []).append(e)
        return index


def read_table(path: Path) -> EntityTable:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if tuple(header) != COLUMNS:
            raise ValueError(f"{path}: columns {header} != {list(COLUMNS)}")
        rows = [
            Entity(r[0], r[1], r[2], r[3], r[4], tuple(m for m in r[5].split(";") if m))  # type: ignore[arg-type]
            for r in reader
        ]
    return EntityTable(tuple(rows))


@cache
def _default_table() -> EntityTable:
    return read_table(entities_path(Paths.default()))


def table(path: Path | None = None) -> EntityTable:
    return read_table(path) if path else _default_table()


SCHEMES = ("iso3", "ne_adm0_a3", "ne_iso_a3_eh", "name")


def resolve(code_or_name: str, scheme: str, *, entities: EntityTable | None = None) -> str:
    """Our entity code for a producer's code or name under `scheme`; UnknownEntity if absent or ambiguous."""
    t = entities or table()
    if scheme in SOURCE_SCHEMES:
        s = SOURCE_SCHEMES[scheme]
        if code_or_name in s.aliases:
            return resolve(s.aliases[code_or_name], "iso3", entities=t)
        try:
            return resolve(code_or_name, s.base, entities=t)
        except UnknownEntity:
            raise UnknownEntity(
                f"{code_or_name!r} is not an entity under {scheme} (its aliases, then column {s.base}); declare it in "
                "envdash/geo.py SOURCE_SCHEMES if the producer's file has it"
            ) from None
    if scheme not in SCHEMES:
        raise ValueError(f"unknown scheme {scheme!r}: one of {list(SCHEMES)} or a source id in SOURCE_SCHEMES")
    found = t.by(scheme).get(code_or_name, [])
    if not found:
        raise UnknownEntity(f"{code_or_name!r} is not in pipeline/geo/entities.csv column {scheme}")
    if len(found) > 1:
        raise UnknownEntity(
            f"{code_or_name!r} in column {scheme} names {len(found)} entities {[e.iso3 for e in found]}; use iso3"
        )
    return found[0].iso3


def entity(code: str, *, entities: EntityTable | None = None) -> Entity:
    """The row for one of our codes."""
    t = entities or table()
    found = t.by("iso3").get(code)
    if not found:
        raise UnknownEntity(f"{code!r} is not in pipeline/geo/entities.csv")
    return found[0]
