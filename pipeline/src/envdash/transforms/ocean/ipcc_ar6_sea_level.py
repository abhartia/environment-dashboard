"""IPCC AR6 WGI projections of global mean sea level rise by 2100, by scenario, quoted from SPM statement B.5.3.

Why the SPM and not the data. The projections behind the statement are published under CC BY 4.0 as the IPCC AR6
Sea Level Projections (Garner, Kopp et al. 2021, Zenodo record 6382554; registry entry
ipcc-ar6-sea-level-projections). That record holds four files: ar6.zip (889,784,792 bytes), two regional zips of
8.7 and 9.2 GB, and location_list.lst (station names only). The global quantile files exist only inside ar6.zip, which
is registered as acquisition manual, so no official file small enough for an automatic fetch carries the global
quantiles by scenario (checked on the Zenodo API on 2026-10-05). Until a person records ar6.zip, the numbers are
quoted from the Summary for Policymakers, whose terms make them display-only: shown verbatim with the statement and
page, never redistributed in data/.

What is published. The likely range of global mean sea level rise by 2100 relative to 1995–2014 for the four
scenarios the statement names (SSP1-1.9, SSP1-2.6, SSP2-4.5, SSP5-8.5; it does not name SSP3-7.0), in metres exactly
as printed. The SPM gives no central estimate, so each end of the range is its own value under a `bound` dimension
(likely-low, likely-high); nothing is computed between them. The statement's 2150 ranges and its low-confidence
"approaching 2 m by 2100" are not published here. Status is projection.

Checks. The build stops unless the quote is in the text of PDF page 21 of the snapshot, and unless the ranges read
from the quote's own words equal the table below, scenario by scenario: the table cannot drift from the quote.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.literature import verify_quote

SOURCE = "ipcc-ar6-wg1-spm"
SPM = Input(SOURCE, "spm-pdf")
PDF_PAGE = 21
LOCATOR = "SPM statement B.5.3, p. 21"
YEAR = "2100"

QUOTE = (
    "Relative to 1995–2014, the likely global mean sea level rise by 2100 is 0.28–0.55 m under the very low GHG "
    "emissions scenario (SSP1-1.9); 0.32–0.62 m under the low GHG emissions scenario (SSP1-2.6); 0.44–0.76 m under "
    "the intermediate GHG emissions scenario (SSP2-4.5); and 0.63–1.01 m under the very high GHG emissions scenario "
    "(SSP5-8.5); and by 2150 is 0.37–0.86 m under the very low scenario (SSP1-1.9); 0.46–0.99 m under the low "
    "scenario (SSP1-2.6); 0.66–1.33 m under the intermediate scenario (SSP2-4.5); and 0.98–1.88 m under the very "
    "high scenario (SSP5-8.5) (medium confidence)."
)
SEGMENT_2100 = re.compile(r"the likely global mean sea level rise by 2100 is (.+?); and by 2150 is ")
RANGE = re.compile(r"(\d+\.\d+)–(\d+\.\d+) m under the [A-Za-z ]+?scenario \((SSP\d-\d\.\d)\)")

# (dimension id, label as the SPM names the scenario, SSP label in the quote): likely range in metres, as printed.
SCENARIOS: tuple[tuple[str, str, str], ...] = (
    ("ssp119", "SSP1-1.9 (very low GHG emissions)", "SSP1-1.9"),
    ("ssp126", "SSP1-2.6 (low GHG emissions)", "SSP1-2.6"),
    ("ssp245", "SSP2-4.5 (intermediate GHG emissions)", "SSP2-4.5"),
    ("ssp585", "SSP5-8.5 (very high GHG emissions)", "SSP5-8.5"),
)
LIKELY_2100: dict[str, tuple[str, str]] = {
    "ssp119": ("0.28", "0.55"),
    "ssp126": ("0.32", "0.62"),
    "ssp245": ("0.44", "0.76"),
    "ssp585": ("0.63", "1.01"),
}

SCENARIO_DIM = Dimension(
    id="scenario", label="Scenario", values=[DimensionValue(id=d, label=label) for d, label, _ in SCENARIOS]
)
BOUND_DIM = Dimension(
    id="bound",
    label="End of the likely range",
    values=[
        DimensionValue(id="likely-low", label="Low end of the likely range"),
        DimensionValue(id="likely-high", label="High end of the likely range"),
    ],
)
METRES = Unit(code="m", label="metres", short="m")


class SpmQuoteError(ValueError):
    pass


def ranges_in_quote(quote: str) -> dict[str, tuple[str, str]]:
    """{SSP label: (low, high)} for 2100, read from the quote's own words."""
    seg = SEGMENT_2100.search(quote)
    if not seg:
        raise SpmQuoteError("the quote has no 'by 2100 is ...; and by 2150 is' clause")
    found = RANGE.findall(seg.group(1))
    out = {ssp: (lo, hi) for lo, hi, ssp in found}
    if len(out) != len(found):
        raise SpmQuoteError("a scenario appears twice in the 2100 clause")
    return out


