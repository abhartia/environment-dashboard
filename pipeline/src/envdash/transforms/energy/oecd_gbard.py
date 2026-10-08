"""OECD government budget allocations for R&D (GBARD), objective Energy: what governments budget for energy research,
in US dollars at purchasing power parities and constant 2020 prices.

Input: the SDMX-CSV (with labels) of dataflow OECD.STI.STP:DSD_RDS_GOV@DF_GBARD_NABS07(1.0), filtered by the registry
URL to MEASURE C (GBARD), SEO NABS05 (Energy), FUNDMODE _T (all funding modes), TRANSCOORD _Z, UNIT_MEASURE USD_PPP
and PRICE_BASE Q (constant prices), every economy and year (registry entry oecd-gbard, open under the OECD terms).

The build stops unless every row is that one series per economy, in millions (UNIT_MULT 6) of US dollars with base
period 2020, and every REF_AREA is an entity in pipeline/geo/entities.csv by ISO 3166-1 alpha-3 code (TWN is Chinese
Taipei). Values are the OECD's, as published: the OECD converts national currencies at its PPPs and deflates to 2020
prices; nothing is converted here. NABS05 Energy covers every form of energy, so this is all energy R&D in government
budgets, fossil fuels and nuclear included, and budgets are plans, not money spent.

Flags. The OECD gives up to three observation status codes per value (OBS_STATUS, OBS_STATUS_2, OBS_STATUS_3: B time
series break, D definition differs, E estimated value, P provisional value) and an auxiliary one (AUX_OBS_STATUS, e.g.
S2 "Unrevised breakdown not adding to the revised total"). Each value keeps them, with the OECD's labels from the
file, as its note; a value with P is preliminary. An empty value would be published as missing with its flags as the
reason (this vintage has none).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from envdash import geo
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "oecd-gbard"
CSV = Input(SOURCE, "gbard-energy-usd-ppp-2020")
INDICATOR = "rd-budget.oecd.energy"
DATAFLOW = "OECD.STI.STP:DSD_RDS_GOV@DF_GBARD_NABS07(1.0)"

FIXED = {
    "STRUCTURE": "DATAFLOW",
    "STRUCTURE_ID": DATAFLOW,
    "FREQ": "A",
    "MEASURE": "C",
    "SEO": "NABS05",
    "FUNDMODE": "_T",
    "TRANSCOORD": "_Z",
    "UNIT_MEASURE": "USD_PPP",
    "PRICE_BASE": "Q",
    "UNIT_MULT": "6",
    "BASE_PER": "2020",
    "CURRENCY": "USD",
}
FLAG_COLUMNS = (
    ("OBS_STATUS", "Observation status"),
    ("OBS_STATUS_2", "Observation status 2"),
    ("OBS_STATUS_3", "Observation status 3"),
    ("AUX_OBS_STATUS", "Aux observation status"),
    ("AUX_OBS_STATUS_2", "Aux observation status 2"),
    ("AUX_OBS_STATUS_3", "Aux observation status 3"),
)
PROVISIONAL = "P"


class OecdFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    entity: str
    year: str
    value: float | None
    flags: tuple[tuple[str, str], ...]
    """(code, label) of each flag given, in column order."""


def read_rows(raw: bytes) -> list[Row]:
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = next(reader)
    needed = [*FIXED, "REF_AREA", "TIME_PERIOD", "OBS_VALUE", "CONF_STATUS"]
    needed += [c for pair in FLAG_COLUMNS for c in pair]
    missing = [c for c in needed if c not in header]
    if missing:
        raise OecdFormatError(f"columns missing: {missing}")
    col = {name: header.index(name) for name in needed}
    out: list[Row] = []
    for line in reader:
        r = {name: line[i] for name, i in col.items()}
        where = f"{r['REF_AREA']} {r['TIME_PERIOD']}"
        for name, want in FIXED.items():
            if r[name] != want:
                raise OecdFormatError(f"{where}: {name} is {r[name]!r}, expected {want!r}")
        if r["CONF_STATUS"]:
            raise OecdFormatError(f"{where}: confidentiality status {r['CONF_STATUS']!r} is not read by this transform")
        if not (len(r["TIME_PERIOD"]) == 4 and r["TIME_PERIOD"].isdigit()):
            raise OecdFormatError(f"{where}: TIME_PERIOD is not a year")
        flags = []
        for code_col, label_col in FLAG_COLUMNS:
            if r[code_col]:
                if not r[label_col]:
                    raise OecdFormatError(f"{where}: flag {r[code_col]!r} has no label")
                flags.append((r[code_col], r[label_col]))
        try:
            value = float(r["OBS_VALUE"]) if r["OBS_VALUE"] else None
        except ValueError:
            raise OecdFormatError(f"{where}: OBS_VALUE {r['OBS_VALUE']!r} is not a number") from None
        out.append(Row(geo.resolve(r["REF_AREA"], "iso3"), r["TIME_PERIOD"], value, tuple(flags)))
    out.sort(key=lambda x: (x.entity, x.year))
    keys = [(x.entity, x.year) for x in out]
    if len(set(keys)) != len(keys):
        raise OecdFormatError("more than one value for an economy and year")
    return out


def observations(rows: list[Row]) -> list[Observation]:
    obs: list[Observation] = []
    for r in rows:
        note = "; ".join(f"OECD flag {c}: {lbl}" for c, lbl in r.flags) + "." if r.flags else None
        status = "preliminary" if any(c == PROVISIONAL for c, _ in r.flags) else "final"
        common = {"entity": r.entity, "period": r.year, "status": status, "note": note}
        if r.value is None:
            reason = "The OECD gives no value" + (f" ({note.rstrip('.')})." if note else ".")
            obs.append(Observation(value=None, missing_reason=reason, **common))  # type: ignore[arg-type]
        else:
            obs.append(Observation(value=r.value, **common))  # type: ignore[arg-type]
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[CSV.key]
    rows = read_rows(f.path.read_bytes())
    obs = observations(rows)
    years = sorted({r.year for r in rows})
    economies = sorted({r.entity for r in rows})
    return Result(
        observations=obs,
        vintage=f"OECD GBARD by NABS 2007, retrieved {f.snapshot.date_accessed}",
        steps=[
            f"Read the OECD SDMX-CSV for dataflow {DATAFLOW} (fetched {f.snapshot.date_accessed}, sha256 "
            f"{f.snapshot.sha256[:12]}…), filtered to GBARD for the objective Energy (NABS05), all funding modes, in "
            "millions of US dollars at PPP and constant 2020 prices, and checked that every row is that series.",
            f"Kept every value as published, for {len(economies)} economies, {years[0]}–{years[-1]}, matched to "
            "pipeline/geo/entities.csv by ISO 3166-1 alpha-3 code.",
            "Kept the OECD's status flags (break in series, definition differs, estimated, provisional, and auxiliary "
            "flags) as notes, with the OECD's labels; a provisional value is marked preliminary.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Government R&D budgets for energy",
                description="How much governments plan to spend each year on research and development whose main "
                "aim is energy, in US dollars at 2020 prices and purchasing power, as reported to the OECD, for OECD "
                "members and some partner economies since 1981. This is all energy research, including fossil fuels "
                "and nuclear power as well as renewables and efficiency, and it is a budget allocation, not money "
                "spent.",
                kind="series",
                unit=Unit(
                    code="USD-PPP-2020-million",
                    label="million US dollars at purchasing power parities, constant 2020 prices",
                    short="million $ (2020 PPP)",
                ),
                display=Display(decimals=0),
                scope=Scope(
                    geography="OECD members and partner economies that report government R&D budgets to the OECD",
                    basis="Government budget allocations for R&D (GBARD) for the socio-economic objective Energy "
                    "(NABS 2007 chapter 05), all funding modes, converted by the OECD to US dollars at purchasing "
                    "power parities and constant 2020 prices.",
                ),
                geo_coverage="country",
                headline_entity="USA",
            ),
            inputs=(CSV,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=1000, value_range=(0.0, 100_000.0)),
        )
    ]
