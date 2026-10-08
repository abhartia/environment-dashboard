"""Eurostat: electricity's share of final energy consumption (nrg_ind_fecf), and government R&D budgets for energy
(gba_nabsfin07, objective NABS05).

Inputs (registry entry eurostat, open under Eurostat's reuse policy): two JSON-stat 2.0 responses of the dissemination
API, each filtered by the registry URL to one series per country, and the Statistics Explained glossary page listing
the official EU candidate countries.

Which countries. Eurostat's copyright notice lets anyone reuse its data for any purpose, except data "for countries
other than: Member States of the European Union (EU) Member States of the European Free Trade Association (EFTA)
official EU acceding and candidate countries", which may not be reused commercially. The registry URLs therefore ask
only for the EU27_2020 aggregate, the 27 member states, the four EFTA states and the nine candidate countries in
REUSABLE_GEOS. A response holding any other geo code stops the build, and so does a glossary page that no longer lists
exactly those nine candidates (CANDIDATES_QUOTE), so a change of status is read by a person before it is published.

Values are Eurostat's as published; nothing is computed. nrg_ind_fecf is a ratio Eurostat computes from its energy
balances: final energy consumption of electricity over final energy consumption of all fuels, energy use only (FC_E,
which leaves out non-energy use of fuels), in percent. gba_nabsfin07 is in million euro at current prices; NABS05
Energy covers every form of energy, fossil fuels and nuclear included.

Flags. Each observation keeps Eurostat's status flag and its label from the response ("e" estimated, "p"
provisional, "b" break in time series, "d" definition differs, and their combinations) as a note; a flag containing
"p" makes the observation preliminary. A cell flagged without a value (for example "|C", confidential) is published
as missing with the flag as the reason. Cells with neither value nor flag are not in the response and are not
published.

Geo codes are Eurostat's two-letter codes (EL for Greece), mapped to ISO 3166-1 alpha-3 in REUSABLE_GEOS; EU27_2020
is EU27.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from envdash import textmatch
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "eurostat"
FECF = Input(SOURCE, "nrg-ind-fecf-electricity")
GBARD = Input(SOURCE, "gba-nabsfin07-energy")
CANDIDATES = Input(SOURCE, "candidate-countries")
ELECTRICITY = "electricity.eurostat.share-of-final-energy"
RD_BUDGET = "rd-budget.eurostat.energy"

EU_MEMBERS = {
    "BE": "BEL", "BG": "BGR", "CZ": "CZE", "DK": "DNK", "DE": "DEU", "EE": "EST", "IE": "IRL", "EL": "GRC",
    "ES": "ESP", "FR": "FRA", "HR": "HRV", "IT": "ITA", "CY": "CYP", "LV": "LVA", "LT": "LTU", "LU": "LUX",
    "HU": "HUN", "MT": "MLT", "NL": "NLD", "AT": "AUT", "PL": "POL", "PT": "PRT", "RO": "ROU", "SI": "SVN",
    "SK": "SVK", "FI": "FIN", "SE": "SWE",
}  # fmt: skip
EFTA = {"IS": "ISL", "LI": "LIE", "NO": "NOR", "CH": "CHE"}
CANDIDATE_COUNTRIES = {
    "AL": "ALB", "BA": "BIH", "GE": "GEO", "MD": "MDA", "ME": "MNE", "MK": "MKD", "RS": "SRB", "TR": "TUR", "UA": "UKR",
}  # fmt: skip
REUSABLE_GEOS = {"EU27_2020": "EU27", **EU_MEMBERS, **EFTA, **CANDIDATE_COUNTRIES}
# The glossary entry "Candidate countries" (Statistics Explained), as read on 2026-10-08.
CANDIDATES_QUOTE = (
    "At present there are nine official candidate countries for membership of the European Union (EU) : Bosnia and "
    "Herzegovina (BA) Montenegro (ME) Moldova (MD) North Macedonia (MK) Georgia (GE) Albania (AL) Serbia (RS) Türkiye "
    "(TR) Ukraine (UA)"
)


class EurostatFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Cell:
    geo: str
    time: str
    value: float | None
    flag: str | None


@dataclass(frozen=True)
class Dataset:
    code: str
    label: str
    updated: str
    fixed: dict[str, str]
    """The single category of every dimension other than geo and time."""
    flag_labels: dict[str, str]
    cells: list[Cell]
    """In geo order of the response, then time order."""


def read_jsonstat(raw: bytes, code: str, fixed: dict[str, str]) -> Dataset:
    doc = json.loads(raw)
    ext = doc.get("extension", {})
    if doc.get("class") != "dataset" or doc.get("version") != "2.0" or ext.get("id") != code.upper():
        raise EurostatFormatError(f"not a JSON-stat 2.0 dataset {code}: class {doc.get('class')!r}, id {ext.get('id')}")
    ids, size = doc["id"], doc["size"]
    if ids[-2:] != ["geo", "time"]:
        raise EurostatFormatError(f"{code}: dimensions {ids}, expected geo and time last")
    for dim, want in fixed.items():
        cats = list(doc["dimension"][dim]["category"]["index"])
        if cats != [want]:
            raise EurostatFormatError(f"{code}: dimension {dim} is {cats}, expected only {want!r}")
    if set(ids[:-2]) != set(fixed):
        raise EurostatFormatError(f"{code}: dimensions {ids[:-2]} other than geo and time, expected {sorted(fixed)}")

    def ordered(dim: str) -> list[str]:
        index = doc["dimension"][dim]["category"]["index"]
        return sorted(index, key=index.__getitem__)

    geos, times = ordered("geo"), ordered("time")
    if [len(geos), len(times)] != size[-2:] or any(n != 1 for n in size[:-2]):
        raise EurostatFormatError(f"{code}: size {size} does not match its categories")
    outside = [g for g in geos if g not in REUSABLE_GEOS]
    if outside:
        raise EurostatFormatError(
            f"{code}: geo codes {outside} are not EU, EFTA or candidate countries, whose data Eurostat licenses for "
            "commercial reuse only with the exceptions in its copyright notice"
        )
    values, flags = doc.get("value", {}), doc.get("status", {})
    if isinstance(values, list) or isinstance(flags, list):
        raise EurostatFormatError(f"{code}: expected sparse value and status objects")
    labels = (ext.get("status") or {}).get("label", {})
    cells: list[Cell] = []
    for gi, g in enumerate(geos):
        for ti, t in enumerate(times):
            k = str(gi * len(times) + ti)
            v, f = values.get(k), flags.get(k)
            if v is None and f is None:
                continue
            if f is not None and f not in labels:
                raise EurostatFormatError(f"{code} {g} {t}: flag {f!r} has no label in the response")
            if v is not None and (isinstance(v, bool) or not isinstance(v, int | float)):
                raise EurostatFormatError(f"{code} {g} {t}: value {v!r} is not a number")
            cells.append(Cell(g, t, None if v is None else float(v), f))
    return Dataset(code, doc["label"], doc["updated"][:10], fixed, labels, cells)


def check_candidates(raw: bytes) -> None:
    text = textmatch.document_text(raw, "text/html")
    if not textmatch.contains(text, CANDIDATES_QUOTE):
        raise EurostatFormatError(
            "Eurostat's glossary no longer lists exactly the nine candidate countries requested; re-read the copyright "
            "notice's exception before publishing data for a country that has changed status"
        )


def observations(ds: Dataset) -> list[Observation]:
    obs: list[Observation] = []
    for c in ds.cells:
        note = None if c.flag is None else f"Eurostat flag '{c.flag}': {ds.flag_labels[c.flag]}."
        status = "preliminary" if c.flag is not None and "p" in c.flag else "final"
        common = {"entity": REUSABLE_GEOS[c.geo], "period": c.time, "status": status, "note": note}
        if c.value is None:
            reason = f"Eurostat gives no value, flagged '{c.flag}': {ds.flag_labels[c.flag]}."  # type: ignore[index]
            obs.append(Observation(value=None, missing_reason=reason, **common))  # type: ignore[arg-type]
        else:
            obs.append(Observation(value=c.value, **common))  # type: ignore[arg-type]
    return obs


def _step_read(f: InputFile, ds: Dataset) -> str:
    return (
        f"Read Eurostat dataset {ds.code} ('{ds.label}', updated {ds.updated}) from the dissemination API (fetched "
        f"{f.snapshot.date_accessed}, sha256 {f.snapshot.sha256[:12]}…), filtered to "
        + ", ".join(f"{k} {v}" for k, v in ds.fixed.items() if k != "freq")
        + "."
    )


GEO_STEP = (
    "Kept only the EU, its member states, the EFTA states and the official candidate countries, whose data Eurostat "
    "lets anyone reuse; checked the candidates against Eurostat's glossary page; mapped Eurostat's two-letter codes "
    "to ISO 3166-1 alpha-3 (EU27_2020 to EU27)."
)
FLAG_STEP = (
    "Kept Eurostat's status flags as notes, with their labels from the response; a provisional flag marks the value "
    "preliminary, and a flagged cell without a value is published as missing with the flag as the reason."
)


def _run(inp: Input, code: str, fixed: dict[str, str]):
    def run(files: dict[str, InputFile]) -> Result:
        check_candidates(files[CANDIDATES.key].path.read_bytes())
        f = files[inp.key]
        ds = read_jsonstat(f.path.read_bytes(), code, fixed)
        obs = observations(ds)
        return Result(
            observations=obs,
            vintage=f"{code} updated {ds.updated}",
            date_published=ds.updated,
            steps=[_step_read(f, ds), GEO_STEP, FLAG_STEP, "Published every value as Eurostat gives it."],
        )

    return run


FECF_FIXED = {"freq": "A", "nrg_bal": "FC_E", "siec": "E7000", "unit": "PC"}
GBARD_FIXED = {"freq": "A", "nabs07": "NABS05", "unit": "MIO_EUR"}
GEOGRAPHY = (
    "The European Union (27 member states since 2020), its member states, the EFTA states and the official EU "
    "candidate countries that report to Eurostat"
)


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=ELECTRICITY,
                title="Electricity's share of final energy use",
                description="How much of the energy that homes, businesses, industry and transport use comes as "
                "electricity, as a share of all the fuels and electricity they use, for the European Union and "
                "European countries since 1990, as calculated by Eurostat. Non-energy uses of fuels, such as "
                "feedstocks for plastics, are not counted.",
                kind="series",
                unit=Unit(code="percent", label="percent of final energy consumption (energy use)", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography=GEOGRAPHY,
                    basis="Eurostat's ratio of final energy consumption of electricity (SIEC E7000) to final energy "
                    "consumption of all fuels, energy use only (FC_E), from its energy balances.",
                ),
                geo_coverage="mixed",
                headline_entity="EU27",
                dimensions=(),
            ),
            inputs=(FECF, CANDIDATES),
            run=_run(FECF, "nrg_ind_fecf", FECF_FIXED),
            module_file=Path(__file__),
            validation=Validation(min_rows=1000, value_range=(0.0, 100.0)),
        ),
        Transform(
            spec=Spec(
                id=RD_BUDGET,
                title="Government R&D budgets for energy (Europe)",
                description="How much European governments plan to spend each year on research and development "
                "whose main aim is energy, in million euro at current prices, as reported to Eurostat. This is all "
                "energy research, including fossil fuels and nuclear power as well as renewables and efficiency, and "
                "it is a budget allocation, not money spent.",
                kind="series",
                unit=Unit(code="EUR-million", label="million euro (current prices)", short="million €"),
                display=Display(decimals=1),
                scope=Scope(
                    geography=GEOGRAPHY,
                    basis="Government budget allocations for R&D (GBARD) for the socio-economic objective Energy "
                    "(NABS 2007 chapter 05), current prices, as reported to Eurostat under the Frascati Manual.",
                ),
                geo_coverage="mixed",
                headline_entity="EU27",
                dimensions=(),
            ),
            inputs=(GBARD, CANDIDATES),
            run=_run(GBARD, "gba_nabsfin07", GBARD_FIXED),
            module_file=Path(__file__),
            validation=Validation(min_rows=400, value_range=(0.0, 50_000.0)),
        ),
    ]