def check_table(quote: str) -> None:
    in_quote = ranges_in_quote(quote)
    table = {ssp: LIKELY_2100[d] for d, _, ssp in SCENARIOS}
    if in_quote != table:
        raise SpmQuoteError(f"the 2100 ranges in the quote {in_quote} differ from the table {table}")


def observations() -> list[Observation]:
    obs: list[Observation] = []
    for d, _, _ in SCENARIOS:
        lo, hi = LIKELY_2100[d]
        if not Decimal(lo) < Decimal(hi):
            raise SpmQuoteError(f"{d}: low end {lo} is not below high end {hi}")
        for bound, v in (("likely-low", lo), ("likely-high", hi)):
            obs.append(
                Observation(
                    entity="WLD",
                    period=YEAR,
                    value=float(Decimal(v)),
                    status="projection",
                    dims={"scenario": d, "bound": bound},
                )
            )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[SPM.key]
    verify_quote(f.path.read_bytes(), PDF_PAGE, QUOTE)
    check_table(QUOTE)
    return Result(
        observations=observations(),
        vintage="AR6 WGI (2021)",
        date_published="2021",
        steps=[
            f"Quoted from {LOCATOR} of the IPCC AR6 Working Group I Summary for Policymakers. The quote was found in "
            f"the text of page {PDF_PAGE} of the PDF snapshot (sha256 {f.snapshot.sha256[:12]}…) before publishing.",
            # No values in the step: display-only numbers stay out of the public catalogue.
            "Value: the likely ranges by 2100 relative to 1995–2014, one per scenario, are published as printed, in "
            "metres, each end of a range as its own value (bound likely-low or likely-high). The build reads the "
            "ranges from the quote's words and stops unless they equal the published table. The SPM gives no central "
            "estimate, and none is computed.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=LOCATOR, quote=QUOTE),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="gmsl.ipcc-ar6.rise-2100-likely",
                title="Global sea level rise by 2100 by emissions scenario, likely range (IPCC AR6)",
                description="The IPCC's assessed likely range of global mean sea level rise by 2100, relative to "
                "1995–2014, under four emissions scenarios from very low (SSP1-1.9) to very high (SSP5-8.5), "
                "medium confidence. Quoted from the Summary for Policymakers of the IPCC Sixth Assessment Report, "
                "Working Group I (2021), statement B.5.3. The same statement says that a rise approaching 2 metres "
                "by 2100 under the very high scenario cannot be ruled out because of deep uncertainty in ice-sheet "
                "processes (low confidence); that is outside these ranges.",
                kind="published-value",
                unit=METRES,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean",
                    baseline="1995–2014",
                    basis="Projections for 2100 under SSP1-1.9, SSP1-2.6, SSP2-4.5 and SSP5-8.5 (SSP3-7.0 is not "
                    "in the statement). Likely range: assessed probability 66–100% (IPCC calibrated language); "
                    "medium confidence. Each end of the range is a separate value; the SPM gives no central "
                    "estimate.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(SCENARIO_DIM, BOUND_DIM),
                headline_dims=(("scenario", "ssp245"), ("bound", "likely-low")),
            ),
            inputs=(SPM,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=8, value_range=(0.0, 2.0)),
        ),
    ]
