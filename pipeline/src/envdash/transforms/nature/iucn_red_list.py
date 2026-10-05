"""IUCN Red List version 2026-1, as the Darwin Core checklist IUCN publishes on GBIF: the number of assessed species
that are threatened, and their share of all assessed species, overall and for nine taxonomic groups.

Input. The pinned archive iucn-2026-1.zip (iucn-red-list-gbif/checklist-2026-1): tab-separated, no header, UTF-8, no
quoting. meta.xml defines the columns; the transform reads meta.xml and stops unless the columns it uses sit at the
indexes below. taxon.txt has one row per accepted taxon (rank species, variety or plant subspecies) and per synonym;
distribution.txt has, for every accepted taxon, one row whose locality is "Global" with the global Red List category
in iucn threatStatus. eml.xml's citation names the version ("Version 2026-1"), which must equal the version in the
archive's URL.

What is counted. Species only (taxonRank "species", taxonomicStatus "accepted"), as IUCN's own totals count species;
varieties and subspecies are left out. Each species must have exactly one Global distribution row. Threatened =
Critically Endangered + Endangered + Vulnerable, IUCN's definition. Categories are matched exactly against CATEGORIES;
the archive also carries the lower-case categories of assessments made under the 1994 criteria ("near threatened",
"least concern", "conservation dependent", i.e. Lower Risk), which are not threatened. Any other category stops the
transform.

Share = threatened species / all assessed species in the group × 100, with every category in the denominator
(including Extinct, Extinct in the Wild and Data Deficient). This is the share of species that have been assessed,
not of all species: assessment is near-complete for birds, mammals, amphibians, sharks and rays, but covers a small,
non-random part of insects, plants and fungi.

Groups (GROUPS): all species; seven classes (MAMMALIA, AVES, AMPHIBIA, REPTILIA, ACTINOPTERYGII, CHONDRICHTHYES,
INSECTA) and two kingdoms (PLANTAE, FUNGI), matched exactly on the archive's kingdom and class columns.

Publisher check: IUCN's summary statistics for 2026-1 (iucnredlist.org) cannot be read by a script (HTTP 403), so
there is none. The registry entry records that the research reproduced 175,909 species and 49,505 threatened from this
archive; tests/test_nature_iucn_red_list.py asserts the same numbers from the snapshot.
"""

from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "iucn-red-list-gbif"
CHECKLIST = Input(SOURCE, "checklist-2026-1")
DWC = "http://rs.tdwg.org/dwc/terms/"
TEXT_NS = "{http://rs.tdwg.org/dwc/text/}"
# meta.xml term -> index this transform relies on.
TAXON_FIELDS = {
    "id": 0,
    DWC + "kingdom": 2,
    DWC + "class": 4,
    DWC + "taxonRank": 10,
    DWC + "taxonomicStatus": 12,
}
DISTRIBUTION_FIELDS = {
    "coreid": 0,
    DWC + "locality": 2,
    "http://iucn.org/terms/threatStatus": 5,
}
GLOBAL = "Global"
SPECIES = "species"
ACCEPTED = "accepted"
VERSION_IN_URL = re.compile(r"/iucn-(\d{4}-\d)\.zip$")
VERSION_IN_CITATION = re.compile(r"Version (\d{4}-\d)\.")

# Category as printed -> threatened?
CATEGORIES: dict[str, bool] = {
    "Extinct": False,
    "Extinct in the Wild": False,
    "Critically Endangered": True,
    "Endangered": True,
    "Vulnerable": True,
    "Near Threatened": False,
    "Least Concern": False,
    "Data Deficient": False,
    # 1994 criteria (Lower Risk subcategories), printed in lower case in the archive.
    "near threatened": False,
    "least concern": False,
    "conservation dependent": False,
}

# group id -> (label, kingdom or None, class or None)
GROUPS: dict[str, tuple[str, str | None, str | None]] = {
    "all": ("All assessed species", None, None),
    "mammals": ("Mammals", "ANIMALIA", "MAMMALIA"),
    "birds": ("Birds", "ANIMALIA", "AVES"),
    "amphibians": ("Amphibians", "ANIMALIA", "AMPHIBIA"),
    "reptiles": ("Reptiles", "ANIMALIA", "REPTILIA"),
    "ray-finned-fishes": ("Ray-finned fishes", "ANIMALIA", "ACTINOPTERYGII"),
    "sharks-rays-chimaeras": ("Sharks, rays and chimaeras", "ANIMALIA", "CHONDRICHTHYES"),
    "insects": ("Insects", "ANIMALIA", "INSECTA"),
    "plants": ("Plants", "PLANTAE", None),
    "fungi": ("Fungi", "FUNGI", None),
}


class IucnFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Tally:
    assessed: dict[str, int]
    threatened: dict[str, int]
    categories: dict[str, int]
    """All species by category as printed."""
    other_ranks: dict[str, int]
    """Accepted taxa below species, by rank, left out."""


def check_meta(raw: bytes) -> None:
    root = ET.fromstring(raw)
    for tag, location, fields in (
        ("core", "taxon.txt", TAXON_FIELDS),
        ("extension", "distribution.txt", DISTRIBUTION_FIELDS),
    ):
        found = None
        for el in root.findall(TEXT_NS + tag):
            loc = el.find(f"{TEXT_NS}files/{TEXT_NS}location")
            if loc is not None and loc.text == location:
                found = el
        if found is None:
            raise IucnFormatError(f"meta.xml has no {tag} for {location}")
        if (found.get("fieldsTerminatedBy"), found.get("fieldsEnclosedBy"), found.get("ignoreHeaderLines")) != (
            "\\t",
            "",
            "0",
        ):
            raise IucnFormatError(f"meta.xml: {location} is not tab-separated, unquoted, without a header")
        indexes = {f.get("term"): int(f.get("index", "-1")) for f in found.findall(TEXT_NS + "field")}
        key = found.find(TEXT_NS + ("id" if tag == "core" else "coreid"))
        indexes["id" if tag == "core" else "coreid"] = int(key.get("index", "-1")) if key is not None else -1
        for term, index in fields.items():
            if indexes.get(term) != index:
                raise IucnFormatError(f"meta.xml: {location} {term} is at {indexes.get(term)}, expected {index}")


def version_of(url: str, eml: bytes) -> str:
    m = VERSION_IN_URL.search(url)
    c = VERSION_IN_CITATION.search(eml.decode("utf-8"))
    if not m or not c or m.group(1) != c.group(1):
        raise IucnFormatError(f"the archive URL {url!r} and eml.xml's citation do not name one Red List version")
    return m.group(1)


def _split(line: bytes, width: int) -> list[str]:
    f = line.decode("utf-8").rstrip("\n").split("\t")
    if len(f) < width:
        raise IucnFormatError(f"a row has {len(f)} fields, fewer than {width}")
    return f


def tally(taxon_lines, distribution_lines) -> Tally:
    species: dict[str, tuple[str, str]] = {}
    other_ranks: Counter[str] = Counter()
    for line in taxon_lines:
        f = _split(line, 13)
        if f[12] != ACCEPTED:
            continue
        if f[0] in species:
            raise IucnFormatError(f"taxon {f[0]} is listed twice")
        if f[10] == SPECIES:
            species[f[0]] = (f[2], f[4])
        else:
            other_ranks[f[10]] += 1
    category_of: dict[str, str] = {}
    for line in distribution_lines:
        f = _split(line, 6)
        if f[2] != GLOBAL or f[0] not in species:
            continue
        if f[0] in category_of:
            raise IucnFormatError(f"species {f[0]} has more than one Global row")
        if f[5] not in CATEGORIES:
            raise IucnFormatError(f"species {f[0]}: unknown Red List category {f[5]!r}")
        category_of[f[0]] = f[5]
    missing = [t for t in species if t not in category_of]
    if missing:
        raise IucnFormatError(f"{len(missing)} species have no Global category, e.g. {missing[:5]}")
    assessed: Counter[str] = Counter()
    threatened: Counter[str] = Counter()
    for t, (kingdom, cls) in species.items():
        for g, (_, k, c) in GROUPS.items():
            if (k is None or k == kingdom) and (c is None or c == cls):
                assessed[g] += 1
                threatened[g] += CATEGORIES[category_of[t]]
    return Tally(
        {g: assessed[g] for g in GROUPS},
        {g: threatened[g] for g in GROUPS},
        dict(Counter(category_of.values())),
        dict(other_ranks),
    )


@functools.lru_cache(maxsize=1)
def _read(path: Path, url: str) -> tuple[str, Tally]:
    with zipfile.ZipFile(path) as z:
        check_meta(z.read("meta.xml"))
        version = version_of(url, z.read("eml.xml"))
        with z.open("taxon.txt") as t, z.open("distribution.txt") as d:
            return version, tally(t, d)


