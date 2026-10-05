"""World Bank WDI: access to electricity (EG.ELC.ACCS.ZS), percent of population, for every economy and the world.

Input: the World Bank Indicators API v2 response for EG.ELC.ACCS.ZS, all economies and aggregates, source 2 (WDI),
one page (registry entry wb-wdi, artifact eg-elc-accs-zs), and the API's country list (artifact countries).

Checks, or the build stops: the response is one page holding every row (pages 1, total equal to the rows), sourceid
"2", every row is indicator EG.ELC.ACCS.ZS "Access to electricity (% of population)" with an empty unit, and no row
carries an observation status (the API's flag field). The indicator's source is the World Bank's SDG 7.1.1
Electrification Dataset (registry evidence); its sibling EG.CFT.ACCS.ZS (clean cooking) carries a non-commercial
licence and is not read.

Entities. The country list marks aggregates with region "Aggregates"; every other entry is an economy, matched to
pipeline/geo/entities.csv by its ISO 3 code (the API's XKX is Kosovo, KOS). Channel Islands (CHI) has no entity in the
crosswalk and is not published. Aggregates other than the World (WLD) are not published: income groups and World
Bank regions are classifications of the World Bank, not places.

Values are published as the API gives them (full precision; WDI displays one decimal). Years without a value in the
response (all of 1960-1989 and 2025 in the release of 13 July 2026) have no observation.

Vintage: the response's "lastupdated" date (the registry's {version}).

Publisher check: none. The Tracking SDG7 report that states the world figure is CC BY-NC 3.0 IGO and not registered.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from envdash import geo
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "wb-wdi"
ACCESS = Input(SOURCE, "eg-elc-accs-zs")
COUNTRIES = Input(SOURCE, "countries")
INDICATOR = ("EG.ELC.ACCS.ZS", "Access to electricity (% of population)")
ISO_ALIASES = {"XKX": "KOS"}
NOT_IN_CROSSWALK = {"CHI": "Channel Islands"}


class WdiFormatError(ValueError):
    pass


def economies(raw: bytes) -> dict[str, str]:
    """ISO 3 code -> name of every economy (not an aggregate) in the API's country list."""
    meta, rows = json.loads(raw)
    if int(meta["pages"]) != 1 or int(meta["total"]) != len(rows):
        raise WdiFormatError(f"country list: {meta} does not hold all {len(rows)} rows on one page")
    return {r["id"]: r["name"] for r in rows if r["region"]["value"] != "Aggregates"}


def entity_of(code: str, name: str) -> str | None:
    if code in NOT_IN_CROSSWALK:
        if NOT_IN_CROSSWALK[code] != name:
            raise WdiFormatError(f"{code} is {name!r}, not {NOT_IN_CROSSWALK[code]!r}")
        return None
    return geo.resolve(ISO_ALIASES.get(code, code), "iso3")


def read(raw: bytes, econ: dict[str, str]) -> tuple[list[Observation], str, list[str]]:
    """(observations sorted by entity and year, lastupdated, economies left out)."""
    meta, rows = json.loads(raw, parse_float=Decimal)
    if int(meta["pages"]) != 1 or int(meta["total"]) != len(rows) or meta["sourceid"] != "2":
        raise WdiFormatError(f"response header {meta} is not one complete WDI page of {len(rows)} rows")
    out: dict[tuple[str, str], Observation] = {}
    left_out: set[str] = set()
    for r in rows:
        if (r["indicator"]["id"], r["indicator"]["value"]) != INDICATOR:
            raise WdiFormatError(f"row for {r['indicator']} in the {INDICATOR[0]} response")
        if r["unit"] != "" or r["obs_status"] != "":
            raise WdiFormatError(f"{r['countryiso3code']} {r['date']}: unit {r['unit']!r} / status {r['obs_status']!r}")
        code = r["countryiso3code"]
        if code == "WLD":
            ent: str | None = "WLD"
        elif code in econ:
            ent = entity_of(code, econ[code])
            if ent is None:
                left_out.add(econ[code])
                continue
        else:
            continue  # an aggregate (region, income group, lending group)
        if r["value"] is None:
            continue
        key = (ent, r["date"])
        if key in out:
            raise WdiFormatError(f"two values for {key}")
        out[key] = Observation(entity=ent, period=r["date"], value=float(r["value"]))  # type: ignore[arg-type]
    return [out[k] for k in sorted(out)], meta["lastupdated"], sorted(left_out)


def run(files: dict[str, InputFile]) -> Result:
    econ = economies(files[COUNTRIES.key].path.read_bytes())
    f = files[ACCESS.key]
    obs, updated, left_out = read(f.path.read_bytes(), econ)
    years = sorted({o.period for o in obs})
    n = len({o.entity for o in obs} - {"WLD"})
    return Result(
        observations=obs,
        vintage=updated,
        date_published=updated,
        steps=[
            f"Read the World Bank Indicators API response for {INDICATOR[0]} ('{INDICATOR[1]}'), WDI source 2, last "
            f"updated {updated}, one page holding every row (sha256 {f.snapshot.sha256[:12]}…).",
            f"Kept the World and the {n} economies with a value, matched by ISO 3 code to pipeline/geo/entities.csv "
            "(the API's XKX is Kosovo, KOS), from the API's country list; World Bank regions, income and lending "
            "groups were left out. Not published because they have no entity in the crosswalk: "
            f"{', '.join(left_out) if left_out else 'none'}.",
            f"Published every non-empty value as given, {years[0]}–{years[-1]}; years without a value have no "
            "observation.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="access.wb-wdi.electricity",
                title="Share of people with access to electricity",
                description="The part of each country's and the world's population that has access to electricity, "
                "each year since 1990, from the World Bank's World Development Indicators.",
                kind="series",
                unit=Unit(code="percent", label="percent of population", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Economies, and the world",
                    basis="World Bank indicator EG.ELC.ACCS.ZS, from the SDG 7.1.1 Electrification Dataset: the "
                    "percentage of the population with access to electricity, from data collected from industry, "
                    "national surveys and international sources (the indicator's metadata). The world value is the "
                    "World Bank's population-weighted average and starts in 1998.",
                ),
                geo_coverage="country",
                headline_entity="WLD",
            ),
            inputs=(ACCESS, COUNTRIES),
            run=run,
            module_file=Path(__file__),
            validation=Validation(min_rows=5000, value_range=(0.0, 100.0)),
        )
    ]
