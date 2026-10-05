"""Stechemesser et al. (2024): the climate policy interventions that achieved major emission reductions, by country,
sector and year, with each one's effect size.

Inputs (Zenodo record 12773811, version v4, CC BY 4.0):
- Policy_out.RDS (artifact policy-out), written by 03_policy_matching.R: a tibble of 8 rows, one per country sample
  ("AC1" developed economies, "AC6" developing economies, per the comments of 01_run_break_detection_models.R) and
  sector (Buildings, Electricity, Industry, Transport). Column `out` holds that sample's detected negative structural
  breaks in sectoral emissions (columns id, country_code, time = break year, coef = break size on the log scale, sd,
  tci, min_year, max_year); column `policy_match_2y` holds the CAPMF policy adoptions and tightenings found in the
  same country and sector within two years of each break (keyed by unique_break_identifier
  "<ISO>_<time-2>_<time+2>"). 06_Fig_4.R says "we operate based on the 2y match in the main text".
- EU_policies_label_df.csv (artifact eu-policies-label), written by 02_preprocess_oecd_data.R: the EU policies the
  break detection controls for (EU-Labels, EU-ETS, EU-MEPS), by country (the authors' names without spaces, as in
  the breaks' `id`), sector and year. They are removed from the policy data before matching, and 06_Fig_4.R's notes
  add the breaks they explain by hand ("Additoinal breaks now matched at all (by single EU policy): Buildings
  Czechia, Slovakia (2nd) Industry Romania, Czechia -> +4 for single").

The file is read with envdash.transforms.action.rds, a reader of R's serialization format: pyreadr refuses this file
because its list-columns hold data frames and fitted model objects.

What is published. A break is a successful policy intervention when at least one policy was adopted or tightened in
its country and sector within two years of it: a CAPMF policy in policy_match_2y, or an EU policy in
EU_policies_label_df.csv whose year falls in [time - 2, time + 2]. On the 2026-10-05 snapshot, 69 negative breaks
are detected, 59 have a CAPMF match, 4 more an EU-policy match (Czech Republic and Slovak Republic buildings,
Czech Republic and Romania industry, as the notes list), and 6 have none: 63 interventions, the number the paper
reports. The count is checked on every build against the breaks the notes name, so a changed file cannot silently
change what "successful" means.

Effect size. The authors' own conversion (03_policy_matching.R: "coef_percent = exp(all_together$coef)-1", times
100 in get_effect_size_means): (e^coef − 1) × 100, the percent change in the sector's emissions at the break,
relative to the counterfactual without it. Values are negative (reductions). Each observation is dated by the break
year and carries, as its note, the policies the authors' matching found (CAPMF names as Policy_name_fig_1, with
the year), so the policy mix behind each effect is visible.

Not used: the six unmatched breaks, the statistical-interval and 3-year matches, and the `is` model objects.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path

from envdash.geo import resolve
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.action import rds

SOURCE = "stechemesser-2024"
POLICY_OUT = Input(SOURCE, "policy-out")
EU_LABELS = Input(SOURCE, "eu-policies-label")
INDICATOR = "policy.stechemesser-2024.successful-interventions"
WINDOW = 2

SAMPLES = {"AC1": ("developed", "Developed economies"), "AC6": ("developing", "Developing economies")}
SECTORS = ("Buildings", "Electricity", "Industry", "Transport")
POLICY_OUT_COLUMNS = ["country_sample", "sector", "out", "is", "policy_match", "policy_match_2y", "policy_match_3y"]
EU_COLUMNS = ["", "country", "Module", "Policy_name", "year", "label"]

# The breaks 06_Fig_4.R's notes say are matched only by an EU policy (sector, the authors' country name, break year).
EU_ONLY_IN_NOTES = frozenset(
    {
        ("Buildings", "CzechRepublic", 2005),
        ("Buildings", "SlovakRepublic", 2003),
        ("Industry", "CzechRepublic", 2010),
        ("Industry", "Romania", 2009),
    }
)
EXPECTED_BREAKS = 69
EXPECTED_SUCCESSFUL = 63

UNIT = Unit(code="percent", label="percent change in the sector's emissions at the break", short="%")


class StechemesserFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Break:
    sample: str
    sector: str
    name: str
    iso: str
    year: int
    coef: float
    cas: tuple[tuple[str, int], ...]
    """CAPMF policies matched within two years: (Policy_name_fig_1, year), sorted."""
    eu: tuple[tuple[str, int], ...] = ()

    @property
    def effect_percent(self) -> float:
        return (math.exp(self.coef) - 1) * 100

    @property
    def successful(self) -> bool:
        return bool(self.cas or self.eu)


def _year(v: object, where: str) -> int:
    if not isinstance(v, float) or not v.is_integer():
        raise StechemesserFormatError(f"{where}: {v!r} is not a whole year")
    return int(v)


def read_breaks(raw: bytes) -> list[Break]:
    """Every negative break in Policy_out.RDS with its CAPMF matches in the two-year window."""
    tbl = rds.read_rds(raw)
    if tbl.strings("names") != POLICY_OUT_COLUMNS:
        raise StechemesserFormatError(f"Policy_out columns {tbl.strings('names')} != {POLICY_OUT_COLUMNS}")
    samples = rds.column(tbl, "country_sample")
    sectors = rds.column(tbl, "sector")
    outs = rds.column(tbl, "out")
    matches = rds.column(tbl, "policy_match_2y")
    if sorted(zip(samples, sectors, strict=True)) != sorted((s, x) for s in SAMPLES for x in SECTORS):
        raise StechemesserFormatError(f"Policy_out rows {list(zip(samples, sectors, strict=True))}")
    breaks: list[Break] = []
    for sample, sector, out, match in zip(samples, sectors, outs, matches, strict=True):
        where = f"{sample} {sector}"
        n = rds.nrow(out)
        ids, isos, times, coefs = (rds.column(out, c) for c in ("id", "country_code", "time", "coef"))
        policies: dict[str, set[tuple[str, int]]] = {}
        coef_of: dict[str, float] = {}
        if rds.nrow(match):
            keys = rds.column(match, "unique_break_identifier")
            names = rds.column(match, "Policy_name_fig_1")
            years = rds.column(match, "year")
            modules = rds.column(match, "Module")
            mcoefs = rds.column(match, "coeff")
            for k, name, y, m, c in zip(keys, names, years, modules, mcoefs, strict=True):
                if m != sector or not isinstance(name, str) or not isinstance(y, int):
                    raise StechemesserFormatError(f"{where}: match {k} has Module {m!r}, policy {name!r}, year {y!r}")
                if coef_of.setdefault(k, c) != c:
                    raise StechemesserFormatError(f"{where}: break {k} carries two coefficients")
                policies.setdefault(k, set()).add((name, y))
        seen: set[str] = set()
        for i in range(n):
            year = _year(times[i], f"{where} row {i + 1} time")
            coef = coefs[i]
            if not isinstance(coef, float) or not coef < 0:
                raise StechemesserFormatError(f"{where} {ids[i]} {year}: coefficient {coef!r} is not negative")
            key = f"{isos[i]}_{year - WINDOW}_{year + WINDOW}"
            if key in seen:
                raise StechemesserFormatError(f"{where}: two breaks share the window {key}")
            seen.add(key)
            if key in coef_of and coef_of[key] != coef:
                raise StechemesserFormatError(f"{where}: matches for {key} carry another break's coefficient")
            breaks.append(
                Break(SAMPLES[sample][0], sector, ids[i], isos[i], year, coef, tuple(sorted(policies.pop(key, ()))))
            )
        if policies:
            raise StechemesserFormatError(f"{where}: matches for no detected break: {sorted(policies)}")
    return breaks


def read_eu_policies(raw: bytes) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """(sector, country as the authors write it) -> [(EU policy, year)]."""
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
    if not rows or rows[0] != EU_COLUMNS:
        raise StechemesserFormatError(f"EU_policies_label_df.csv header {rows[:1]} != {EU_COLUMNS}")
    out: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for n, r in enumerate(rows[1:], start=2):
        if len(r) != len(EU_COLUMNS) or r[3] not in ("EU-Labels", "EU-ETS", "EU-MEPS") or r[5] != "1":
            raise StechemesserFormatError(f"EU_policies_label_df.csv line {n}: {r}")
        out.setdefault((r[2], r[1]), []).append((r[3], int(r[4])))
    return out


def with_eu(breaks: list[Break], eu: dict[tuple[str, str], list[tuple[str, int]]]) -> list[Break]:
    return [
        Break(
            b.sample,
            b.sector,
            b.name,
            b.iso,
            b.year,
            b.coef,
            b.cas,
            tuple(sorted(p for p in eu.get((b.sector, b.name), []) if abs(p[1] - b.year) <= WINDOW)),
        )
        for b in breaks
    ]


def check_counts(breaks: list[Break]) -> None:
    """The counts the paper and 06_Fig_4.R's notes give: a changed file stops the build instead of changing them."""
    successful = [b for b in breaks if b.successful]
    eu_only = {(b.sector, b.name, b.year) for b in successful if not b.cas}
    if len(breaks) != EXPECTED_BREAKS or len(successful) != EXPECTED_SUCCESSFUL or eu_only != EU_ONLY_IN_NOTES:
        raise StechemesserFormatError(
            f"{len(breaks)} breaks and {len(successful)} matched (EU-only {sorted(eu_only)}); the replication notes "
            f"give {EXPECTED_BREAKS}, {EXPECTED_SUCCESSFUL} and {sorted(EU_ONLY_IN_NOTES)}"
        )