def _steps(version: str, t: Tally) -> list[str]:
    cats = "; ".join(f"{c} {n:,}" for c, n in sorted(t.categories.items(), key=lambda kv: -kv[1]))
    ranks = ", ".join(f"{n:,} {r}" for r, n in sorted(t.other_ranks.items()))
    groups = "; ".join(
        f"{label}: kingdom {k}" + (f", class {c}" if c else "") for g, (label, k, c) in GROUPS.items() if g != "all"
    )
    return [
        f"Read meta.xml, eml.xml, taxon.txt and distribution.txt from the IUCN Red List version {version} archive on "
        "GBIF; checked the column positions against meta.xml and the version against eml.xml's citation.",
        f"Counted accepted taxa of rank species ({t.assessed['all']:,}), each by the category of its single Global "
        f"distribution row: {cats}. Left out accepted taxa below species ({ranks}).",
        "Threatened = Critically Endangered + Endangered + Vulnerable. The lower-case categories are assessments "
        "under IUCN's 1994 criteria (Lower Risk) and are counted as not threatened.",
        f"Groups, matched exactly on the archive's kingdom and class: {groups}.",
    ]


def _run_share(files: dict[str, InputFile]) -> Result:
    f = files[CHECKLIST.key]
    version, t = _read(f.path, str(f.snapshot.url))
    empty = [g for g in GROUPS if t.assessed[g] == 0]
    if empty:
        raise IucnFormatError(f"no assessed species in group(s) {empty}: the archive or GROUPS has changed")
    hundred = Decimal(100)
    obs = [
        Observation(
            entity="WLD",
            period=version[:4],
            value=float(Decimal(t.threatened[g]) / Decimal(t.assessed[g]) * hundred),
            dims={"group": g},
        )
        for g in GROUPS
    ]
    return Result(
        observations=obs,
        vintage=version,
        steps=[
            *_steps(version, t),
            "Share = threatened species / all assessed species in the group × 100 (exact decimal arithmetic), with "
            "every category, including Extinct and Data Deficient, in the denominator.",
        ],
        changes="share of assessed species that are threatened calculated from the species' Red List categories.",
    )


def _run_count(files: dict[str, InputFile]) -> Result:
    f = files[CHECKLIST.key]
    version, t = _read(f.path, str(f.snapshot.url))
    obs = [
        Observation(entity="WLD", period=version[:4], value=float(t.threatened[g]), dims={"group": g}) for g in GROUPS
    ]
    return Result(
        observations=obs,
        vintage=version,
        steps=_steps(version, t),
        changes="threatened species counted from the species' Red List categories.",
    )


_DIMENSION = Dimension(
    id="group", label="Group", values=[DimensionValue(id=g, label=label) for g, (label, _, _) in GROUPS.items()]
)
_BASIS = (
    "Species assessed for the IUCN Red List (global assessments); threatened = Critically Endangered, Endangered or "
    "Vulnerable. Only assessed species are counted: birds, mammals, amphibians, sharks and rays are almost fully "
    "assessed, insects, plants and fungi only in small, non-random part, so their figures describe the assessed "
    "species, not the whole group. The period is the year of the Red List version."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="species.iucn-red-list.threatened-share",
                title="Share of assessed species that are threatened with extinction",
                description="Of the species assessed for the IUCN Red List, the percentage listed as Critically "
                "Endangered, Endangered or Vulnerable, for all assessed species and for nine groups, in the "
                "current version of the Red List.",
                kind="derived",
                unit=Unit(code="percent", label="percent of assessed species", short="%"),
                display=Display(decimals=0),
                scope=Scope(
                    geography="World (global Red List assessments)",
                    basis=_BASIS + " Denominator: all assessed species in the group, including Extinct, Extinct in "
                    "the Wild and Data Deficient.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("group", "all"),),
            ),
            inputs=(CHECKLIST,),
            run=_run_share,
            module_file=here,
            validation=Validation(min_rows=len(GROUPS), value_range=(0.0, 100.0)),
        ),
        Transform(
            spec=Spec(
                id="species.iucn-red-list.threatened-count",
                title="Number of species threatened with extinction",
                description="How many of the species assessed for the IUCN Red List are listed as Critically "
                "Endangered, Endangered or Vulnerable, in total and for nine groups, in the current version of the "
                "Red List.",
                kind="derived",
                unit=Unit(code="species", label="species", short="species"),
                display=Display(decimals=0),
                scope=Scope(geography="World (global Red List assessments)", basis=_BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("group", "all"),),
            ),
            inputs=(CHECKLIST,),
            run=_run_count,
            module_file=here,
            validation=Validation(min_rows=len(GROUPS), value_range=(0.0, 200_000.0)),
        ),
    ]