def _note(b: Break) -> str:
    parts = []
    if b.cas:
        parts.append("CAPMF policies adopted or tightened: " + "; ".join(f"{n} ({y})" for n, y in b.cas))
    if b.eu:
        parts.append("EU policies: " + "; ".join(f"{n} ({y})" for n, y in b.eu))
    return (
        f"Break detected in {b.year}; the authors' matching finds, within {WINDOW} years in this country and sector, "
        + ". ".join(parts)
        + "."
    )


def observations(breaks: list[Break]) -> list[Observation]:
    obs = []
    for b in sorted((b for b in breaks if b.successful), key=lambda b: (b.iso, b.sector, b.year)):
        obs.append(
            Observation(
                entity=resolve(b.iso, "iso3"),
                period=f"{b.year:04d}",
                value=b.effect_percent,
                note=_note(b),
                dims={"sector": b.sector.lower(), "economy_group": b.sample},
            )
        )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    po, eu = files[POLICY_OUT.key], files[EU_LABELS.key]
    breaks = with_eu(read_breaks(po.path.read_bytes()), read_eu_policies(eu.path.read_bytes()))
    check_counts(breaks)
    eu_only = sum(1 for b in breaks if b.successful and not b.cas)
    return Result(
        observations=observations(breaks),
        vintage="Zenodo v4 (2024-07-18)",
        year="2024",
        date_published="2024-07-18",
        steps=[
            f"Read Policy_out.RDS (sha256 {po.snapshot.sha256[:12]}…) with a reader of R's serialization format: "
            f"{len(breaks)} negative structural breaks in sectoral emissions across the developed (AC1) and "
            "developing (AC6) country samples and four sectors, each with the CAPMF policies the authors matched "
            "to it within two years (policy_match_2y, the window used in the paper's main text).",
            f"Read EU_policies_label_df.csv (sha256 {eu.snapshot.sha256[:12]}…), the EU policies the model controls "
            "for, and matched each break to those in force in its country and sector within two years, as the notes "
            f"of 06_Fig_4.R do by hand: {eu_only} breaks are matched only by an EU policy.",
            f"Kept the {EXPECTED_SUCCESSFUL} breaks with at least one matched policy (the paper's successful policy "
            f"interventions); the other {len(breaks) - EXPECTED_SUCCESSFUL} have none and are not published.",
            "Effect size = (e^coefficient − 1) × 100, the authors' conversion of the break coefficient (log scale) to "
            "the percent change in the sector's emissions. Each value's note lists the matched policies.",
        ],
        changes="break coefficients converted from the log scale to percent change, as the authors do; breaks "
        "without a matched policy left out.",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Climate policy interventions that cut emissions (Stechemesser et al. 2024)",
                description="The 63 policy interventions that Stechemesser and colleagues found behind large, "
                "sudden drops in a sector's emissions in 41 countries over two decades: for each, the country, "
                "the sector (buildings, electricity, industry or transport), the year of the drop and its size, "
                "as the percent change in the sector's emissions compared with what the model expects without it. "
                "Each value names the policies adopted or tightened within two years before or after the drop. "
                "Most successful interventions combine several policies; the drop cannot be credited to one policy "
                "alone.",
                kind="derived",
                unit=UNIT,
                display=Display(decimals=1),
                scope=Scope(
                    geography="41 countries (OECD members and large emerging economies), one value per intervention",
                    basis="Detected with machine-learning break detection on sectoral CO2 emissions, 2000–2022; "
                    "policy data from a July 2023 pre-release of the OECD Climate Actions and Policies Measurement "
                    "Framework (CAPMF), plus the EU policies the model controls for. Effect size relative to the "
                    "model's counterfactual, on the log scale converted to percent.",
                ),
                geo_coverage="country",
                headline_entity="GBR",
                dimensions=(
                    Dimension(
                        id="sector",
                        label="Sector",
                        values=[DimensionValue(id=s.lower(), label=s) for s in SECTORS],
                    ),
                    Dimension(
                        id="economy_group",
                        label="Country group",
                        values=[DimensionValue(id=i, label=label) for i, label in SAMPLES.values()],
                    ),
                ),
                headline_dims=(("economy_group", "developed"), ("sector", "electricity")),
            ),
            inputs=(POLICY_OUT, EU_LABELS),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=EXPECTED_SUCCESSFUL, value_range=(-100.0, 0.0)),
            key_files=(Path(rds.__file__),),
        )
    ]
